from datetime import date as date_type
from datetime import datetime
from datetime import time as time_type
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from availability.models import AppointmentSlot
from company_accounts.models import CompanyAccount
from notifications.services import (
    send_booking_confirmed_to_customer,
    send_booking_created_notifications,
    send_booking_declined_to_customer,
)
from services.models import ServiceOffering, StaffServiceOffering
from staff_members.models import StaffMember

from .forms import BookingForm
from .models import Booking


class _SlotTaken(Exception):
    """Raised inside the booking transaction when the slot is no longer available."""

_WINDOW_STEP = timedelta(minutes=15)
_LOOKAHEAD_DAYS = 60

# Booking statuses that count as "occupying" a time window for conflict detection.
_ACTIVE_BOOKING_STATUSES = [Booking.Status.CONFIRMED, Booking.Status.PENDING]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_active_company(company_slug):
    return get_object_or_404(CompanyAccount, slug=company_slug, is_active=True)


def _require_public_page(company):
    if not company.public_page_enabled:
        raise Http404


def _get_active_staff(company, staff_uid):
    return get_object_or_404(StaffMember, public_id=staff_uid, company=company, is_active=True)


def _get_active_service(company, service_uid):
    return get_object_or_404(ServiceOffering, public_id=service_uid, company=company, is_active=True)


def _get_active_assignment(staff_member, service_offering):
    return get_object_or_404(
        StaffServiceOffering,
        staff_member=staff_member,
        service_offering=service_offering,
        is_active=True,
    )


def _day_bounds(target_date):
    """Return (start, end) aware datetimes covering the full calendar day in the local timezone."""
    start = timezone.make_aware(datetime.combine(target_date, time_type.min))
    end = timezone.make_aware(datetime.combine(target_date, time_type.max))
    return start, end


def _occupied_ranges(staff_member, day_start, day_end):
    """
    Return list of (start, end) for active bookings and blocked slots in the range.
    Both CONFIRMED and PENDING bookings are considered occupied to prevent double-booking
    of pending appointment requests.
    """
    booked = list(
        Booking.objects.filter(
            staff_member=staff_member,
            status__in=_ACTIVE_BOOKING_STATUSES,
            start_at__lt=day_end,
            end_at__gt=day_start,
        ).values_list("start_at", "end_at")
    )
    blocked = list(
        AppointmentSlot.objects.filter(
            staff_member=staff_member,
            status=AppointmentSlot.Status.BLOCKED,
            start_at__lt=day_end,
            end_at__gt=day_start,
        ).values_list("start_at", "end_at")
    )
    return booked + blocked


def _windows_for_date(staff_member, service_duration_minutes, target_date):
    """
    Generate all available start times (15-min step) for the given date.
    A window is available if:
      - It falls within an AVAILABLE AppointmentSlot for the staff member.
      - It does not overlap any active (confirmed or pending) booking or blocked slot.
      - Its start_at is in the future.
    """
    window_duration = timedelta(minutes=service_duration_minutes)
    now = timezone.now()
    day_start, day_end = _day_bounds(target_date)

    availability_slots = AppointmentSlot.objects.filter(
        staff_member=staff_member,
        status=AppointmentSlot.Status.AVAILABLE,
        start_at__lt=day_end,
        end_at__gt=day_start,
    ).order_by("start_at")

    occupied = _occupied_ranges(staff_member, day_start, day_end)

    windows = []
    for slot in availability_slots:
        current = slot.start_at
        while current + window_duration <= slot.end_at:
            if current > now:
                window_end = current + window_duration
                overlaps = any(
                    current < occ_end and window_end > occ_start
                    for occ_start, occ_end in occupied
                )
                if not overlaps:
                    windows.append(current)
            current += _WINDOW_STEP

    return windows


