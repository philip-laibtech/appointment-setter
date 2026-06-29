import time
from datetime import timedelta
from io import StringIO

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core import mail
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.management import CommandError, call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from django_otp.oath import TOTP
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice

from .models import CompanyAccount
from staff_members.models import StaffMember


def current_totp_token(device):
    totp = TOTP(device.bin_key, device.step, device.t0, device.digits, device.drift)
    totp.time = time.time()
    return str(totp.token()).zfill(device.digits)


def make_account(business_name="Acme AG", email="acme@example.com", password="S3cur3Pass!"):
    return CompanyAccount.objects.create_user(
        email=email,
        password=password,
        business_name=business_name,
        tos_version=settings.CURRENT_TOS_VERSION,
    )


class CompanyAccountModelTests(TestCase):
    def test_registration_creates_account(self):
        account = make_account()
        self.assertIsNotNone(account.pk)

    def test_business_name_required(self):
        with self.assertRaises((ValueError, ValidationError)):
            CompanyAccount.objects.create_user(
                email="x@example.com",
                password="S3cur3Pass!",
                business_name="",
            )

    def test_email_required(self):
        with self.assertRaises((ValueError, ValidationError)):
            CompanyAccount.objects.create_user(
                email="",
                password="S3cur3Pass!",
                business_name="Test Corp",
            )

    def test_email_unique(self):
        make_account()
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            CompanyAccount.objects.create_user(
                email="acme@example.com",
                password="S3cur3Pass!",
                business_name="Other Corp",
            )

    def test_slug_generated_from_business_name(self):
        account = make_account(business_name="Hello World GmbH")
        self.assertEqual(account.slug, "hello-world-gmbh")

    def test_slug_unique_on_duplicate_business_name(self):
        a1 = make_account(business_name="Dupe Corp", email="one@example.com")
        a2 = make_account(business_name="Dupe Corp", email="two@example.com")
        self.assertNotEqual(a1.slug, a2.slug)
        self.assertEqual(a1.slug, "dupe-corp")
        self.assertEqual(a2.slug, "dupe-corp-1")

    def test_password_validation_is_active(self):
        with self.assertRaises(ValidationError):
            validate_password("password")


