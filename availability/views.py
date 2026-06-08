from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from bookings.models import Booking
from staff_members.models import StaffMember

from .forms import OpenHoursForm, RecurringHoursForm
from .models import AppointmentSlot

_OVERLAP_STATUSES = [AppointmentSlot.Status.AVAILABLE, AppointmentSlot.Status.BLOCKED]


@login_required
@require_http_methods(["GET"])
def slot_list_view(request):
    staff_filter_id = request.GET.get("staff")
    slots = AppointmentSlot.objects.filter(
        company=request.user,
        start_at__gte=timezone.now(),
    ).select_related("staff_member")

    staff_members = StaffMember.objects.filter(company=request.user)
    selected_staff = None

    if staff_filter_id:
        try:
            selected_staff = staff_members.get(pk=int(staff_filter_id))
            slots = slots.filter(staff_member=selected_staff)
        except (StaffMember.DoesNotExist, ValueError):
            pass

    return render(request, "availability/slot_list.html", {
        "slots": slots,
        "staff_members": staff_members,
        "selected_staff": selected_staff,
    })


@login_required
@require_http_methods(["GET", "POST"])
def slot_create_view(request):
    form = OpenHoursForm(request.POST or None, company=request.user)
    if request.method == "POST" and form.is_valid():
        AppointmentSlot.objects.create(
            company=request.user,
            staff_member=form.cleaned_data["staff_member"],
            start_at=form.cleaned_data["start_at"],
            end_at=form.cleaned_data["end_at"],
        )
        return redirect("availability:list")
    return render(request, "availability/slot_form.html", {"form": form})


@login_required
@require_http_methods(["GET", "POST"])
def slot_edit_view(request, slot_id):
    slot = get_object_or_404(AppointmentSlot, pk=slot_id, company=request.user)
    local_start = timezone.localtime(slot.start_at)
    local_end = timezone.localtime(slot.end_at)
    initial = {
        "staff_member": slot.staff_member_id,
        "date": local_start.strftime("%Y-%m-%d"),
        "start_time": local_start.strftime("%H:%M"),
        "end_time": local_end.strftime("%H:%M"),
    }
    form = OpenHoursForm(
        request.POST or None,
        initial=initial,
        company=request.user,
        instance_pk=slot.pk,
    )
    if request.method == "POST" and form.is_valid():
        slot.staff_member = form.cleaned_data["staff_member"]
        slot.start_at = form.cleaned_data["start_at"]
        slot.end_at = form.cleaned_data["end_at"]
        slot.save()
        return redirect("availability:list")
    return render(request, "availability/slot_form.html", {
        "form": form,
        "title": "Edit Open Hours",
        "submit_label": "Save changes",
    })


@login_required
@require_http_methods(["GET", "POST"])
def slot_delete_view(request, slot_id):
    slot = get_object_or_404(AppointmentSlot, pk=slot_id, company=request.user)
    now = timezone.now()
    future_active_bookings = Booking.objects.filter(
        appointment_slot=slot,
        start_at__gt=now,
        status__in=[Booking.Status.CONFIRMED, Booking.Status.PENDING],
    ).select_related("service_offering")

    if request.method == "POST":
        if future_active_bookings.exists():
            messages.error(request, "Cannot delete: this slot has confirmed future bookings.")
            return redirect(request.path)
        slot.delete()
        messages.success(request, "Open hours block deleted.")
        return redirect("availability:list")

    return render(request, "availability/slot_confirm_delete.html", {
        "slot": slot,
        "affected_bookings": future_active_bookings,
    })


@login_required
@require_http_methods(["GET", "POST"])
def recurring_create_view(request):
    form = RecurringHoursForm(request.POST or None, company=request.user)
    if request.method == "POST" and form.is_valid():
        staff_member = form.cleaned_data["staff_member"]
        weekdays = {int(d) for d in form.cleaned_data["weekdays"]}
        start_time = form.cleaned_data["start_time"]
        end_time = form.cleaned_data["end_time"]
        date_from = form.cleaned_data["date_from"]
        date_until = form.cleaned_data["date_until"]

        now = timezone.now()
        to_create = []
        skipped = 0

        current = date_from
        while current <= date_until:
            if current.weekday() in weekdays:
                start_at = timezone.make_aware(datetime.combine(current, start_time))
                end_at = timezone.make_aware(datetime.combine(current, end_time))

                if start_at <= now:
                    skipped += 1
                elif AppointmentSlot.objects.filter(
                    staff_member=staff_member,
                    status__in=_OVERLAP_STATUSES,
                    start_at__lt=end_at,
                    end_at__gt=start_at,
                ).exists():
                    skipped += 1
                else:
                    to_create.append(AppointmentSlot(
                        company=request.user,
                        staff_member=staff_member,
                        start_at=start_at,
                        end_at=end_at,
                    ))
            current += timedelta(days=1)

        if to_create:
            AppointmentSlot.objects.bulk_create(to_create)

        created = len(to_create)
        _add_recurring_messages(request, created, skipped)
        return redirect("availability:list")

    return render(request, "availability/recurring_form.html", {"form": form})


def _add_recurring_messages(request, created, skipped):
    if created == 0 and skipped == 0:
        messages.warning(request, "No matching dates found in the selected range.")
    elif created == 0:
        messages.warning(
            request,
            f"No blocks were created — {skipped} skipped (already past or overlapping).",
        )
    else:
        n = f"{created} open hours block{'s' if created != 1 else ''}"
        msg = f"Created {n}."
        if skipped:
            msg += f" {skipped} skipped due to overlap or past date."
        messages.success(request, msg)
