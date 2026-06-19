import logging
from datetime import timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

from django.conf import settings as django_settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from django.core.mail import send_mail
from django.template.loader import render_to_string

from .forms import CompanyLoginForm, CompanyRegistrationForm, CompanySettingsForm
from .models import DeletionRequest
from bookings.models import Booking
from staff_members.models import StaffMember
from services.models import ServiceOffering


@login_required
@require_http_methods(["GET"])
def request_account_deletion_view(request):
    return render(request, "company_accounts/account_deletion_request.html", {
        "company": request.user,
    })


@login_required
@require_http_methods(["POST"])
def submit_account_deletion_view(request):
    if not request.POST.get("confirmed"):
        return redirect("company_accounts:request_account_deletion")

    company = request.user

    if hasattr(company, "deletion_request"):
        messages.info(
            request,
            _("A deletion request is already pending for your account. Our support team will contact you shortly."),
        )
        return redirect("company_accounts:settings")

    deletion_request = DeletionRequest.objects.create(company=company)

    support_email = django_settings.SUPPORT_EMAIL
    if support_email:
        subject = f"Account Deletion Request — {company.business_name}"
        body = render_to_string(
            "company_accounts/emails/deletion_request.txt",
            {
                "company": company,
                "token": deletion_request.token,
                "requested_at": deletion_request.requested_at,
            },
        )
        try:
            send_mail(subject, body, django_settings.DEFAULT_FROM_EMAIL, [support_email])
        except Exception:
            logger.exception("Failed to send deletion request notification to support for company %s", company.pk)

    messages.success(
        request,
        _("Your deletion request has been received. A support agent will call you at %(phone)s within 1 business day to verify your identity.") % {"phone": company.phone},
    )
    return redirect("company_accounts:settings")


@login_required
@require_http_methods(["GET", "POST"])
def tos_reaccept_view(request):
    next_url = request.GET.get("next") or request.POST.get("next") or reverse("company_accounts:dashboard")
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        next_url = reverse("company_accounts:dashboard")

    if request.method == "POST" and request.POST.get("tos_accepted"):
        request.user.tos_accepted_at = timezone.now()
        request.user.tos_version = django_settings.CURRENT_TOS_VERSION
        request.user.save(update_fields=["tos_accepted_at", "tos_version"])
        return redirect(next_url)

    return render(request, "company_accounts/tos_reaccept.html", {
        "tos_url": reverse("landing:terms_of_service"),
        "next": next_url,
    })


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
    return render(request, "company_accounts/register.html", {
        "form": form,
        "tos_url": reverse("landing:terms_of_service"),
        "privacy_url": reverse("landing:privacy_policy"),
    })


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
    "street",
    "plz",
    "location",
    "phone",
    "website",
    "public_page_enabled",
    "show_staff_names_publicly",
    "enable_any_employee_option",
    "booking_confirmation_mode",
    "language",
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
        translation.activate(instance.language)
        request.LANGUAGE_CODE = translation.get_language()
        messages.success(request, _("Settings saved."))
        return redirect("company_accounts:settings")
    return render(request, "company_accounts/settings.html", {"form": form, "company": company})
