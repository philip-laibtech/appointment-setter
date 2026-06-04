from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .forms import CompanyLoginForm, CompanyRegistrationForm, CompanySettingsForm
from bookings.models import Booking
from staff_members.models import StaffMember
from services.models import ServiceOffering


@require_http_methods(["GET", "POST"])
def register_view(request):
    if request.user.is_authenticated:
        return redirect("company_accounts:dashboard")
    form = CompanyRegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect("company_accounts:dashboard")
    return render(request, "company_accounts/register.html", {"form": form})


@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.user.is_authenticated:
        return redirect("company_accounts:dashboard")
    form = CompanyLoginForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        login(request, form.get_user())
        return redirect("company_accounts:dashboard")
    return render(request, "company_accounts/login.html", {"form": form})


@require_http_methods(["POST"])
def logout_view(request):
    logout(request)
    return redirect("company_accounts:login")


@login_required
def dashboard_view(request):
    company = request.user
    now = timezone.now()

    staff_members = StaffMember.objects.filter(company=company, is_active=True)
    staff_total = StaffMember.objects.filter(company=company).count()
    staff_active = staff_members.count()
    service_total = ServiceOffering.objects.filter(company=company).count()
    service_active = ServiceOffering.objects.filter(company=company, is_active=True).count()

    upcoming_bookings = (
        Booking.objects.filter(
            company=company,
            status=Booking.Status.CONFIRMED,
            start_at__gte=now,
        )
        .select_related("staff_member", "service_offering")
        .order_by("start_at")[:15]
    )
    upcoming_count = Booking.objects.filter(
        company=company,
        status=Booking.Status.CONFIRMED,
        start_at__gte=now,
    ).count()

    return render(request, "company_accounts/dashboard.html", {
        "company": company,
        "staff_members": staff_members,
        "staff_total": staff_total,
        "staff_active": staff_active,
        "service_total": service_total,
        "service_active": service_active,
        "upcoming_bookings": upcoming_bookings,
        "upcoming_count": upcoming_count,
    })


_SETTINGS_UPDATE_FIELDS = [
    "business_name",
    "public_page_enabled",
    "timezone",
    "show_staff_names_publicly",
    "enable_any_employee_option",
    "booking_confirmation_mode",
    "updated_at",
]


@login_required
@require_http_methods(["GET", "POST"])
def settings_view(request):
    company = request.user
    form = CompanySettingsForm(request.POST or None, instance=company)
    if request.method == "POST" and form.is_valid():
        instance = form.save(commit=False)
        instance.save(update_fields=_SETTINGS_UPDATE_FIELDS)
        messages.success(request, "Settings saved.")
        return redirect("company_accounts:settings")
    return render(request, "company_accounts/settings.html", {"form": form, "company": company})
