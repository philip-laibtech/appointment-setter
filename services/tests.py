from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from staff_members.models import StaffMember

from .models import ServiceOffering, StaffServiceOffering

User = get_user_model()

LIST_URL = reverse("services:list")
CREATE_URL = reverse("services:create")


def _make_company(email, business_name="Test Co"):
    return User.objects.create_user(
        email=email,
        password="testpassword123",
        business_name=business_name,
    )


def _make_staff(company, name="Alice", is_active=True):
    return StaffMember.objects.create(company=company, name=name, is_active=is_active)


def _make_service(company, name="Consultation", duration=30, is_active=True):
    return ServiceOffering.objects.create(
        company=company,
        name=name,
        duration_minutes=duration,
        is_active=is_active,
    )


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------

class AccessControlTests(TestCase):
    def test_list_requires_login(self):
        response = self.client.get(LIST_URL)
        self.assertRedirects(response, f"/login/?next={LIST_URL}")

    def test_create_requires_login(self):
        response = self.client.get(CREATE_URL)
        self.assertRedirects(response, f"/login/?next={CREATE_URL}")

    def test_edit_requires_login(self):
        company = _make_company("owner@example.com")
        service = _make_service(company)
        url = reverse("services:edit", args=[service.pk])
        response = self.client.get(url)
        self.assertRedirects(response, f"/login/?next={url}")

    def test_delete_requires_login(self):
        company = _make_company("owner2@example.com")
        service = _make_service(company)
        url = reverse("services:delete", args=[service.pk])
        response = self.client.get(url)
        self.assertRedirects(response, f"/login/?next={url}")

    def test_cannot_access_another_companys_service_via_edit(self):
        owner = _make_company("owner@example.com")
        other = _make_company("other@example.com")
        service = _make_service(owner)
        url = reverse("services:edit", args=[service.pk])
        self.client.login(username="other@example.com", password="testpassword123")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_cannot_delete_another_companys_service(self):
        owner = _make_company("owner3@example.com")
        other = _make_company("other3@example.com")
        service = _make_service(owner)
        url = reverse("services:delete", args=[service.pk])
        self.client.login(username="other3@example.com", password="testpassword123")
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)
        self.assertTrue(ServiceOffering.objects.filter(pk=service.pk).exists())


# ---------------------------------------------------------------------------
# ServiceOffering — create
# ---------------------------------------------------------------------------

class ServiceCreateTests(TestCase):
    def setUp(self):
        self.company = _make_company("creator@example.com")
        self.client.login(username="creator@example.com", password="testpassword123")

    def test_create_sets_company_from_request_user(self):
        self.client.post(CREATE_URL, {"name": "Consult", "duration_minutes": 30})
        service = ServiceOffering.objects.get(company=self.company)
        self.assertEqual(service.company, self.company)

    def test_name_is_required(self):
        response = self.client.post(CREATE_URL, {"name": "", "duration_minutes": 30})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ServiceOffering.objects.filter(company=self.company).exists())

    def test_duration_is_required(self):
        response = self.client.post(CREATE_URL, {"name": "Consult"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ServiceOffering.objects.filter(company=self.company).exists())

    def test_duration_below_5_is_rejected(self):
        response = self.client.post(CREATE_URL, {"name": "Consult", "duration_minutes": 4})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ServiceOffering.objects.filter(company=self.company).exists())

    def test_duration_above_480_is_rejected(self):
        response = self.client.post(CREATE_URL, {"name": "Consult", "duration_minutes": 481})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ServiceOffering.objects.filter(company=self.company).exists())

    def test_duration_exactly_5_is_accepted(self):
        self.client.post(CREATE_URL, {"name": "Quick", "duration_minutes": 5})
        self.assertTrue(ServiceOffering.objects.filter(company=self.company, duration_minutes=5).exists())

    def test_duration_exactly_480_is_accepted(self):
        self.client.post(CREATE_URL, {"name": "Long", "duration_minutes": 480})
        self.assertTrue(ServiceOffering.objects.filter(company=self.company, duration_minutes=480).exists())

    def test_create_redirects_to_list(self):
        response = self.client.post(CREATE_URL, {"name": "Consult", "duration_minutes": 30})
        self.assertRedirects(response, LIST_URL)

    def test_create_with_zero_assigned_staff_is_valid(self):
        self.client.post(CREATE_URL, {"name": "Solo", "duration_minutes": 30})
        service = ServiceOffering.objects.get(company=self.company, name="Solo")
        self.assertEqual(StaffServiceOffering.objects.filter(service_offering=service).count(), 0)


