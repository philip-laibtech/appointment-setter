from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from .models import CompanyAccount


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
