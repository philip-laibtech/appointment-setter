from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import StaffMember

User = get_user_model()

LIST_URL = reverse("staff_members:list")
CREATE_URL = reverse("staff_members:create")


def _make_company(email, business_name="Test Co"):
    return User.objects.create_user(
        email=email,
        password="testpassword123",
        business_name=business_name,
    )


def _make_member(company, name="Alice", email="", phone="", is_active=True):
    return StaffMember.objects.create(
        company=company,
        name=name,
        email=email,
        phone=phone,
        is_active=is_active,
    )


class AuthRequiredTests(TestCase):
    def test_list_requires_login(self):
        response = self.client.get(LIST_URL)
        self.assertRedirects(response, f"/company-accounts/login/?next={LIST_URL}")

    def test_create_requires_login(self):
        response = self.client.get(CREATE_URL)
        self.assertRedirects(response, f"/company-accounts/login/?next={CREATE_URL}")

    def test_edit_requires_login(self):
        company = _make_company("owner@example.com")
        member = _make_member(company)
        url = reverse("staff_members:edit", args=[member.pk])
        response = self.client.get(url)
        self.assertRedirects(response, f"/company-accounts/login/?next={url}")

    def test_delete_requires_login(self):
        company = _make_company("owner2@example.com")
        member = _make_member(company)
        url = reverse("staff_members:delete", args=[member.pk])
        response = self.client.get(url)
        self.assertRedirects(response, f"/company-accounts/login/?next={url}")


class StaffListTests(TestCase):
    def setUp(self):
        self.company = _make_company("list@example.com")
        self.client.login(username="list@example.com", password="testpassword123")

    def test_shows_own_staff_only(self):
        other = _make_company("other@example.com")
        m1 = _make_member(self.company, "Alice")
        _make_member(other, "Eve")
        response = self.client.get(LIST_URL)
        self.assertEqual(response.status_code, 200)
        members = list(response.context["members"])
        self.assertIn(m1, members)
        self.assertEqual(len(members), 1)

    def test_shows_inactive_staff(self):
        _make_member(self.company, "Inactive", is_active=False)
        response = self.client.get(LIST_URL)
        self.assertEqual(len(list(response.context["members"])), 1)


class StaffCreateTests(TestCase):
    def setUp(self):
        self.company = _make_company("creator@example.com")
        self.client.login(username="creator@example.com", password="testpassword123")

    def test_create_with_required_fields(self):
        response = self.client.post(CREATE_URL, {"name": "Bob"})
        self.assertRedirects(response, LIST_URL)
        self.assertTrue(StaffMember.objects.filter(company=self.company, name="Bob").exists())

    def test_company_is_set_from_request_user(self):
        self.client.post(CREATE_URL, {"name": "Bob"})
        member = StaffMember.objects.get(company=self.company)
        self.assertEqual(member.company, self.company)

    def test_name_is_required(self):
        response = self.client.post(CREATE_URL, {"name": ""})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(StaffMember.objects.filter(company=self.company).exists())

    def test_create_with_optional_fields(self):
        self.client.post(CREATE_URL, {
            "name": "Carol",
            "email": "carol@example.com",
            "phone": "+41 79 123 45 67",
        })
        member = StaffMember.objects.get(company=self.company, name="Carol")
        self.assertEqual(member.email, "carol@example.com")
        self.assertEqual(member.phone, "+41 79 123 45 67")

    def test_name_is_stripped(self):
        self.client.post(CREATE_URL, {"name": "  Alice  "})
        member = StaffMember.objects.get(company=self.company)
        self.assertEqual(member.name, "Alice")

    def test_email_is_lowercased_and_stripped(self):
        self.client.post(CREATE_URL, {"name": "Dave", "email": " Dave@Example.COM "})
        member = StaffMember.objects.get(company=self.company, name="Dave")
        self.assertEqual(member.email, "dave@example.com")


class StaffEditTests(TestCase):
    def setUp(self):
        self.owner = _make_company("owner@example.com")
        self.other = _make_company("other@example.com")
        self.member = _make_member(self.owner, "Alice")
        self.edit_url = reverse("staff_members:edit", args=[self.member.pk])

    def test_owner_can_edit(self):
        self.client.login(username="owner@example.com", password="testpassword123")
        response = self.client.post(self.edit_url, {"name": "Alicia", "is_active": True})
        self.assertRedirects(response, LIST_URL)
        self.member.refresh_from_db()
        self.assertEqual(self.member.name, "Alicia")

    def test_other_company_gets_404(self):
        self.client.login(username="other@example.com", password="testpassword123")
        response = self.client.post(self.edit_url, {"name": "Hacked"})
        self.assertEqual(response.status_code, 404)
        self.member.refresh_from_db()
        self.assertEqual(self.member.name, "Alice")

    def test_edit_get_prefills_form(self):
        self.client.login(username="owner@example.com", password="testpassword123")
        response = self.client.get(self.edit_url)
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual(form.instance.name, "Alice")

    def test_can_deactivate_via_edit(self):
        self.client.login(username="owner@example.com", password="testpassword123")
        self.client.post(self.edit_url, {"name": "Alice"})
        self.member.refresh_from_db()
        self.assertFalse(self.member.is_active)


class StaffDeleteTests(TestCase):
    def setUp(self):
        self.owner = _make_company("owner@example.com")
        self.other = _make_company("other@example.com")
        self.member = _make_member(self.owner, "Alice")
        self.delete_url = reverse("staff_members:delete", args=[self.member.pk])

    def test_delete_requires_post(self):
        self.client.login(username="owner@example.com", password="testpassword123")
        response = self.client.get(self.delete_url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(StaffMember.objects.filter(pk=self.member.pk).exists())

    def test_owner_can_delete_member_without_slots(self):
        self.client.login(username="owner@example.com", password="testpassword123")
        response = self.client.post(self.delete_url)
        self.assertRedirects(response, LIST_URL)
        self.assertFalse(StaffMember.objects.filter(pk=self.member.pk).exists())

    def test_other_company_gets_404_on_delete(self):
        self.client.login(username="other@example.com", password="testpassword123")
        response = self.client.post(self.delete_url)
        self.assertEqual(response.status_code, 404)
        self.assertTrue(StaffMember.objects.filter(pk=self.member.pk).exists())

    def test_member_with_slots_is_deactivated_not_deleted(self):
        from availability.models import AppointmentSlot
        from django.utils import timezone
        from datetime import timedelta

        AppointmentSlot.objects.create(
            company=self.owner,
            staff_member=self.member,
            start_at=timezone.now() + timedelta(hours=1),
            end_at=timezone.now() + timedelta(hours=2),
        )
        self.client.login(username="owner@example.com", password="testpassword123")
        response = self.client.post(self.delete_url)
        self.assertRedirects(response, LIST_URL)
        self.member.refresh_from_db()
        self.assertTrue(StaffMember.objects.filter(pk=self.member.pk).exists())
        self.assertFalse(self.member.is_active)


class StaffModelTests(TestCase):
    def test_str_returns_name(self):
        company = _make_company("str@example.com")
        member = _make_member(company, "Zara")
        self.assertEqual(str(member), "Zara")

    def test_default_is_active(self):
        company = _make_company("active@example.com")
        member = StaffMember.objects.create(company=company, name="Test")
        self.assertTrue(member.is_active)
