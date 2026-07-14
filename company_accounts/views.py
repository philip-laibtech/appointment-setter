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
from django_otp import login as otp_login, user_has_device
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp.plugins.otp_totp.models import TOTPDevice

from django.core.mail import EmailMessage, send_mail
from django.template.loader import render_to_string

from .forms import (
    CompanyLoginForm,
    CompanyRegistrationForm,
    CompanySettingsForm,
    PasswordConfirmForm,
    SupportRequestForm,
    TOTPSetupForm,
    TwoFactorVerifyForm,
)
from .lockout import clear_failed_attempts, is_locked_out, record_failed_attempt
from .models import CompanyAccount, DeletionRequest
from .two_factor import backup_codes_remaining, build_qr_data_uri, format_secret, issue_backup_codes
from bookings.models import Booking
from staff_members.models import StaffMember
from services.models import ServiceOffering

# How long a verified-password-but-not-yet-verified-2FA session may sit idle
# before the pending login is discarded and the user must re-enter their password.
TWO_FACTOR_PENDING_TTL = timedelta(minutes=10)


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


def _safe_next_url(request, candidate):
    if candidate and url_has_allowed_host_and_scheme(
        url=candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate
    return ""


@require_http_methods(["GET", "POST"])
@ratelimit(key="ip", rate="5/m", block=True)
@ratelimit(key="post:username", rate="5/m", method="POST", block=True)
def login_view(request):
    if request.user.is_authenticated:
        return redirect("company_accounts:dashboard")

    submitted_email = request.POST.get("username", "") if request.method == "POST" else ""
    if request.method == "POST" and submitted_email and is_locked_out(submitted_email):
        messages.error(
            request,
            _("Too many failed login attempts for this account. Please try again in %(minutes)d minutes.")
            % {"minutes": django_settings.ACCOUNT_LOCKOUT_DURATION_MINUTES},
        )
        form = CompanyLoginForm(request)
        return render(request, "company_accounts/login.html", {"form": form, "next": request.GET.get("next", "")})

    form = CompanyLoginForm(request, data=request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.get_user()
        clear_failed_attempts(submitted_email)
        next_url = _safe_next_url(request, request.POST.get("next") or request.GET.get("next"))
        if user_has_device(user, confirmed=True):
            request.session["2fa_user_id"] = user.pk
            request.session["2fa_next"] = next_url
            request.session["2fa_started_at"] = timezone.now().isoformat()
            return redirect("company_accounts:two_factor_verify")
        login(request, user)
        return redirect(next_url or "company_accounts:dashboard")
    if request.method == "POST" and submitted_email:
        record_failed_attempt(submitted_email)
    next_url = request.GET.get("next", "")
    return render(request, "company_accounts/login.html", {"form": form, "next": next_url})


@require_http_methods(["GET", "POST"])
@ratelimit(key="ip", rate="10/m", block=True)
def two_factor_verify_view(request):
    user_id = request.session.get("2fa_user_id")
    started_at_raw = request.session.get("2fa_started_at")
    expired = False
    if started_at_raw:
        try:
            started_at = timezone.datetime.fromisoformat(started_at_raw)
        except ValueError:
            expired = True
        else:
            expired = timezone.now() - started_at > TWO_FACTOR_PENDING_TTL
    if not user_id or expired:
        for key in ("2fa_user_id", "2fa_next", "2fa_started_at"):
            request.session.pop(key, None)
        if expired:
            messages.error(request, _("Your sign-in session expired. Please log in again."))
        return redirect("company_accounts:login")

    try:
        user = CompanyAccount.objects.get(pk=user_id, is_active=True)
    except CompanyAccount.DoesNotExist:
        for key in ("2fa_user_id", "2fa_next", "2fa_started_at"):
            request.session.pop(key, None)
        return redirect("company_accounts:login")

    form = TwoFactorVerifyForm(request.POST or None, user=user)
    if request.method == "POST" and form.is_valid():
        next_url = request.session.get("2fa_next", "")
        for key in ("2fa_user_id", "2fa_next", "2fa_started_at"):
            request.session.pop(key, None)
        login(request, user)
        otp_login(request, form.matched_device)
        return redirect(next_url or "company_accounts:dashboard")
    return render(request, "company_accounts/two_factor_verify.html", {"form": form})


@require_http_methods(["POST"])
def two_factor_cancel_view(request):
    for key in ("2fa_user_id", "2fa_next", "2fa_started_at"):
        request.session.pop(key, None)
    return redirect("company_accounts:login")


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
    "email",
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
    "slot_interval_minutes",
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
    return render(request, "company_accounts/settings.html", {
        "form": form,
        "company": company,
        "two_factor_enabled": user_has_device(company, confirmed=True),
    })


@login_required
@require_http_methods(["GET", "POST"])
@ratelimit(key="user", rate="5/h", block=True)
def support_request_view(request):
    company = request.user
    form = SupportRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        support_email = django_settings.SUPPORT_EMAIL
        if support_email:
            subject = f"Support Request — {company.business_name}: {form.cleaned_data['subject']}"
            body = render_to_string(
                "company_accounts/emails/support_request.txt",
                {
                    "company": company,
                    "subject": form.cleaned_data["subject"],
                    "message": form.cleaned_data["message"],
                },
            )
            try:
                email = EmailMessage(
                    subject,
                    body,
                    django_settings.DEFAULT_FROM_EMAIL,
                    [support_email],
                    reply_to=[company.email],
                )
                email.send()
            except Exception:
                logger.exception("Failed to send support request email for company %s", company.pk)
                messages.error(request, _("Something went wrong sending your message. Please try again."))
                return redirect("company_accounts:support_request")
        messages.success(request, _("Your message has been sent. We'll get back to you as soon as possible."))
        return redirect("company_accounts:settings")
    return render(request, "company_accounts/support_request.html", {
        "form": form,
        "company": company,
    })


@login_required
@require_http_methods(["GET"])
def two_factor_status_view(request):
    company = request.user
    enabled = user_has_device(company, confirmed=True)
    return render(request, "company_accounts/two_factor_status.html", {
        "company": company,
        "enabled": enabled,
        "backup_codes_remaining": backup_codes_remaining(company) if enabled else 0,
        "password_form": PasswordConfirmForm(user=company),
    })


@login_required
@require_http_methods(["GET", "POST"])
@ratelimit(key="user", rate="20/h", block=True)
def two_factor_setup_view(request):
    company = request.user
    if user_has_device(company, confirmed=True):
        messages.info(request, _("Two-factor authentication is already enabled."))
        return redirect("company_accounts:two_factor_status")

    if request.method == "POST":
        device = TOTPDevice.objects.filter(user=company, confirmed=False).order_by("-id").first()
        if device is None:
            messages.error(request, _("Your setup session expired. Please start again."))
            return redirect("company_accounts:two_factor_setup")
        form = TOTPSetupForm(request.POST, device=device)
        if form.is_valid():
            device.confirmed = True
            device.name = "default"
            device.save(update_fields=["confirmed", "name"])
            codes = issue_backup_codes(company)
            messages.success(request, _("Two-factor authentication is now enabled."))
            return render(request, "company_accounts/two_factor_backup_codes.html", {
                "company": company,
                "codes": codes,
            })
    else:
        TOTPDevice.objects.filter(user=company, confirmed=False).delete()
        device = TOTPDevice.objects.create(user=company, confirmed=False, name="default-unconfirmed")
        form = TOTPSetupForm(device=device)

    return render(request, "company_accounts/two_factor_setup.html", {
        "company": company,
        "form": form,
        "qr_data_uri": build_qr_data_uri(device.config_url),
        "secret": format_secret(device),
    })


@login_required
@require_http_methods(["POST"])
@ratelimit(key="user", rate="10/h", block=True)
def two_factor_disable_view(request):
    form = PasswordConfirmForm(request.POST, user=request.user)
    if form.is_valid():
        TOTPDevice.objects.filter(user=request.user).delete()
        StaticDevice.objects.filter(user=request.user).delete()
        messages.success(request, _("Two-factor authentication has been disabled."))
    else:
        messages.error(request, _("Incorrect password. Two-factor authentication was not disabled."))
    return redirect("company_accounts:two_factor_status")


@login_required
@require_http_methods(["POST"])
@ratelimit(key="user", rate="10/h", block=True)
def two_factor_regenerate_backup_codes_view(request):
    company = request.user
    if not user_has_device(company, confirmed=True):
        return redirect("company_accounts:two_factor_status")
    form = PasswordConfirmForm(request.POST, user=company)
    if form.is_valid():
        codes = issue_backup_codes(company)
        messages.success(request, _("New backup codes have been generated. Your old codes no longer work."))
        return render(request, "company_accounts/two_factor_backup_codes.html", {
            "company": company,
            "codes": codes,
        })
    messages.error(request, _("Incorrect password. Backup codes were not regenerated."))
    return redirect("company_accounts:two_factor_status")
