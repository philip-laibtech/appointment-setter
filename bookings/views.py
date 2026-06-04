from datetime import date as date_type
from datetime import datetime
from datetime import time as time_type
from datetime import timedelta
from datetime import timezone as dt_tz

from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from availability.models import AppointmentSlot
from company_accounts.models import CompanyAccount
from services.models import ServiceOffering, StaffServiceOffering
from staff_members.models import StaffMember

from .forms import BookingForm
from .models import Booking

# TODO: Add rate limiting to booking routes before production.
# Consider django-ratelimit for IP-based throttling on /b/ endpoints.

_WINDOW_STEP = timedelta(minutes=15)
_LOOKAHEAD_DAYS = 60


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_active_company(company_slug):
    return get_object_or_404(CompanyAccount, slug=company_slug, is_active=True)


def _require_public_page(company):
    if not company.public_page_enabled:
        raise Http404


def _get_active_staff(company, staff_id):
    return get_object_or_404(StaffMember, pk=staff_id, company=company, is_active=True)


def _get_active_service(company, service_id):
    return get_object_or_404(ServiceOffering, pk=service_id, company=company, is_active=True)


def _get_active_assignment(staff_member, service_offering):
    return get_object_or_404(
        StaffServiceOffering,
        staff_member=staff_member,
        service_offering=service_offering,
        is_active=True,
    )


def _day_bounds_utc(target_date):
    """Return (start, end) UTC-aware datetimes covering the full calendar day."""
    start = datetime.combine(target_date, time_type.min, tzinfo=dt_tz.utc)
    end = datetime.combine(target_date, time_type.max, tzinfo=dt_tz.utc)
    return start, end


def _occupied_ranges(staff_member, day_start, day_end):
    """Return list of (start, end) for confirmed bookings and blocked slots in the range."""
    booked = list(
        Booking.objects.filter(
            staff_member=staff_member,
            status=Booking.Status.CONFIRMED,
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
      - It does not overlap any confirmed booking or blocked slot.
      - Its start_at is in the future.
    """
    window_duration = timedelta(minutes=service_duration_minutes)
    now = timezone.now()
    day_start, day_end = _day_bounds_utc(target_date)

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
            status=Booking.Status.CONFIRMED,
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
                    available.add(current.date())
            current += _WINDOW_STEP

    return sorted(available)


def _parse_date(date_str):
    try:
        return date_type.fromisoformat(date_str)
    except (ValueError, TypeError):
        raise Http404


def _parse_start_at(date_str, start_time_str):
    """Parse URL params into a UTC-aware start datetime. Raises Http404 on bad input."""
    booking_date = _parse_date(date_str)
    try:
        parts = start_time_str.split("-")
        if len(parts) != 2:
            raise Http404
        hour, minute = int(parts[0]), int(parts[1])
        booking_time = time_type(hour, minute)
    except (ValueError, IndexError):
        raise Http404
    return datetime.combine(booking_date, booking_time, tzinfo=dt_tz.utc)


# ---------------------------------------------------------------------------
# Public views
# ---------------------------------------------------------------------------

@require_http_methods(["GET"])
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
            staff_id=active_staff[0].pk,
        )

    return render(
        request,
        "bookings/public_staff_select.html",
        {"company": company, "staff_members": active_staff},
    )


@require_http_methods(["GET"])
def public_service_select_view(request, company_slug, staff_id):
    company = _get_active_company(company_slug)
    _require_public_page(company)
    staff_member = _get_active_staff(company, staff_id)

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
def public_slot_select_view(request, company_slug, staff_id, service_id):
    """Day selection: shows calendar days that have at least one available window."""
    company = _get_active_company(company_slug)
    _require_public_page(company)
    staff_member = _get_active_staff(company, staff_id)
    service = _get_active_service(company, service_id)
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
def public_time_select_view(request, company_slug, staff_id, service_id, date):
    """Time selection: shows available 15-minute-stepped windows for a chosen day."""
    company = _get_active_company(company_slug)
    _require_public_page(company)
    staff_member = _get_active_staff(company, staff_id)
    service = _get_active_service(company, service_id)
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
def public_booking_form_view(request, company_slug, staff_id, service_id, date, start_time):
    company = _get_active_company(company_slug)
    _require_public_page(company)
    staff_member = _get_active_staff(company, staff_id)
    service = _get_active_service(company, service_id)
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

    # Must not overlap any existing confirmed booking.
    if Booking.objects.filter(
        staff_member=staff_member,
        status=Booking.Status.CONFIRMED,
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
                # Lock overlapping confirmed bookings to prevent race conditions.
                Booking.objects.select_for_update().filter(
                    staff_member=staff_member,
                    status=Booking.Status.CONFIRMED,
                    start_at__lt=end_at,
                    end_at__gt=start_at,
                )

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
                    raise Http404

                # Re-validate inside the transaction with locks held.
                now_inner = timezone.now()
                if start_at <= now_inner:
                    raise Http404
                if Booking.objects.filter(
                    staff_member=staff_member,
                    status=Booking.Status.CONFIRMED,
                    start_at__lt=end_at,
                    end_at__gt=start_at,
                ).exists():
                    raise Http404
                if not StaffServiceOffering.objects.filter(
                    staff_member=staff_member,
                    service_offering=service,
                    is_active=True,
                ).exists():
                    raise Http404

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
                    privacy_accepted_at=now_inner,
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


@require_http_methods(["GET"])
def public_booking_confirmed_view(request, company_slug, public_token):
    company = _get_active_company(company_slug)
    booking = get_object_or_404(Booking, public_token=public_token, company=company)
    return render(
        request,
        "bookings/public_booking_confirmed.html",
        {"company": company, "booking": booking},
    )