def _available_days(staff_member, service_duration_minutes):
    """
    Return a sorted list of dates (within the next _LOOKAHEAD_DAYS) that have
    at least one available time window for the given staff member and service.
    """
    now = timezone.now()
    horizon = now + timedelta(days=_LOOKAHEAD_DAYS)
    window_duration = timedelta(minutes=service_duration_minutes)

    availability_slots = AppointmentSlot.objects.filter(
        staff_member=staff_member,
        status=AppointmentSlot.Status.AVAILABLE,
        end_at__gt=now,
        start_at__lt=horizon,
    ).order_by("start_at")

    if not availability_slots.exists():
        return []

    occupied = list(
        Booking.objects.filter(
            staff_member=staff_member,
            status__in=_ACTIVE_BOOKING_STATUSES,
            start_at__gte=now,
            start_at__lt=horizon,
        ).values_list("start_at", "end_at")
    ) + list(
        AppointmentSlot.objects.filter(
            staff_member=staff_member,
            status=AppointmentSlot.Status.BLOCKED,
            end_at__gt=now,
            start_at__lt=horizon,
        ).values_list("start_at", "end_at")
    )

    available = set()
    for slot in availability_slots:
        current = slot.start_at
        while current + window_duration <= slot.end_at:
            if current > now:
                window_end = current + window_duration
                overlaps = any(
                    current < occ_end and window_end > occ_start
                    for occ_start, occ_end in occupied
                )
                if not overlaps:
                    available.add(timezone.localtime(current).date())
            current += _WINDOW_STEP

    return sorted(available)


def _parse_date(date_str):
    try:
        return date_type.fromisoformat(date_str)
    except (ValueError, TypeError):
        raise Http404


def _parse_start_at(date_str, start_time_str):
    """Parse URL params into a local-timezone-aware start datetime. Raises Http404 on bad input."""
    booking_date = _parse_date(date_str)
    try:
        parts = start_time_str.split("-")
        if len(parts) != 2:
            raise Http404
        hour, minute = int(parts[0]), int(parts[1])
        booking_time = time_type(hour, minute)
    except (ValueError, IndexError):
        raise Http404
    return timezone.make_aware(datetime.combine(booking_date, booking_time))


# ---------------------------------------------------------------------------
# Any Employee helpers
# ---------------------------------------------------------------------------

def _get_eligible_services_for_any(company):
    """Active services offered by at least one active staff member of the company."""
    return (
        ServiceOffering.objects.filter(
            company=company,
            is_active=True,
            staff_service_offerings__is_active=True,
            staff_service_offerings__staff_member__company=company,
            staff_service_offerings__staff_member__is_active=True,
        )
        .order_by("name")
        .distinct()
    )


def _eligible_staff_for_any(company, service):
    """Active staff members of the company who are actively assigned to the service."""
    return list(
        StaffMember.objects.filter(
            company=company,
            is_active=True,
            staff_service_offerings__service_offering=service,
            staff_service_offerings__is_active=True,
        ).distinct().order_by("pk")
    )


def _available_days_for_any(company, service):
    """Sorted list of dates with at least one available window across all eligible staff."""
    available = set()
    for staff in _eligible_staff_for_any(company, service):
        available.update(_available_days(staff, service.duration_minutes))
    return sorted(available)


def _windows_for_date_any(company, service, target_date):
    """Sorted unique available start times across all eligible staff for the given date."""
    available = set()
    for staff in _eligible_staff_for_any(company, service):
        available.update(_windows_for_date(staff, service.duration_minutes, target_date))
    return sorted(available)


def _find_eligible_staff_and_slot(company, service, start_at, end_at):
    """
    Return (staff_member, covering_slot) for the first eligible staff member
    who has an available covering slot for the requested window, or (None, None).
    Both CONFIRMED and PENDING bookings are checked for conflicts.
    """
    for staff in _eligible_staff_for_any(company, service):
        slot = AppointmentSlot.objects.filter(
            staff_member=staff,
            status=AppointmentSlot.Status.AVAILABLE,
            start_at__lte=start_at,
            end_at__gte=end_at,
        ).first()
        if not slot:
            continue
        if Booking.objects.filter(
            staff_member=staff,
            status__in=_ACTIVE_BOOKING_STATUSES,
            start_at__lt=end_at,
            end_at__gt=start_at,
        ).exists():
            continue
        if AppointmentSlot.objects.filter(
            staff_member=staff,
            status=AppointmentSlot.Status.BLOCKED,
            start_at__lt=end_at,
            end_at__gt=start_at,
        ).exists():
            continue
        return staff, slot
    return None, None


