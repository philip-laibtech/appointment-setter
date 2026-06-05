from django.contrib.auth.password_validation import validate_password
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from .models import CompanyAccount
from staff_members.models import StaffMember


def make_account(business_name="Acme AG", email="acme@example.com", password="S3cur3Pass!"):
    return CompanyAccount.objects.create_user(
        email=email,
        password=password,
        business_name=business_name,
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
        self.assertContains(response, self.account.email)
        self.assertContains(response, self.account.slug)


class RegistrationAutoLoginTest(TestCase):
    def test_successful_registration_logs_user_in(self):
        url = reverse("company_accounts:register")
        response = self.client.post(url, {
            "business_name": "New Co",
            "email": "new@example.com",
            "password1": "S3cur3Pass!",
            "password2": "S3cur3Pass!",
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
        self.assertFormError(response.context["form"], "business_name", "Business name is required.")
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
                "staff_id": staff.pk,
                "service_id": service.pk,
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