class LoginTest(TestCase):
    def setUp(self):
        cache.clear()
        self.account = make_account()
        self.login_url = reverse("company_accounts:login")

    def test_login_with_email_and_password(self):
        response = self.client.post(self.login_url, {
            "username": "acme@example.com",
            "password": "S3cur3Pass!",
        })
        self.assertRedirects(response, reverse("company_accounts:dashboard"))

    def test_login_wrong_password_fails(self):
        response = self.client.post(self.login_url, {
            "username": "acme@example.com",
            "password": "wrongpassword",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)


class LoginLockoutTests(TestCase):
    def setUp(self):
        cache.clear()
        self.account = make_account()
        self.login_url = reverse("company_accounts:login")

    def _fail_login(self):
        return self.client.post(self.login_url, {
            "username": "acme@example.com",
            "password": "wrongpassword",
        })

    def test_account_locked_out_after_threshold_failed_attempts(self):
        for _ in range(settings.ACCOUNT_LOCKOUT_THRESHOLD):
            self._fail_login()

        response = self.client.post(self.login_url, {
            "username": "acme@example.com",
            "password": "S3cur3Pass!",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_successful_login_clears_failed_attempts(self):
        for _ in range(settings.ACCOUNT_LOCKOUT_THRESHOLD - 1):
            self._fail_login()

        response = self.client.post(self.login_url, {
            "username": "acme@example.com",
            "password": "S3cur3Pass!",
        })
        self.assertRedirects(response, reverse("company_accounts:dashboard"))

    def test_lockout_is_keyed_per_account_not_global(self):
        make_account(business_name="Other Co", email="other@example.com")
        for _ in range(settings.ACCOUNT_LOCKOUT_THRESHOLD):
            self._fail_login()

        response = self.client.post(self.login_url, {
            "username": "other@example.com",
            "password": "S3cur3Pass!",
        })
        self.assertRedirects(response, reverse("company_accounts:dashboard"))


class DashboardTest(TestCase):
    def setUp(self):
        self.account = make_account()
        self.dashboard_url = reverse("company_accounts:dashboard")

    def test_dashboard_not_accessible_without_login(self):
        response = self.client.get(self.dashboard_url)
        self.assertRedirects(response, f"{reverse('company_accounts:login')}?next={self.dashboard_url}")

    def test_dashboard_accessible_with_login(self):
        self.client.force_login(self.account)
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, 200)

    def test_dashboard_shows_company_data(self):
        self.client.force_login(self.account)
        response = self.client.get(self.dashboard_url)
        self.assertContains(response, self.account.business_name)
        self.assertContains(response, self.account.slug)


class RegistrationAutoLoginTest(TestCase):
    def test_successful_registration_logs_user_in(self):
        url = reverse("company_accounts:register")
        response = self.client.post(url, {
            "business_name": "New Co",
            "email": "new@example.com",
            "phone": "+41 79 123 45 67",
            "password1": "S3cur3Pass!",
            "password2": "S3cur3Pass!",
            "tos_accepted": "on",
            "captcha_0": "PASSED",
            "captcha_1": "PASSED",
        })
        self.assertRedirects(response, reverse("company_accounts:dashboard"))
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_failed_registration_does_not_log_user_in(self):
        url = reverse("company_accounts:register")
        response = self.client.post(url, {
            "business_name": "New Co",
            "email": "new@example.com",
            "password1": "S3cur3Pass!",
            "password2": "wrong",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)


class PasswordResetFlowTest(TestCase):
    def setUp(self):
        self.account = make_account()
        self.reset_url = reverse("company_accounts:password_reset")

    def test_reset_page_renders(self):
        response = self.client.get(self.reset_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "company_accounts/password_reset.html")

    def test_valid_email_sends_reset_email(self):
        self.client.post(self.reset_url, {"email": self.account.email})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.account.email, mail.outbox[0].to)

    def test_unknown_email_sends_no_email(self):
        self.client.post(self.reset_url, {"email": "nobody@example.com"})
        self.assertEqual(len(mail.outbox), 0)

    def test_valid_email_redirects_to_done_page(self):
        response = self.client.post(self.reset_url, {"email": self.account.email})
        self.assertRedirects(response, reverse("company_accounts:password_reset_done"))

    def test_done_page_renders(self):
        response = self.client.get(reverse("company_accounts:password_reset_done"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "company_accounts/password_reset_done.html")

    def test_complete_page_renders(self):
        response = self.client.get(reverse("company_accounts:password_reset_complete"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "company_accounts/password_reset_complete.html")

    def test_login_page_has_forgot_password_link(self):
        response = self.client.get(reverse("company_accounts:login"))
        self.assertContains(response, reverse("company_accounts:password_reset"))


class CompanySettingsTest(TestCase):
    def setUp(self):
        self.account = make_account()
        self.settings_url = reverse("company_accounts:settings")

    # 1. Settings page requires login
    def test_settings_requires_login(self):
        response = self.client.get(self.settings_url)
        self.assertRedirects(
            response,
            f"{reverse('company_accounts:login')}?next={self.settings_url}",
        )

    # 2. Logged-in company can access settings page
    def test_settings_accessible_when_logged_in(self):
        self.client.force_login(self.account)
        response = self.client.get(self.settings_url)
        self.assertEqual(response.status_code, 200)

    # 3. Settings page shows current business name
    def test_settings_shows_business_name(self):
        self.client.force_login(self.account)
        response = self.client.get(self.settings_url)
        self.assertContains(response, self.account.business_name)

    # 4. Settings page shows public booking link
    def test_settings_shows_public_booking_link(self):
        self.client.force_login(self.account)
        response = self.client.get(self.settings_url)
        self.assertContains(response, f"/b/{self.account.slug}/")

    # 5. Settings page shows account email as read-only (not in a form field)
    def test_settings_shows_account_email_readonly(self):
        self.client.force_login(self.account)
        response = self.client.get(self.settings_url)
        self.assertContains(response, self.account.email)
        # email must not appear as a form input
        self.assertNotContains(response, f'name="email"')

    # 6. Company can update business name
    def test_can_update_business_name(self):
        self.client.force_login(self.account)
        self.client.post(self.settings_url, {
            "business_name": "New Name Ltd",
            "public_page_enabled": "on",
            "timezone": "Europe/Zurich",
            "show_staff_names_publicly": "on",
            "enable_any_employee_option": "on",
            "booking_confirmation_mode": "automatic",
        })
        self.account.refresh_from_db()
        self.assertEqual(self.account.business_name, "New Name Ltd")

    # 7. Company can update public_page_enabled
    def test_can_update_public_page_enabled(self):
        self.client.force_login(self.account)
        self.client.post(self.settings_url, {
            "business_name": self.account.business_name,
            "timezone": "Europe/Zurich",
            "booking_confirmation_mode": "automatic",
            # omitting public_page_enabled = unchecked = False
        })
        self.account.refresh_from_db()
        self.assertFalse(self.account.public_page_enabled)

    # 9. Business name is required
    def test_business_name_required(self):
        self.client.force_login(self.account)
        response = self.client.post(self.settings_url, {
            "business_name": "",
            "public_page_enabled": "on",
            "timezone": "Europe/Zurich",
        })
        self.assertEqual(response.status_code, 200)
        # Company language defaults to German, so the error message is translated.
        self.assertFormError(response.context["form"], "business_name", "Firmenname ist erforderlich.")
        self.account.refresh_from_db()
        self.assertEqual(self.account.business_name, "Acme AG")

    # 11. Email cannot be changed through settings POST
    def test_email_cannot_be_changed(self):
        self.client.force_login(self.account)
        self.client.post(self.settings_url, {
            "business_name": self.account.business_name,
            "public_page_enabled": "on",
            "timezone": "Europe/Zurich",
            "email": "hacker@evil.com",
        })
        self.account.refresh_from_db()
        self.assertEqual(self.account.email, "acme@example.com")

    # 12. Slug cannot be changed through settings POST
    def test_slug_cannot_be_changed(self):
        original_slug = self.account.slug
        self.client.force_login(self.account)
        self.client.post(self.settings_url, {
            "business_name": self.account.business_name,
            "public_page_enabled": "on",
            "timezone": "Europe/Zurich",
            "slug": "injected-slug",
        })
        self.account.refresh_from_db()
        self.assertEqual(self.account.slug, original_slug)

    # 13. Password cannot be changed through settings POST
    def test_password_cannot_be_changed(self):
        self.client.force_login(self.account)
        self.client.post(self.settings_url, {
            "business_name": self.account.business_name,
            "public_page_enabled": "on",
            "timezone": "Europe/Zurich",
            "password": "newpassword123",
        })
        self.account.refresh_from_db()
        self.assertTrue(self.account.check_password("S3cur3Pass!"))

    # 14. Public booking page respects updated public_page_enabled
    def test_booking_page_respects_public_page_enabled(self):
        self.client.force_login(self.account)
        self.client.post(self.settings_url, {
            "business_name": self.account.business_name,
            "timezone": "Europe/Zurich",
            "booking_confirmation_mode": "automatic",
            # public_page_enabled omitted → False
        })
        self.account.refresh_from_db()
        self.assertFalse(self.account.public_page_enabled)
        # Now access the public booking page as an unauthenticated visitor
        self.client.logout()
        response = self.client.get(
            reverse("bookings:entry", kwargs={"company_slug": self.account.slug})
        )
        # Should not redirect to a staff or service page; should show unavailable
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "bookings/public_unavailable.html")

    # 15. Company can disable Any Employee option
    def test_can_disable_any_employee_option(self):
        self.client.force_login(self.account)
        self.client.post(self.settings_url, {
            "business_name": self.account.business_name,
            "public_page_enabled": "on",
            "timezone": "Europe/Zurich",
            "show_staff_names_publicly": "on",
            "booking_confirmation_mode": "automatic",
            # enable_any_employee_option omitted → False
        })
        self.account.refresh_from_db()
        self.assertFalse(self.account.enable_any_employee_option)

    # 16. Public booking page hides Any Employee when disabled
    def test_any_employee_option_hidden_when_disabled(self):
        self.account.enable_any_employee_option = False
        self.account.save(update_fields=["enable_any_employee_option"])
        # Need 2+ active staff for the staff select page to appear
        StaffMember.objects.create(company=self.account, name="Alice", is_active=True)
        StaffMember.objects.create(company=self.account, name="Bob", is_active=True)
        response = self.client.get(
            reverse("bookings:entry", kwargs={"company_slug": self.account.slug})
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Any Employee")

    # 16b. Any Employee routes return 404 when disabled
    def test_any_employee_routes_404_when_disabled(self):
        self.account.enable_any_employee_option = False
        self.account.save(update_fields=["enable_any_employee_option"])
        response = self.client.get(
            reverse("bookings:any_service_select", kwargs={"company_slug": self.account.slug})
        )
        self.assertEqual(response.status_code, 404)

    # 17. Company can hide staff names publicly
    def test_can_hide_staff_names_publicly(self):
        self.client.force_login(self.account)
        self.client.post(self.settings_url, {
            "business_name": self.account.business_name,
            "public_page_enabled": "on",
            "timezone": "Europe/Zurich",
            "enable_any_employee_option": "on",
            "booking_confirmation_mode": "automatic",
            # show_staff_names_publicly omitted → False
        })
        self.account.refresh_from_db()
        self.assertFalse(self.account.show_staff_names_publicly)

    # 18. Public slot pages hide staff names when disabled
    def test_public_slot_page_hides_staff_name_when_disabled(self):
        from datetime import timedelta
        from django.utils import timezone as dj_timezone
        from availability.models import AppointmentSlot
        from services.models import ServiceOffering, StaffServiceOffering

        self.account.show_staff_names_publicly = False
        self.account.save(update_fields=["show_staff_names_publicly"])

        staff = StaffMember.objects.create(company=self.account, name="Alice", is_active=True)
        service = ServiceOffering.objects.create(
            company=self.account, name="Haircut", duration_minutes=30, is_active=True
        )
        StaffServiceOffering.objects.create(staff_member=staff, service_offering=service, is_active=True)

        now = dj_timezone.now()
        AppointmentSlot.objects.create(
            company=self.account,
            staff_member=staff,
            start_at=now + timedelta(hours=2),
            end_at=now + timedelta(hours=6),
            status=AppointmentSlot.Status.AVAILABLE,
        )

        url = reverse(
            "bookings:slot_select",
            kwargs={
                "company_slug": self.account.slug,
                "staff_uid": staff.public_id,
                "service_uid": service.public_id,
            },
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Alice")


# ---------------------------------------------------------------------------
# Booking confirmation mode settings
# ---------------------------------------------------------------------------

class BookingConfirmationModeSettingsTests(TestCase):
    """Tests 1-5: settings page shows mode, accepts valid values, rejects invalid."""

    def setUp(self):
        self.company = make_account(email="bcsettings@example.com")
        self.settings_url = reverse("company_accounts:settings")

    def test_settings_page_shows_booking_confirmation_mode_field(self):
        self.client.force_login(self.company)
        response = self.client.get(self.settings_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "booking_confirmation_mode")

    def test_company_can_set_confirmation_mode_to_automatic(self):
        self.client.force_login(self.company)
        self.client.post(self.settings_url, {
            "business_name": self.company.business_name,
            "timezone": self.company.timezone,
            "public_page_enabled": "on",
            "show_staff_names_publicly": "on",
            "enable_any_employee_option": "on",
            "booking_confirmation_mode": "automatic",
        })
        self.company.refresh_from_db()
        self.assertEqual(self.company.booking_confirmation_mode, "automatic")

    def test_company_can_set_confirmation_mode_to_manual(self):
        self.client.force_login(self.company)
        self.client.post(self.settings_url, {
            "business_name": self.company.business_name,
            "timezone": self.company.timezone,
            "booking_confirmation_mode": "manual",
        })
        self.company.refresh_from_db()
        self.assertEqual(self.company.booking_confirmation_mode, "manual")

    def test_invalid_confirmation_mode_is_rejected(self):
        self.client.force_login(self.company)
        response = self.client.post(self.settings_url, {
            "business_name": self.company.business_name,
            "timezone": self.company.timezone,
            "booking_confirmation_mode": "hacked_value",
        })
        self.assertEqual(response.status_code, 200)
        self.company.refresh_from_db()
        self.assertNotEqual(self.company.booking_confirmation_mode, "hacked_value")

    def test_confirmation_mode_cannot_be_changed_for_another_company(self):
        other = make_account(email="bcsettings_other@example.com", business_name="Other Co")
        self.client.force_login(self.company)
        # Even if POST somehow includes another company's PK, only self.company is edited.
        self.client.post(self.settings_url, {
            "business_name": self.company.business_name,
            "timezone": self.company.timezone,
            "booking_confirmation_mode": "manual",
        })
        other.refresh_from_db()
        # other's mode must not have changed
        self.assertEqual(other.booking_confirmation_mode, "automatic")


class SlotIntervalSettingsTests(TestCase):
    """Company-configurable slot interval: default 15 min, min 5, max 120."""

    def setUp(self):
        self.company = make_account(email="slotinterval@example.com")
        self.settings_url = reverse("company_accounts:settings")

    def test_default_slot_interval_is_15_minutes(self):
        self.assertEqual(self.company.slot_interval_minutes, 15)

    def test_settings_page_shows_slot_interval_field(self):
        self.client.force_login(self.company)
        response = self.client.get(self.settings_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "slot_interval_minutes")

    def test_company_can_set_valid_slot_interval(self):
        self.client.force_login(self.company)
        self.client.post(self.settings_url, {
            "business_name": self.company.business_name,
            "timezone": self.company.timezone,
            "booking_confirmation_mode": "automatic",
            "slot_interval_minutes": "30",
        })
        self.company.refresh_from_db()
        self.assertEqual(self.company.slot_interval_minutes, 30)

    def test_slot_interval_below_minimum_is_rejected(self):
        self.client.force_login(self.company)
        response = self.client.post(self.settings_url, {
            "business_name": self.company.business_name,
            "timezone": self.company.timezone,
            "booking_confirmation_mode": "automatic",
            "slot_interval_minutes": "4",
        })
        self.assertEqual(response.status_code, 200)
        self.company.refresh_from_db()
        self.assertEqual(self.company.slot_interval_minutes, 15)

    def test_slot_interval_above_maximum_is_rejected(self):
        self.client.force_login(self.company)
        response = self.client.post(self.settings_url, {
            "business_name": self.company.business_name,
            "timezone": self.company.timezone,
            "booking_confirmation_mode": "automatic",
            "slot_interval_minutes": "121",
        })
        self.assertEqual(response.status_code, 200)
        self.company.refresh_from_db()
        self.assertEqual(self.company.slot_interval_minutes, 15)

    def test_omitted_slot_interval_keeps_current_value(self):
        self.company.slot_interval_minutes = 20
        self.company.save()
        self.client.force_login(self.company)
        self.client.post(self.settings_url, {
            "business_name": self.company.business_name,
            "timezone": self.company.timezone,
            "booking_confirmation_mode": "automatic",
        })
        self.company.refresh_from_db()
        self.assertEqual(self.company.slot_interval_minutes, 20)


# ---------------------------------------------------------------------------
# i18n: company settings (interface language)
# ---------------------------------------------------------------------------

class CompanyLanguageSettingsTests(TestCase):
    def setUp(self):
        self.company = make_account(email="lang@example.com", business_name="Lang Co")
        self.settings_url = reverse("company_accounts:settings")

    def test_new_company_defaults_to_german(self):
        self.assertEqual(self.company.language, CompanyAccount.Language.GERMAN)

    def test_settings_page_shows_language_field_with_all_choices(self):
        self.client.force_login(self.company)
        response = self.client.get(self.settings_url)
        self.assertEqual(response.status_code, 200)
        for code, _label in CompanyAccount.Language.choices:
            self.assertContains(response, f'value="{code}"')

    def test_company_can_update_language(self):
        self.client.force_login(self.company)
        self.client.post(self.settings_url, {
            "business_name": self.company.business_name,
            "timezone": self.company.timezone,
            "booking_confirmation_mode": "automatic",
            "language": "fr",
        })
        self.company.refresh_from_db()
        self.assertEqual(self.company.language, "fr")

    def test_invalid_language_code_rejected(self):
        self.client.force_login(self.company)
        response = self.client.post(self.settings_url, {
            "business_name": self.company.business_name,
            "timezone": self.company.timezone,
            "booking_confirmation_mode": "automatic",
            "language": "xx",
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors.get("language"))
        self.company.refresh_from_db()
        self.assertEqual(self.company.language, "de")

    def test_language_update_does_not_affect_other_company(self):
        other = make_account(email="lang_other@example.com", business_name="Other Lang Co")
        self.client.force_login(self.company)
        self.client.post(self.settings_url, {
            "business_name": self.company.business_name,
            "timezone": self.company.timezone,
            "booking_confirmation_mode": "automatic",
            "language": "it",
        })
        other.refresh_from_db()
        self.assertEqual(other.language, "de")

    def test_settings_page_renders_in_updated_language(self):
        self.company.language = "fr"
        self.company.save(update_fields=["language"])
        self.client.force_login(self.company)
        response = self.client.get(self.settings_url)
        self.assertContains(response, "Paramètres")


# ---------------------------------------------------------------------------
# i18n: authenticated interface
# ---------------------------------------------------------------------------

class AuthenticatedInterfaceLanguageTests(TestCase):
    def setUp(self):
        self.dashboard_url = reverse("company_accounts:dashboard")

    def test_dashboard_renders_in_german_by_default(self):
        company = make_account(email="de_dash@example.com", business_name="DE Co")
        self.client.force_login(company)
        response = self.client.get(self.dashboard_url)
        self.assertContains(response, "Übersicht")

    def test_dashboard_renders_in_french_when_company_language_fr(self):
        company = make_account(email="fr_dash@example.com", business_name="FR Co")
        company.language = "fr"
        company.save(update_fields=["language"])
        self.client.force_login(company)
        response = self.client.get(self.dashboard_url)
        self.assertContains(response, "Tableau de bord")

    def test_dashboard_renders_in_italian_when_company_language_it(self):
        company = make_account(email="it_dash@example.com", business_name="IT Co")
        company.language = "it"
        company.save(update_fields=["language"])
        self.client.force_login(company)
        response = self.client.get(self.dashboard_url)
        self.assertContains(response, "Pannello di controllo")

    def test_pending_bookings_page_respects_company_language(self):
        company = make_account(email="fr_pending@example.com", business_name="FR Pending Co")
        company.language = "fr"
        company.save(update_fields=["language"])
        self.client.force_login(company)
        response = self.client.get(reverse("bookings:pending_bookings"))
        self.assertContains(response, "Aucune demande de réservation en attente pour le moment.")

    def test_all_bookings_page_respects_company_language(self):
        company = make_account(email="it_all@example.com", business_name="IT All Co")
        company.language = "it"
        company.save(update_fields=["language"])
        self.client.force_login(company)
        response = self.client.get(reverse("bookings:all_bookings"))
        self.assertContains(response, "Nessuna prenotazione in arrivo.")

    def test_business_name_not_translated_regardless_of_language(self):
        company = make_account(email="fr_name@example.com", business_name="Le Salon de Coiffure")
        company.language = "fr"
        company.save(update_fields=["language"])
        self.client.force_login(company)
        response = self.client.get(self.dashboard_url)
        self.assertContains(response, "Le Salon de Coiffure")


# ---------------------------------------------------------------------------
# Two-factor authentication
# ---------------------------------------------------------------------------

class TwoFactorSetupTests(TestCase):
    def setUp(self):
        self.account = make_account(email="2fa_setup@example.com")
        self.setup_url = reverse("company_accounts:two_factor_setup")
        self.status_url = reverse("company_accounts:two_factor_status")
        self.client.force_login(self.account)

    def test_setup_requires_login(self):
        self.client.logout()
        response = self.client.get(self.setup_url)
        self.assertRedirects(response, f"{reverse('company_accounts:login')}?next={self.setup_url}")

    def test_status_page_shows_disabled_by_default(self):
        response = self.client.get(self.status_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Deaktiviert")

    def test_get_setup_page_creates_unconfirmed_device_with_qr_and_secret(self):
        response = self.client.get(self.setup_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data:image/png;base64,")
        device = TOTPDevice.objects.get(user=self.account, confirmed=False)
        self.assertContains(response, response.context["secret"])
        self.assertEqual(response.context["secret"].replace(" ", ""), self._b32_secret(device))

    def _b32_secret(self, device):
        import base64
        return base64.b32encode(device.bin_key).decode("ascii")

    def test_revisiting_setup_page_replaces_unconfirmed_device(self):
        self.client.get(self.setup_url)
        first = TOTPDevice.objects.get(user=self.account, confirmed=False)
        self.client.get(self.setup_url)
        self.assertEqual(TOTPDevice.objects.filter(user=self.account, confirmed=False).count(), 1)
        second = TOTPDevice.objects.get(user=self.account, confirmed=False)
        self.assertNotEqual(first.pk, second.pk)

    def test_wrong_code_does_not_enable_2fa(self):
        self.client.get(self.setup_url)
        response = self.client.post(self.setup_url, {"token": "000000"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(TOTPDevice.objects.filter(user=self.account, confirmed=True).exists())

    def test_correct_code_enables_2fa_and_shows_backup_codes(self):
        self.client.get(self.setup_url)
        device = TOTPDevice.objects.get(user=self.account, confirmed=False)
        token = current_totp_token(device)
        response = self.client.post(self.setup_url, {"token": token})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "company_accounts/two_factor_backup_codes.html")
        self.assertTrue(TOTPDevice.objects.filter(user=self.account, confirmed=True).exists())
        codes = response.context["codes"]
        self.assertEqual(len(codes), settings.TWO_FACTOR_BACKUP_CODE_COUNT)
        self.assertEqual(StaticToken.objects.filter(device__user=self.account).count(), len(codes))

    def test_setup_redirects_when_already_enabled(self):
        self._enable_2fa()
        response = self.client.get(self.setup_url)
        self.assertRedirects(response, self.status_url)

    def _enable_2fa(self):
        self.client.get(self.setup_url)
        device = TOTPDevice.objects.get(user=self.account, confirmed=False)
        token = current_totp_token(device)
        self.client.post(self.setup_url, {"token": token})
        device.refresh_from_db()
        return device


class TwoFactorLoginTests(TestCase):
    def setUp(self):
        cache.clear()
        self.account = make_account(email="2fa_login@example.com")
        self.login_url = reverse("company_accounts:login")
        self.verify_url = reverse("company_accounts:two_factor_verify")
        self.dashboard_url = reverse("company_accounts:dashboard")
        self.device = TOTPDevice.objects.create(user=self.account, confirmed=True, name="default")

    def test_login_with_2fa_enabled_does_not_log_in_immediately(self):
        response = self.client.post(self.login_url, {
            "username": self.account.email,
            "password": "S3cur3Pass!",
        })
        self.assertRedirects(response, self.verify_url)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_wrong_password_does_not_reach_verify_step(self):
        response = self.client.post(self.login_url, {
            "username": self.account.email,
            "password": "wrongpassword",
        })
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("2fa_user_id", self.client.session)

    def test_verify_page_inaccessible_without_pending_login(self):
        response = self.client.get(self.verify_url)
        self.assertRedirects(response, self.login_url)

    def test_wrong_totp_code_does_not_log_in(self):
        self.client.post(self.login_url, {
            "username": self.account.email,
            "password": "S3cur3Pass!",
        })
        response = self.client.post(self.verify_url, {"token": "000000"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_correct_totp_code_logs_in(self):
        self.client.post(self.login_url, {
            "username": self.account.email,
            "password": "S3cur3Pass!",
        })
        token = current_totp_token(self.device)
        response = self.client.post(self.verify_url, {"token": token})
        self.assertRedirects(response, self.dashboard_url)
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_backup_code_logs_in_and_is_single_use(self):
        static_device = StaticDevice.objects.create(user=self.account, name="backup", confirmed=True)
        token = StaticToken.objects.create(device=static_device, token="abcd1234").token

        self.client.post(self.login_url, {"username": self.account.email, "password": "S3cur3Pass!"})
        response = self.client.post(self.verify_url, {"token": token})
        self.assertRedirects(response, self.dashboard_url)
        self.assertTrue(response.wsgi_request.user.is_authenticated)

        self.client.logout()
        self.client.post(self.login_url, {"username": self.account.email, "password": "S3cur3Pass!"})
        response = self.client.post(self.verify_url, {"token": token})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_next_param_preserved_through_2fa_verification(self):
        settings_url = reverse("company_accounts:settings")
        self.client.post(self.login_url, {
            "username": self.account.email,
            "password": "S3cur3Pass!",
            "next": settings_url,
        })
        token = current_totp_token(self.device)
        response = self.client.post(self.verify_url, {"token": token})
        self.assertRedirects(response, settings_url)

    def test_cancel_clears_pending_login_state(self):
        self.client.post(self.login_url, {
            "username": self.account.email,
            "password": "S3cur3Pass!",
        })
        self.assertIn("2fa_user_id", self.client.session)
        self.client.post(reverse("company_accounts:two_factor_cancel"))
        self.assertNotIn("2fa_user_id", self.client.session)

    def test_expired_pending_login_redirects_to_login_with_message(self):
        from datetime import timedelta
        from django.utils import timezone as dj_timezone

        self.client.post(self.login_url, {
            "username": self.account.email,
            "password": "S3cur3Pass!",
        })
        session = self.client.session
        session["2fa_started_at"] = (dj_timezone.now() - timedelta(minutes=11)).isoformat()
        session.save()
        response = self.client.get(self.verify_url, follow=True)
        self.assertRedirects(response, self.login_url)
        self.assertNotIn("2fa_user_id", self.client.session)


class TwoFactorManagementTests(TestCase):
    def setUp(self):
        self.account = make_account(email="2fa_manage@example.com")
        self.status_url = reverse("company_accounts:two_factor_status")
        self.disable_url = reverse("company_accounts:two_factor_disable")
        self.regen_url = reverse("company_accounts:two_factor_regenerate_backup_codes")
        self.client.force_login(self.account)
        self.device = TOTPDevice.objects.create(user=self.account, confirmed=True, name="default")
        from company_accounts.two_factor import issue_backup_codes
        issue_backup_codes(self.account)

    def test_status_page_shows_enabled_and_backup_code_count(self):
        response = self.client.get(self.status_url)
        self.assertContains(response, "Aktiviert")
        self.assertEqual(response.context["backup_codes_remaining"], settings.TWO_FACTOR_BACKUP_CODE_COUNT)

    def test_disable_with_wrong_password_does_not_disable(self):
        self.client.post(self.disable_url, {"password": "wrongpassword"})
        self.assertTrue(TOTPDevice.objects.filter(user=self.account, confirmed=True).exists())

    def test_disable_with_correct_password_removes_all_devices(self):
        self.client.post(self.disable_url, {"password": "S3cur3Pass!"})
        self.assertFalse(TOTPDevice.objects.filter(user=self.account).exists())
        self.assertFalse(StaticDevice.objects.filter(user=self.account).exists())

    def test_regenerate_with_wrong_password_keeps_old_codes(self):
        old_tokens = set(StaticToken.objects.filter(device__user=self.account).values_list("token", flat=True))
        self.client.post(self.regen_url, {"password": "wrongpassword"})
        new_tokens = set(StaticToken.objects.filter(device__user=self.account).values_list("token", flat=True))
        self.assertEqual(old_tokens, new_tokens)

    def test_regenerate_with_correct_password_replaces_codes(self):
        old_tokens = set(StaticToken.objects.filter(device__user=self.account).values_list("token", flat=True))
        response = self.client.post(self.regen_url, {"password": "S3cur3Pass!"})
        self.assertTemplateUsed(response, "company_accounts/two_factor_backup_codes.html")
        new_tokens = set(response.context["codes"])
        self.assertEqual(len(new_tokens), settings.TWO_FACTOR_BACKUP_CODE_COUNT)
        self.assertTrue(old_tokens.isdisjoint(new_tokens) or len(old_tokens) == 0)
        stored_tokens = set(StaticToken.objects.filter(device__user=self.account).values_list("token", flat=True))
        self.assertEqual(stored_tokens, new_tokens)

    def test_other_company_devices_are_unaffected_by_disable(self):
        other = make_account(email="2fa_other@example.com")
        other_device = TOTPDevice.objects.create(user=other, confirmed=True, name="default")
        self.client.post(self.disable_url, {"password": "S3cur3Pass!"})
        self.assertTrue(TOTPDevice.objects.filter(pk=other_device.pk, confirmed=True).exists())


class SettingsPageTwoFactorLinkTests(TestCase):
    def test_settings_page_links_to_two_factor_management(self):
        account = make_account(email="2fa_settings_link@example.com")
        self.client.force_login(account)
        response = self.client.get(reverse("company_accounts:settings"))
        self.assertContains(response, reverse("company_accounts:two_factor_status"))


class AdminRequiresVerifiedOtpTests(TestCase):
    """Closes AUDIT.md 2.4: the admin (full PII access) requires a verified
    OTP device, independent of the optional 2FA setting for company logins."""

    def setUp(self):
        self.staff = CompanyAccount.objects.create_superuser(
            email="admin_2fa@example.com",
            password="S3cur3Pass!",
            business_name="Admin Co",
            tos_version=settings.CURRENT_TOS_VERSION,
        )
        self.login_url = reverse("admin:login")
        self.index_url = reverse("admin:index")

    def test_staff_without_device_cannot_log_in_via_admin(self):
        response = self.client.post(self.login_url, {
            "username": self.staff.email,
            "password": "S3cur3Pass!",
            "otp_device": "",
            "otp_token": "",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_staff_with_device_but_no_token_cannot_log_in_via_admin(self):
        TOTPDevice.objects.create(user=self.staff, confirmed=True, name="default")
        response = self.client.post(self.login_url, {
            "username": self.staff.email,
            "password": "S3cur3Pass!",
            "otp_device": "",
            "otp_token": "",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_staff_with_correct_password_and_otp_token_reaches_admin_index(self):
        device = TOTPDevice.objects.create(user=self.staff, confirmed=True, name="default")
        response = self.client.post(f"{self.login_url}?next={self.index_url}", {
            "username": self.staff.email,
            "password": "S3cur3Pass!",
            "otp_device": device.persistent_id,
            "otp_token": current_totp_token(device),
            "next": self.index_url,
        })
        self.assertRedirects(response, self.index_url)
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_force_login_without_otp_verification_cannot_reach_admin_index(self):
        TOTPDevice.objects.create(user=self.staff, confirmed=True, name="default")
        self.client.force_login(self.staff)
        response = self.client.get(self.index_url)
        self.assertNotEqual(response.status_code, 200)


class DeleteCompanyCommandTests(TestCase):
    """AUDIT.md 3.3 — --confirm-name allows non-interactive (cron/CI) use."""

    def setUp(self):
        mail.outbox = []
        self.account = make_account(business_name="Acme AG", email="acme@example.com")

    def test_dry_run_does_not_delete(self):
        call_command("delete_company", "--email", "acme@example.com", "--confirmed-by", "Tester", "--dry-run", stdout=StringIO())
        self.assertTrue(CompanyAccount.objects.filter(email="acme@example.com").exists())

    def test_confirm_name_flag_deletes_without_input(self):
        call_command(
            "delete_company",
            "--email", "acme@example.com",
            "--confirmed-by", "Tester",
            "--confirm-name", "Acme AG",
            stdout=StringIO(),
        )
        self.assertFalse(CompanyAccount.objects.filter(email="acme@example.com").exists())

    def test_wrong_confirm_name_aborts(self):
        with self.assertRaises(CommandError):
            call_command(
                "delete_company",
                "--email", "acme@example.com",
                "--confirmed-by", "Tester",
                "--confirm-name", "Wrong Name",
                stdout=StringIO(),
            )
        self.assertTrue(CompanyAccount.objects.filter(email="acme@example.com").exists())

    def test_deletion_writes_audit_log_and_sends_farewell_email(self):
        from .models import AccountDeletionLog
        call_command(
            "delete_company",
            "--email", "acme@example.com",
            "--confirmed-by", "Tester",
            "--confirm-name", "Acme AG",
            stdout=StringIO(),
        )
        self.assertTrue(AccountDeletionLog.objects.filter(business_name="Acme AG").exists())
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["acme@example.com"])


class PurgeDeletionLogsCommandTests(TestCase):
    def _make_log(self, business_name, executed_at):
        from .models import AccountDeletionLog
        log = AccountDeletionLog.objects.create(
            company_email_hash=AccountDeletionLog.hash_email(f"{business_name}@example.com"),
            business_name=business_name,
            deletion_token="tok",
            requested_at=executed_at,
            confirmed_by="Tester",
        )
        log.executed_at = executed_at
        log.save(update_fields=["executed_at"])
        return log

    def test_old_log_purged(self):
        old_cutoff = timezone.now().replace(year=timezone.now().year - settings.DELETION_LOG_RETENTION_YEARS - 1)
        self._make_log("Old Co", old_cutoff)
        call_command("purge_deletion_logs", stdout=StringIO())
        from .models import AccountDeletionLog
        self.assertFalse(AccountDeletionLog.objects.filter(business_name="Old Co").exists())

    def test_recent_log_kept(self):
        self._make_log("Recent Co", timezone.now())
        call_command("purge_deletion_logs", stdout=StringIO())
        from .models import AccountDeletionLog
        self.assertTrue(AccountDeletionLog.objects.filter(business_name="Recent Co").exists())

    def test_dry_run_does_not_purge(self):
        old_cutoff = timezone.now().replace(year=timezone.now().year - settings.DELETION_LOG_RETENTION_YEARS - 1)
        self._make_log("Old Co", old_cutoff)
        call_command("purge_deletion_logs", "--dry-run", stdout=StringIO())
        from .models import AccountDeletionLog
        self.assertTrue(AccountDeletionLog.objects.filter(business_name="Old Co").exists())