def _booking_status_and_slot_status(company):
    """Return the booking status based on the company's confirmation mode."""
    if company.booking_confirmation_mode == CompanyAccount.BookingConfirmationMode.MANUAL:
        return Booking.Status.PENDING
    return Booking.Status.CONFIRMED


# ---------------------------------------------------------------------------
# Public views
# ---------------------------------------------------------------------------

@require_http_methods(["GET"])
@ratelimit(key="ip", rate="20/m", block=True)
def public_booking_entry_view(request, company_slug):
    company = _get_active_company(company_slug)
    if not company.public_page_enabled:
        return render(
            request,
            "bookings/public_unavailable.html",
            {"company": company, "reason": "disabled"},
        )

    active_staff = list(StaffMember.objects.filter(company=company, is_active=True))

    if not active_staff:
        return render(
            request,
            "bookings/public_unavailable.html",
            {"company": company, "reason": "no_staff"},
        )

    if len(active_staff) == 1:
        return redirect(
            "bookings:service_select",
            company_slug=company_slug,
            staff_uid=active_staff[0].public_id,
        )

    return render(
        request,
        "bookings/public_staff_select.html",
        {"company": company, "staff_members": active_staff},
    )


@require_http_methods(["GET"])
@ratelimit(key="ip", rate="60/h", block=True)
def public_service_select_view(request, company_slug, staff_uid):
    company = _get_active_company(company_slug)
    _require_public_page(company)
    staff_member = _get_active_staff(company, staff_uid)

    services = (
        ServiceOffering.objects.filter(
            company=company,
            is_active=True,
            staff_service_offerings__staff_member=staff_member,
            staff_service_offerings__is_active=True,
        )
        .order_by("name")
        .distinct()
    )

    return render(
        request,
        "bookings/public_service_select.html",
        {"company": company, "staff_member": staff_member, "services": services},
    )


@require_http_methods(["GET"])
@ratelimit(key="ip", rate="60/h", block=True)
def public_slot_select_view(request, company_slug, staff_uid, service_uid):
    """Day selection: shows calendar days that have at least one available window."""
    company = _get_active_company(company_slug)
    _require_public_page(company)
    staff_member = _get_active_staff(company, staff_uid)
    service = _get_active_service(company, service_uid)
    _get_active_assignment(staff_member, service)

    days = _available_days(staff_member, service.duration_minutes)

    return render(
        request,
        "bookings/public_slot_select.html",
        {
            "company": company,
            "staff_member": staff_member,
            "service": service,
            "days": days,
        },
    )


@require_http_methods(["GET"])
@ratelimit(key="ip", rate="60/h", block=True)
def public_time_select_view(request, company_slug, staff_uid, service_uid, date):
    """Time selection: shows available 15-minute-stepped windows for a chosen day."""
    company = _get_active_company(company_slug)
    _require_public_page(company)
    staff_member = _get_active_staff(company, staff_uid)
    service = _get_active_service(company, service_uid)
    _get_active_assignment(staff_member, service)

    target_date = _parse_date(date)
    windows = _windows_for_date(staff_member, service.duration_minutes, target_date)

    return render(
        request,
        "bookings/public_time_select.html",
        {
            "company": company,
            "staff_member": staff_member,
            "service": service,
            "target_date": target_date,
            "windows": windows,
        },
    )