# ---------------------------------------------------------------------------
# ServiceOffering — list scoping
# ---------------------------------------------------------------------------

class ServiceListTests(TestCase):
    def setUp(self):
        self.company = _make_company("list@example.com")
        self.client.login(username="list@example.com", password="testpassword123")

    def test_shows_own_services_only(self):
        other = _make_company("other@example.com")
        s1 = _make_service(self.company, "Consult")
        _make_service(other, "Other Service")
        response = self.client.get(LIST_URL)
        self.assertEqual(response.status_code, 200)
        services = list(response.context["services"])
        self.assertIn(s1, services)
        self.assertEqual(len(services), 1)


# ---------------------------------------------------------------------------
# ServiceOffering — edit and delete
# ---------------------------------------------------------------------------

class ServiceEditTests(TestCase):
    def setUp(self):
        self.owner = _make_company("owner@example.com")
        self.other = _make_company("other@example.com")
        self.service = _make_service(self.owner, "Consult")
        self.edit_url = reverse("services:edit", args=[self.service.pk])

    def test_owner_can_edit_service(self):
        self.client.login(username="owner@example.com", password="testpassword123")
        response = self.client.post(
            self.edit_url,
            {"name": "Updated Consult", "duration_minutes": 45, "is_active": True},
        )
        self.assertRedirects(response, LIST_URL)
        self.service.refresh_from_db()
        self.assertEqual(self.service.name, "Updated Consult")

    def test_other_company_gets_404_on_edit(self):
        self.client.login(username="other@example.com", password="testpassword123")
        response = self.client.post(
            self.edit_url,
            {"name": "Hacked", "duration_minutes": 30, "is_active": True},
        )
        self.assertEqual(response.status_code, 404)
        self.service.refresh_from_db()
        self.assertEqual(self.service.name, "Consult")


