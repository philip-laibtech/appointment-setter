from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from bookings.models import Booking

from .forms import StaffMemberEditForm, StaffMemberForm
from .models import StaffMember


@login_required
@require_http_methods(["GET"])
def staff_list_view(request):
    members = StaffMember.objects.filter(company=request.user)
    return render(request, "staff_members/staff_list.html", {"members": members})


@login_required
@require_http_methods(["GET", "POST"])
def staff_create_view(request):
    form = StaffMemberForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        member = form.save(commit=False)
        member.company = request.user
        member.save()
        messages.success(request, f"Staff member \"{member.name}\" added.")
        return redirect("staff_members:list")
    return render(request, "staff_members/staff_form.html", {"form": form})


@login_required
@require_http_methods(["GET", "POST"])
def staff_edit_view(request, member_id):
    member = get_object_or_404(StaffMember, pk=member_id, company=request.user)
    form = StaffMemberEditForm(request.POST or None, instance=member)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Staff member \"{member.name}\" updated.")
        return redirect("staff_members:list")
    return render(request, "staff_members/staff_form.html", {
        "form": form,
        "member": member,
        "title": "Edit Staff Member",
        "submit_label": "Save changes",
    })


@login_required
@require_http_methods(["GET", "POST"])
def staff_delete_view(request, member_id):
    member = get_object_or_404(StaffMember, pk=member_id, company=request.user)
    now = timezone.now()
    has_future_slots = member.appointment_slots.filter(start_at__gt=now).exists()
    has_future_bookings = member.bookings.filter(
        start_at__gt=now,
        status__in=[Booking.Status.CONFIRMED, Booking.Status.PENDING],
    ).exists()
    is_blocked = has_future_slots or has_future_bookings

    if request.method == "POST":
        if is_blocked:
            messages.error(
                request,
                f"Cannot delete \"{member.name}\": they have upcoming slots or active bookings.",
            )
            return redirect(request.path)
        member.delete()
        messages.success(request, f"Staff member \"{member.name}\" deleted.")
        return redirect("staff_members:list")

    return render(request, "staff_members/staff_confirm_delete.html", {
        "member": member,
        "is_blocked": is_blocked,
        "has_future_slots": has_future_slots,
        "has_future_bookings": has_future_bookings,
    })