@require_http_methods(["GET", "POST"])
@ratelimit(key="ip", rate="20/m", block=True)
def public_booking_form_view(request, company_slug, staff_uid, service_uid, date, start_time):
    company = _get_active_company(company_slug)
    _require_public_page(company)
    staff_member = _get_active_staff(company, staff_uid)
    service = _get_active_service(company, service_uid)
    _get_active_assignment(staff_member, service)

    start_at = _parse_start_at(date, start_time)
    end_at = start_at + timedelta(minutes=service.duration_minutes)
    now = timezone.now()

    # Validate the requested window.
    if start_at <= now:
        raise Http404

    # Must fall within an available slot for this staff member.
    covering_slot = AppointmentSlot.objects.filter(
        staff_member=staff_member,
        status=AppointmentSlot.Status.AVAILABLE,
        start_at__lte=start_at,
        end_at__gte=end_at,
    ).first()
    if not covering_slot:
        raise Http404

    # Must not overlap any active (confirmed or pending) booking.
    if Booking.objects.filter(
        staff_member=staff_member,
        status__in=_ACTIVE_BOOKING_STATUSES,
        start_at__lt=end_at,
        end_at__gt=start_at,
    ).exists():
        raise Http404

    # Must not overlap any blocked slot.
    if AppointmentSlot.objects.filter(
        staff_member=staff_member,
        status=AppointmentSlot.Status.BLOCKED,
        start_at__lt=end_at,
        end_at__gt=start_at,
    ).exists():
        raise Http404

    form = BookingForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                # Lock the covering slot row.
                locked_slot = (
                    AppointmentSlot.objects.select_for_update()
                    .filter(
                        staff_member=staff_member,
                        status=AppointmentSlot.Status.AVAILABLE,
                        start_at__lte=start_at,
                        end_at__gte=end_at,
                    )
                    .first()
                )
                if not locked_slot:
                    raise _SlotTaken

                # Re-validate inside the transaction with locks held.
                now_inner = timezone.now()
                if start_at <= now_inner:
                    raise Http404
                if Booking.objects.filter(
                    staff_member=staff_member,
                    status__in=_ACTIVE_BOOKING_STATUSES,
                    start_at__lt=end_at,
                    end_at__gt=start_at,
                ).exists():
                    raise _SlotTaken
                if not StaffServiceOffering.objects.filter(
                    staff_member=staff_member,
                    service_offering=service,
                    is_active=True,
                ).exists():
                    raise Http404

                booking_status = _booking_status_and_slot_status(company)

                booking = Booking.objects.create(
                    company=company,
                    staff_member=staff_member,
                    service_offering=service,
                    appointment_slot=locked_slot,
                    start_at=start_at,
                    end_at=end_at,
                    customer_first_name=form.cleaned_data["customer_first_name"],
                    customer_last_name=form.cleaned_data["customer_last_name"],
                    customer_email=form.cleaned_data["customer_email"],
                    customer_phone=form.cleaned_data["customer_phone"],
                    customer_message=form.cleaned_data["customer_message"],
                    # Set only after form.is_valid() confirms privacy_accepted=True,
                    # so this timestamp is proof the checkbox was checked.
                    privacy_accepted_at=now_inner,
                    status=booking_status,
                )

                transaction.on_commit(
                    lambda booking=booking: send_booking_created_notifications(booking)
                )

        except _SlotTaken:
            return render(
                request,
                "bookings/public_unavailable.html",
                {
                    "company": company,
                    "reason": "slot_taken",
                    "time_select_url": reverse(
                        "bookings:time_select",
                        kwargs={
                            "company_slug": company_slug,
                            "staff_uid": staff_uid,
                            "service_uid": service_uid,
                            "date": start_at.date().isoformat(),
                        },
                    ),
                },
            )
        except AppointmentSlot.DoesNotExist:
            raise Http404

        return redirect(
            "bookings:confirmed",
            company_slug=company_slug,
            public_token=booking.public_token,
        )

    return render(
        request,
        "bookings/public_booking_form.html",
        {
            "company": company,
            "staff_member": staff_member,
            "service": service,
            "start_at": start_at,
            "end_at": end_at,
            "form": form,
        },
    )


_CONFIRMED_PAGE_TTL = timedelta(minutes=10)


@require_http_methods(["GET"])
def public_booking_confirmed_view(request, company_slug, public_token):
    company = _get_active_company(company_slug)
    booking = get_object_or_404(Booking, public_token=public_token, company=company)
    if timezone.now() > booking.created_at + _CONFIRMED_PAGE_TTL:
        raise Http404
    response = render(
        request,
        "bookings/public_booking_confirmed.html",
        {"company": company, "booking": booking},
    )
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def _require_any_employee_enabled(company):
    if not company.enable_any_employee_option:
        raise Http404


@require_http_methods(["GET"])
@ratelimit(key="ip", rate="60/h", block=True)
def any_service_select_view(request, company_slug):
    company = _get_active_company(company_slug)
    _require_public_page(company)
    _require_any_employee_enabled(company)
    services = _get_eligible_services_for_any(company)
    return render(
        request,
        "bookings/any_service_select.html",
        {"company": company, "services": services},
    )


