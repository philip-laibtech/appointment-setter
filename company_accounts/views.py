from datetime import timedelta
from zoneinfo import ZoneInfo

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from .forms import CompanyLoginForm, CompanyRegistrationForm, CompanySettingsForm
from bookings.models import Booking
from staff_members.models import StaffMember
from services.models import ServiceOffering


@require_http_methods(["GET", "POST"])
@ratelimit(key="ip", rate="10/h", block=True)
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
@ratelimit(key="ip", rate="5/m", block=True)
@ratelimit(key="post:username", rate="5/m", method="POST", block=True)
def login_view(request):
    if request.user.is_authenticated:
        return redirect("company_accounts:dashboard")
    form = CompanyLoginForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        login(request, form.get_user())
        next_url = request.POST.get("next") or request.GET.get("next")
        if next_url and url_has_allowed_host_and_scheme(
            url=next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(next_url)
        return redirect("company_accounts:dashboard")
    next_url = request.GET.get("next", "")
    return render(request, "company_accounts/login.html", {"form": form, "next": next_url})


@require_http_methods(["POST"])
def logout_view(request):
    logout(request)
    return redirect("company_accounts:login")


@login_required
def dashboard_view(request):
    company = request.user

    staff_members = StaffMember.objects.filter(company=company, is_active=True)

    tz = ZoneInfo(company.timezone)
    today_start = timezone.now().astimezone(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    todays_bookings_count = Booking.objects.filter(
        company=company,
        start_at__gte=today_start,
        start_at__lt=today_end,
        status__in=[Booking.Status.CONFIRMED, Booking.Status.PENDING],
    ).count()

    pending_bookings_count = Booking.objects.filter(
        company=company,
        status=Booking.Status.PENDING,
    ).count()

    return render(request, "company_accounts/dashboard.html", {
        "company": company,
        "staff_members": staff_members,
        "todays_bookings_count": todays_bookings_count,
        "pending_bookings_count": pending_bookings_count,
    })


_SETTINGS_UPDATE_FIELDS = [
    "business_name",
    "public_page_enabled",
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
