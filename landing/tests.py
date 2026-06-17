from django.test import TestCase
from django.urls import reverse


class LandingPageTests(TestCase):
    def setUp(self):
        self.url = reverse("landing:home")
        self.response = self.client.get(self.url)

    def test_landing_page_returns_200(self):
        self.assertEqual(self.response.status_code, 200)

    def test_landing_page_contains_title(self):
        # Default interface language is German.
        self.assertContains(self.response, "Einfache Terminbuchung für Ihr Unternehmen")

    def test_landing_page_contains_register_link(self):
        self.assertContains(self.response, reverse("company_accounts:register"))

    def test_landing_page_contains_login_link(self):
        self.assertContains(self.response, reverse("company_accounts:login"))