@require_http_methods(["GET"])
@ratelimit(key="ip", rate="60/h", block=True)
def any_slot_select_view(request, company_slug, service_uid):
    """Day selection: shows calendar days with at least one available window across all eligible staff."""
    company = _get_active_company(company_slug)
    _require_public_page(company)
    _require_any_employee_enabled(company)
    service = _get_active_service(company, service_uid)
    days = _available_days_for_any(company, service)
    return render(
        request,
        "bookings/any_slot_select.html",
        {"company": company, "service": service, "days": days},
    )


@require_http_methods(["GET"])
@ratelimit(key="ip", rate="60/h", block=True)
def any_time_select_view(request, company_slug, service_uid, date):
    """Time selection: shows available 15-minute-stepped windows for a chosen day across all eligible staff."""
    company = _get_active_company(company_slug)
    _require_public_page(company)
    _require_any_employee_enabled(company)
    service = _get_active_service(company, service_uid)
    target_date = _parse_date(date)
    windows = _windows_for_date_any(company, service, target_date)
    return render(
        request,
        "bookings/any_time_select.html",
        {
            "company": company,
            "service": service,
            "target_date": target_date,
            "windows": windows,
        },
    )


@require_http_methods(["GET", "POST"])
@ratelimit(key="ip", rate="20/m", block=True)
def any_booking_form_view(request, company_slug, service_uid, date, start_time):
    company = _get_active_company(company_slug)
    _require_public_page(company)
    _require_any_employee_enabled(company)
    service = _get_active_service(company, service_uid)

    start_at = _parse_start_at(date, start_time)
    end_at = start_at + timedelta(minutes=service.duration_minutes)
    now = timezone.now()

    if start_at <= now:
        raise Http404

    staff_member, covering_slot = _find_eligible_staff_and_slot(company, service, start_at, end_at)
    if not staff_member:
        raise Http404

    form = BookingForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                now_inner = timezone.now()
                if start_at <= now_inner:
                    raise Http404

                # Re-find a valid staff+slot under lock.
                booking_staff = None
                locked_slot = None
                for staff in _eligible_staff_for_any(company, service):
                    if Booking.objects.filter(
                        staff_member=staff,
                        status__in=_ACTIVE_BOOKING_STATUSES,
                        start_at__lt=end_at,
                        end_at__gt=start_at,
                    ).exists():
                        continue
                    slot = (
                        AppointmentSlot.objects.select_for_update()
                        .filter(
                            staff_member=staff,
                            status=AppointmentSlot.Status.AVAILABLE,
                            start_at__lte=start_at,
                            end_at__gte=end_at,
                        )
                        .first()
                    )
                    if not slot:
                        continue
                    if AppointmentSlot.objects.filter(
                        staff_member=staff,
                        status=AppointmentSlot.Status.BLOCKED,
                        start_at__lt=end_at,
                        end_at__gt=start_at,
                    ).exists():
                        continue
                    booking_staff = staff
                    locked_slot = slot
                    break

                if not locked_slot:
                    raise _SlotTaken

                booking_status = _booking_status_and_slot_status(company)

                booking = Booking.objects.create(
                    company=company,
                    staff_member=booking_staff,
                    service_offering=service,
                    appointment_slot=locked_slot,
                    start_at=start_at,
                    end_at=end_at,
                    customer_first_name=form.cleaned_data["customer_first_name"],
                    customer_last_name=form.cleaned_data["customer_last_name"],
                    customer_email=form.cleaned_data["customer_email"],
                    customer_phone=form.cleaned_data["customer_phone"],
                    customer_message=form.cleaned_data["customer_message"],
                    # Set only after form.is_valid() confirms privacy_accepted=True,
                    # so this timestamp is proof the checkbox was checked.
                    privacy_accepted_at=now_inner,
                    status=booking_status,
                )

                transaction.on_commit(
                    lambda booking=booking: send_booking_created_notifications(booking)
                )

        except _SlotTaken:
            return render(
                request,
                "bookings/public_unavailable.html",
                {
                    "company": company,
                    "reason": "slot_taken",
                    "time_select_url": reverse(
                        "bookings:any_time_select",
                        kwargs={
                            "company_slug": company_slug,
                            "service_uid": service_uid,
                            "date": start_at.date().isoformat(),
                        },
                    ),
                },
            )

        return redirect(
            "bookings:confirmed",
            company_slug=company_slug,
            public_token=booking.public_token,
        )

    return render(
        request,
        "bookings/any_booking_form.html",
        {
            "company": company,
            "staff_member": staff_member,
            "service": service,
            "start_at": start_at,
            "end_at": end_at,
            "target_date": start_at.date(),
            "form": form,
        },
    )


