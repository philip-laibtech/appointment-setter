from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from .forms import ServiceOfferingEditForm, ServiceOfferingForm
from .models import ServiceOffering, StaffServiceOffering


@login_required
@require_http_methods(["GET"])
def service_list_view(request):
    active_assignments = Prefetch(
        "staff_service_offerings",
        queryset=StaffServiceOffering.objects.filter(
            is_active=True
        ).select_related("staff_member"),
        to_attr="active_assignments",
    )
    services = ServiceOffering.objects.filter(
        company=request.user
    ).prefetch_related(active_assignments)
    return render(request, "services/service_list.html", {"services": services})


@login_required
@require_http_methods(["GET", "POST"])
def service_create_view(request):
    form = ServiceOfferingForm(request.POST or None, company=request.user)
    if request.method == "POST" and form.is_valid():
        service = form.save(commit=False)
        service.company = request.user
        service.save()
        _sync_staff_assignments(service, form.cleaned_data["assigned_staff_members"])
        messages.success(request, _('Service "%(name)s" created.') % {"name": service.name})
        return redirect("services:list")
    return render(request, "services/service_form.html", {
        "form": form,
        "is_edit": False,
        "title": _("Add Service"),
        "submit_label": _("Add service"),
    })


@login_required
@require_http_methods(["GET", "POST"])
def service_edit_view(request, service_id):
    service = get_object_or_404(ServiceOffering, pk=service_id, company=request.user)
    current_staff_ids = list(
        StaffServiceOffering.objects.filter(
            service_offering=service, is_active=True
        ).values_list("staff_member_id", flat=True)
    )
    form = ServiceOfferingEditForm(
        request.POST or None,
        instance=service,
        company=request.user,
        initial={"assigned_staff_members": current_staff_ids},
    )
    if request.method == "POST" and form.is_valid():
        service = form.save()
        _sync_staff_assignments(service, form.cleaned_data["assigned_staff_members"])
        messages.success(request, _('Service "%(name)s" updated.') % {"name": service.name})
        return redirect("services:list")
    return render(request, "services/service_form.html", {
        "form": form,
        "service": service,
        "is_edit": True,
        "title": _("Edit Service"),
        "submit_label": _("Save changes"),
    })


@login_required
@require_http_methods(["GET", "POST"])
def service_delete_view(request, service_id):
    service = get_object_or_404(ServiceOffering, pk=service_id, company=request.user)
    if request.method == "POST":
        if service.bookings.exists():
            messages.error(
                request,
                _('"%(name)s" has existing bookings and cannot be deleted.') % {"name": service.name},
            )
            return redirect("services:delete", service_id)
        name = service.name
        service.delete()
        messages.success(request, _('Service "%(name)s" deleted.') % {"name": name})
        return redirect("services:list")
    return render(request, "services/service_confirm_delete.html", {
        "service": service,
        "has_bookings": service.bookings.exists(),
    })


def _sync_staff_assignments(service, selected_members):
    selected_ids = {m.pk for m in selected_members}

    for member in selected_members:
        assignment, created = StaffServiceOffering.objects.get_or_create(
            staff_member=member,
            service_offering=service,
            defaults={"is_active": True},
        )
        if not created and not assignment.is_active:
            assignment.is_active = True
            assignment.save(update_fields=["is_active", "updated_at"])

    StaffServiceOffering.objects.filter(
        service_offering=service,
        is_active=True,
    ).exclude(staff_member_id__in=selected_ids).update(is_active=False)