class ServiceDeleteTests(TestCase):
    def setUp(self):
        self.owner = _make_company("owner@example.com")
        self.service = _make_service(self.owner)
        self.delete_url = reverse("services:delete", args=[self.service.pk])

    def test_delete_get_shows_confirm_page(self):
        self.client.login(username="owner@example.com", password="testpassword123")
        response = self.client.get(self.delete_url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(ServiceOffering.objects.filter(pk=self.service.pk).exists())

    def test_post_hard_deletes_service(self):
        self.client.login(username="owner@example.com", password="testpassword123")
        response = self.client.post(self.delete_url)
        self.assertRedirects(response, LIST_URL)
        self.assertFalse(ServiceOffering.objects.filter(pk=self.service.pk).exists())


# ---------------------------------------------------------------------------
# Staff assignment
# ---------------------------------------------------------------------------

class StaffAssignmentTests(TestCase):
    def setUp(self):
        self.company = _make_company("assign@example.com")
        self.other = _make_company("other@example.com")
        self.staff1 = _make_staff(self.company, "Alice")
        self.staff2 = _make_staff(self.company, "Bob")
        self.inactive_staff = _make_staff(self.company, "Inactive", is_active=False)
        self.other_staff = _make_staff(self.other, "Eve")
        self.client.login(username="assign@example.com", password="testpassword123")

    def test_assign_single_staff_member(self):
        self.client.post(CREATE_URL, {
            "name": "Consult",
            "duration_minutes": 30,
            "assigned_staff_members": [self.staff1.pk],
        })
        service = ServiceOffering.objects.get(company=self.company, name="Consult")
        self.assertEqual(
            StaffServiceOffering.objects.filter(service_offering=service, is_active=True).count(), 1
        )

    def test_assign_multiple_staff_members(self):
        self.client.post(CREATE_URL, {
            "name": "Group",
            "duration_minutes": 60,
            "assigned_staff_members": [self.staff1.pk, self.staff2.pk],
        })
        service = ServiceOffering.objects.get(company=self.company, name="Group")
        self.assertEqual(
            StaffServiceOffering.objects.filter(service_offering=service, is_active=True).count(), 2
        )

    def test_cannot_assign_other_companys_staff(self):
        response = self.client.post(CREATE_URL, {
            "name": "Consult",
            "duration_minutes": 30,
            "assigned_staff_members": [self.other_staff.pk],
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ServiceOffering.objects.filter(company=self.company, name="Consult").exists())

    def test_inactive_staff_not_available_as_choice(self):
        self.client.get(CREATE_URL)
        response = self.client.get(CREATE_URL)
        form = response.context["form"]
        qs = form.fields["assigned_staff_members"].queryset
        self.assertNotIn(self.inactive_staff, qs)

    def test_inactive_staff_cannot_be_assigned_directly(self):
        response = self.client.post(CREATE_URL, {
            "name": "Consult",
            "duration_minutes": 30,
            "assigned_staff_members": [self.inactive_staff.pk],
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ServiceOffering.objects.filter(company=self.company, name="Consult").exists())

    def test_duplicate_assignment_is_prevented(self):
        service = _make_service(self.company, "Consult")
        StaffServiceOffering.objects.create(
            staff_member=self.staff1, service_offering=service
        )
        with self.assertRaises(Exception):
            StaffServiceOffering.objects.create(
                staff_member=self.staff1, service_offering=service
            )

    def test_edit_syncs_staff_assignments(self):
        service = _make_service(self.company, "Consult")
        StaffServiceOffering.objects.create(
            staff_member=self.staff1, service_offering=service, is_active=True
        )
        url = reverse("services:edit", args=[service.pk])
        self.client.post(url, {
            "name": "Consult",
            "duration_minutes": 30,
            "is_active": True,
            "assigned_staff_members": [self.staff2.pk],
        })
        self.assertFalse(
            StaffServiceOffering.objects.filter(
                staff_member=self.staff1, service_offering=service, is_active=True
            ).exists()
        )
        self.assertTrue(
            StaffServiceOffering.objects.filter(
                staff_member=self.staff2, service_offering=service, is_active=True
            ).exists()
        )

    def test_unselected_staff_are_deactivated_not_deleted(self):
        service = _make_service(self.company, "Consult")
        StaffServiceOffering.objects.create(
            staff_member=self.staff1, service_offering=service, is_active=True
        )
        url = reverse("services:edit", args=[service.pk])
        self.client.post(url, {
            "name": "Consult",
            "duration_minutes": 30,
            "is_active": True,
            "assigned_staff_members": [],
        })
        assignment = StaffServiceOffering.objects.get(
            staff_member=self.staff1, service_offering=service
        )
        self.assertFalse(assignment.is_active)

    def test_delete_service_also_deletes_assignments(self):
        service = _make_service(self.company, "Consult")
        assignment = StaffServiceOffering.objects.create(
            staff_member=self.staff1, service_offering=service, is_active=True
        )
        url = reverse("services:delete", args=[service.pk])
        self.client.post(url)
        self.assertFalse(StaffServiceOffering.objects.filter(pk=assignment.pk).exists())


# ---------------------------------------------------------------------------
# Model constraint — same company
# ---------------------------------------------------------------------------

class SameCompanyConstraintTests(TestCase):
    def test_clean_rejects_cross_company_assignment(self):
        from django.core.exceptions import ValidationError

        company_a = _make_company("a@example.com")
        company_b = _make_company("b@example.com")
        staff = _make_staff(company_a)
        service = _make_service(company_b)
        assignment = StaffServiceOffering(staff_member=staff, service_offering=service)
        with self.assertRaises(ValidationError):
            assignment.clean()

    def test_clean_accepts_same_company_assignment(self):
        from django.core.exceptions import ValidationError

        company = _make_company("same@example.com")
        staff = _make_staff(company)
        service = _make_service(company)
        assignment = StaffServiceOffering(staff_member=staff, service_offering=service)
        try:
            assignment.clean()
        except ValidationError:
            self.fail("clean() raised ValidationError for a valid same-company assignment.")