@require_http_methods(["GET", "POST"])
def public_booking_cancel_view(request, company_slug, public_token):
    company = _get_active_company(company_slug)
    booking = get_object_or_404(
        Booking,
        public_token=public_token,
        company=company,
        status=Booking.Status.CONFIRMED,
    )

    if request.method == "POST":
        with transaction.atomic():
            locked = (
                Booking.objects.select_for_update()
                .filter(
                    public_token=public_token,
                    company=company,
                    status=Booking.Status.CONFIRMED,
                )
                .first()
            )
            if not locked:
                return redirect(
                    "bookings:confirmed",
                    company_slug=company_slug,
                    public_token=public_token,
                )
            locked.status = Booking.Status.CANCELLED
            locked.save(update_fields=["status", "updated_at"])

        return redirect(
            "bookings:confirmed",
            company_slug=company_slug,
            public_token=public_token,
        )

    return render(
        request,
        "bookings/public_booking_cancel.html",
        {"company": company, "booking": booking},
    )


# ---------------------------------------------------------------------------
# Internal company management views
# ---------------------------------------------------------------------------

@login_required
@require_http_methods(["GET"])
def pending_bookings_view(request):
    pending = (
        Booking.objects.filter(
            company=request.user,
            status=Booking.Status.PENDING,
        )
        .select_related("staff_member", "service_offering")
        .order_by("start_at")
    )
    return render(
        request,
        "bookings/pending_booking_list.html",
        {"pending_bookings": pending},
    )


@login_required
@require_http_methods(["GET"])
def all_bookings_view(request):
    now = timezone.now()
    company = request.user

    upcoming_qs = (
        Booking.objects.filter(
            company=company,
            start_at__gte=now,
            status__in=[Booking.Status.CONFIRMED, Booking.Status.PENDING],
        )
        .select_related("staff_member", "service_offering")
        .order_by("start_at")
    )

    paginator = Paginator(upcoming_qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "bookings/all_bookings_list.html",
        {"page_obj": page_obj},
    )


@login_required
@require_http_methods(["GET"])
def past_bookings_view(request):
    past_qs = (
        Booking.objects.filter(
            company=request.user,
            start_at__lt=timezone.now(),
        )
        .select_related("staff_member", "service_offering")
        .order_by("-start_at")
    )

    paginator = Paginator(past_qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "bookings/past_bookings_list.html",
        {"page_obj": page_obj},
    )


@login_required
@require_http_methods(["POST"])
def confirm_booking_view(request, booking_id):
    with transaction.atomic():
        booking = get_object_or_404(
            Booking.objects.select_for_update(),
            pk=booking_id,
            company=request.user,
            status=Booking.Status.PENDING,
        )
        booking.status = Booking.Status.CONFIRMED
        booking.save(update_fields=["status", "updated_at"])
        transaction.on_commit(
            lambda booking=booking: send_booking_confirmed_to_customer(booking)
        )
    return redirect("bookings:pending_bookings")


@login_required
@require_http_methods(["POST"])
def decline_booking_view(request, booking_id):
    with transaction.atomic():
        booking = get_object_or_404(
            Booking.objects.select_for_update(),
            pk=booking_id,
            company=request.user,
            status=Booking.Status.PENDING,
        )
        booking.status = Booking.Status.DECLINED
        booking.save(update_fields=["status", "updated_at"])
        transaction.on_commit(
            lambda booking=booking: send_booking_declined_to_customer(booking)
        )
    return redirect("bookings:pending_bookings")
