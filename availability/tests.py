from datetime import date as _date, datetime as _datetime, time as _time, timedelta

from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from staff_members.models import StaffMember

from .admin import AppointmentSlotAdmin
from .models import AppointmentSlot

User = get_user_model()

LIST_URL = reverse("availability:list")
CREATE_URL = reverse("availability:create")


def _future(minutes=60):
    return timezone.now() + timedelta(minutes=minutes)


def _make_company(email, business_name="Test Co"):
    return User.objects.create_user(
        email=email,
        password="testpassword123",
        business_name=business_name,
    )


def _make_staff(company, name="Alice"):
    return StaffMember.objects.create(company=company, name=name)


def _form_data(start_dt, end_dt, staff_member):
    """Convert two datetime objects to the form POST dict."""
    return {
        "staff_member": staff_member.pk,
        "date": start_dt.strftime("%Y-%m-%d"),
        "start_time": start_dt.strftime("%H:%M"),
        "end_time": end_dt.strftime("%H:%M"),
    }


def _make_slot(company, staff_member=None, start_offset=60, end_offset=90,
               status=AppointmentSlot.Status.AVAILABLE):
    return AppointmentSlot.objects.create(
        company=company,
        staff_member=staff_member,
        start_at=timezone.now() + timedelta(minutes=start_offset),
        end_at=timezone.now() + timedelta(minutes=end_offset),
        status=status,
    )


class AuthRequiredTests(TestCase):
    def test_list_requires_login(self):
        response = self.client.get(LIST_URL)
        self.assertRedirects(response, f"/company-accounts/login/?next={LIST_URL}")

    def test_create_requires_login(self):
        response = self.client.get(CREATE_URL)
        self.assertRedirects(response, f"/company-accounts/login/?next={CREATE_URL}")

    def test_delete_requires_login(self):
        company = _make_company("owner@example.com")
        staff = _make_staff(company)
        slot = _make_slot(company, staff)
        delete_url = reverse("availability:delete", args=[slot.pk])
        response = self.client.get(delete_url)
        self.assertRedirects(response, f"/company-accounts/login/?next={delete_url}")


class OpenHoursCreateTests(TestCase):
    def setUp(self):
        self.company = _make_company("creator@example.com")
        self.staff = _make_staff(self.company)
        self.client.login(username="creator@example.com", password="testpassword123")

    def test_logged_in_can_create_valid_entry(self):
        start = _future(60)
        end = _future(90)
        response = self.client.post(CREATE_URL, _form_data(start, end, self.staff))
        self.assertRedirects(response, LIST_URL)
        self.assertEqual(AppointmentSlot.objects.filter(company=self.company).count(), 1)

    def test_entry_assigned_to_request_user(self):
        start = _future(60)
        end = _future(90)
        self.client.post(CREATE_URL, _form_data(start, end, self.staff))
        slot = AppointmentSlot.objects.get(company=self.company)
        self.assertEqual(slot.company, self.company)
        self.assertEqual(slot.staff_member, self.staff)

    def test_cannot_create_entry_in_past(self):
        past = timezone.now() - timedelta(minutes=30)
        end = timezone.now() + timedelta(minutes=30)
        response = self.client.post(CREATE_URL, _form_data(past, end, self.staff))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(AppointmentSlot.objects.filter(company=self.company).exists())

    def test_cannot_create_entry_end_before_start(self):
        start = _future(90)
        end = _future(60)
        response = self.client.post(CREATE_URL, _form_data(start, end, self.staff))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(AppointmentSlot.objects.filter(company=self.company).exists())

    def test_cannot_create_entry_shorter_than_5_minutes(self):
        start = _future(60)
        end = start + timedelta(minutes=4)
        response = self.client.post(CREATE_URL, _form_data(start, end, self.staff))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(AppointmentSlot.objects.filter(company=self.company).exists())

    def test_cannot_create_entry_longer_than_8_hours(self):
        start = _future(60)
        end = start + timedelta(hours=8, minutes=1)
        response = self.client.post(CREATE_URL, _form_data(start, end, self.staff))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(AppointmentSlot.objects.filter(company=self.company).exists())

    def test_cannot_create_overlapping_entry_same_staff(self):
        _make_slot(self.company, self.staff, start_offset=60, end_offset=120)
        start = _future(90)
        end = _future(150)
        response = self.client.post(CREATE_URL, _form_data(start, end, self.staff))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(AppointmentSlot.objects.filter(company=self.company).count(), 1)

    def test_overlapping_entry_different_staff_is_allowed(self):
        """Two staff members may have overlapping slots."""
        staff_b = _make_staff(self.company, name="Bob")
        _make_slot(self.company, self.staff, start_offset=60, end_offset=120)
        start = _future(90)
        end = _future(150)
        response = self.client.post(CREATE_URL, _form_data(start, end, staff_b))
        self.assertRedirects(response, LIST_URL)
        self.assertEqual(AppointmentSlot.objects.filter(company=self.company).count(), 2)

    def test_staff_from_other_company_rejected(self):
        other_company = _make_company("other@example.com")
        other_staff = _make_staff(other_company, name="Eve")
        start = _future(60)
        end = _future(90)
        response = self.client.post(CREATE_URL, _form_data(start, end, other_staff))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(AppointmentSlot.objects.filter(company=self.company).exists())

    def test_no_staff_member_is_invalid(self):
        start = _future(60)
        end = _future(90)
        data = {
            "date": start.strftime("%Y-%m-%d"),
            "start_time": start.strftime("%H:%M"),
            "end_time": end.strftime("%H:%M"),
        }
        response = self.client.post(CREATE_URL, data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(AppointmentSlot.objects.filter(company=self.company).exists())

    def test_single_staff_member_is_preselected(self):
        response = self.client.get(CREATE_URL)
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual(form.fields["staff_member"].initial, self.staff)


class OpenHoursListTests(TestCase):
    def test_company_sees_only_own_entries(self):
        company_a = _make_company("a@example.com")
        company_b = _make_company("b@example.com")
        staff_a = _make_staff(company_a)
        staff_b = _make_staff(company_b)
        slot_a = _make_slot(company_a, staff_a)
        _make_slot(company_b, staff_b)

        self.client.login(username="a@example.com", password="testpassword123")
        response = self.client.get(LIST_URL)
        self.assertEqual(response.status_code, 200)
        slots_in_context = list(response.context["slots"])
        self.assertIn(slot_a, slots_in_context)
        self.assertEqual(len(slots_in_context), 1)

    def test_filter_by_staff_member(self):
        company = _make_company("filter@example.com")
        staff_a = _make_staff(company, "Alice")
        staff_b = _make_staff(company, "Bob")
        slot_a = _make_slot(company, staff_a)
        _make_slot(company, staff_b)

        self.client.login(username="filter@example.com", password="testpassword123")
        response = self.client.get(LIST_URL + f"?staff={staff_a.pk}")
        self.assertEqual(response.status_code, 200)
        slots = list(response.context["slots"])
        self.assertEqual(slots, [slot_a])
        self.assertEqual(response.context["selected_staff"], staff_a)

    def test_invalid_staff_filter_shows_all(self):
        company = _make_company("filterall@example.com")
        staff = _make_staff(company)
        _make_slot(company, staff)

        self.client.login(username="filterall@example.com", password="testpassword123")
        response = self.client.get(LIST_URL + "?staff=99999")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(list(response.context["slots"])), 1)
        self.assertIsNone(response.context["selected_staff"])


class OpenHoursDeleteTests(TestCase):
    def setUp(self):
        self.owner = _make_company("owner@example.com")
        self.other = _make_company("other@example.com")
        self.staff = _make_staff(self.owner)
        self.slot = _make_slot(self.owner, self.staff)
        self.delete_url = reverse("availability:delete", args=[self.slot.pk])

    def test_owner_can_delete_own_entry(self):
        self.client.login(username="owner@example.com", password="testpassword123")
        response = self.client.post(self.delete_url)
        self.assertRedirects(response, LIST_URL)
        self.assertFalse(AppointmentSlot.objects.filter(pk=self.slot.pk).exists())

    def test_other_company_cannot_delete_entry(self):
        self.client.login(username="other@example.com", password="testpassword123")
        response = self.client.post(self.delete_url)
        self.assertEqual(response.status_code, 404)
        self.assertTrue(AppointmentSlot.objects.filter(pk=self.slot.pk).exists())

    def test_delete_requires_post(self):
        self.client.login(username="owner@example.com", password="testpassword123")
        response = self.client.get(self.delete_url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(AppointmentSlot.objects.filter(pk=self.slot.pk).exists())


class OpenHoursEditTests(TestCase):
    def setUp(self):
        self.owner = _make_company("owner@example.com")
        self.other = _make_company("other@example.com")
        self.staff = _make_staff(self.owner)
        self.slot = _make_slot(self.owner, self.staff, start_offset=120, end_offset=180)
        self.edit_url = reverse("availability:edit", args=[self.slot.pk])

    def test_edit_requires_login(self):
        response = self.client.get(self.edit_url)
        self.assertRedirects(response, f"/company-accounts/login/?next={self.edit_url}")

    def test_owner_can_edit_own_entry(self):
        self.client.login(username="owner@example.com", password="testpassword123")
        new_start = _future(240)
        new_end = _future(300)
        response = self.client.post(self.edit_url, _form_data(new_start, new_end, self.staff))
        self.assertRedirects(response, LIST_URL)
        self.slot.refresh_from_db()
        self.assertEqual(self.slot.start_at.strftime("%H:%M"), new_start.strftime("%H:%M"))
        self.assertEqual(self.slot.end_at.strftime("%H:%M"), new_end.strftime("%H:%M"))

    def test_other_company_cannot_edit_entry(self):
        self.client.login(username="other@example.com", password="testpassword123")
        other_staff = _make_staff(self.other, "Other")
        new_start = _future(240)
        new_end = _future(300)
        response = self.client.post(self.edit_url, _form_data(new_start, new_end, other_staff))
        self.assertEqual(response.status_code, 404)

    def test_edit_get_prefills_form(self):
        self.client.login(username="owner@example.com", password="testpassword123")
        response = self.client.get(self.edit_url)
        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertEqual(form.initial["date"], self.slot.start_at.strftime("%Y-%m-%d"))
        self.assertEqual(form.initial["staff_member"], self.staff.pk)

    def test_saving_unchanged_times_does_not_trigger_overlap(self):
        """Re-saving a slot with its own existing times must not fail with an overlap error."""
        self.client.login(username="owner@example.com", password="testpassword123")
        same_start = self.slot.start_at
        same_end = self.slot.end_at
        response = self.client.post(self.edit_url, _form_data(same_start, same_end, self.staff))
        self.assertRedirects(response, LIST_URL)

    def test_edit_overlap_still_blocked_against_other_slots_same_staff(self):
        _make_slot(self.owner, self.staff, start_offset=300, end_offset=360)
        self.client.login(username="owner@example.com", password="testpassword123")
        overlap_start = _future(330)
        overlap_end = _future(390)
        response = self.client.post(self.edit_url, _form_data(overlap_start, overlap_end, self.staff))
        self.assertEqual(response.status_code, 200)


RECURRING_URL = reverse("availability:create_recurring")


def _next_weekday(n):
    """Return the next calendar date that falls on weekday n (0=Mon), never today."""
    today = timezone.now().date()
    days_ahead = (n - today.weekday()) % 7 or 7
    return today + timedelta(days=days_ahead)


def _recurring_data(weekdays, start_time, end_time, date_from, date_until, staff_member):
    return {
        "staff_member": staff_member.pk,
        "weekdays": weekdays,
        "start_time": start_time,
        "end_time": end_time,
        "date_from": date_from.isoformat(),
        "date_until": date_until.isoformat(),
    }


class RecurringCreateTests(TestCase):
    def setUp(self):
        self.company = _make_company("recurring@example.com")
        self.staff = _make_staff(self.company)
        self.client.login(username="recurring@example.com", password="testpassword123")

    def test_recurring_requires_login(self):
        self.client.logout()
        response = self.client.get(RECURRING_URL)
        self.assertRedirects(response, f"/company-accounts/login/?next={RECURRING_URL}")

    def test_creates_correct_number_of_slots(self):
        monday = _next_weekday(0)
        response = self.client.post(RECURRING_URL, _recurring_data(
            weekdays=["0"],
            start_time="09:00",
            end_time="10:00",
            date_from=monday,
            date_until=monday + timedelta(days=14),
            staff_member=self.staff,
        ))
        self.assertRedirects(response, LIST_URL)
        self.assertEqual(AppointmentSlot.objects.filter(company=self.company).count(), 3)

    def test_slots_assigned_to_request_user_and_staff(self):
        monday = _next_weekday(0)
        self.client.post(RECURRING_URL, _recurring_data(
            weekdays=["0"],
            start_time="09:00",
            end_time="10:00",
            date_from=monday,
            date_until=monday,
            staff_member=self.staff,
        ))
        slot = AppointmentSlot.objects.get(company=self.company)
        self.assertEqual(slot.company, self.company)
        self.assertEqual(slot.staff_member, self.staff)

    def test_only_selected_weekdays_are_created(self):
        next_mon = _next_weekday(0)
        next_sun = next_mon + timedelta(days=6)
        self.client.post(RECURRING_URL, _recurring_data(
            weekdays=["2"],
            start_time="09:00",
            end_time="10:00",
            date_from=next_mon,
            date_until=next_sun,
            staff_member=self.staff,
        ))
        slots = AppointmentSlot.objects.filter(company=self.company)
        self.assertEqual(slots.count(), 1)
        self.assertEqual(slots.first().start_at.weekday(), 2)

    def test_multiple_weekdays_are_all_created(self):
        next_mon = _next_weekday(0)
        next_sun = next_mon + timedelta(days=6)
        self.client.post(RECURRING_URL, _recurring_data(
            weekdays=["0", "2", "4"],
            start_time="09:00",
            end_time="10:00",
            date_from=next_mon,
            date_until=next_sun,
            staff_member=self.staff,
        ))
        self.assertEqual(AppointmentSlot.objects.filter(company=self.company).count(), 3)

    def test_overlapping_slots_same_staff_are_skipped(self):
        monday = _next_weekday(0)
        AppointmentSlot.objects.create(
            company=self.company,
            staff_member=self.staff,
            start_at=timezone.make_aware(_datetime.combine(monday, _time(9, 0))),
            end_at=timezone.make_aware(_datetime.combine(monday, _time(10, 0))),
        )
        response = self.client.post(RECURRING_URL, _recurring_data(
            weekdays=["0"],
            start_time="09:00",
            end_time="10:00",
            date_from=monday,
            date_until=monday,
            staff_member=self.staff,
        ))
        self.assertRedirects(response, LIST_URL)
        self.assertEqual(AppointmentSlot.objects.filter(company=self.company).count(), 1)

    def test_overlapping_slots_different_staff_are_not_skipped(self):
        monday = _next_weekday(0)
        staff_b = _make_staff(self.company, "Bob")
        AppointmentSlot.objects.create(
            company=self.company,
            staff_member=self.staff,
            start_at=timezone.make_aware(_datetime.combine(monday, _time(9, 0))),
            end_at=timezone.make_aware(_datetime.combine(monday, _time(10, 0))),
        )
        self.client.post(RECURRING_URL, _recurring_data(
            weekdays=["0"],
            start_time="09:00",
            end_time="10:00",
            date_from=monday,
            date_until=monday,
            staff_member=staff_b,
        ))
        self.assertEqual(AppointmentSlot.objects.filter(company=self.company).count(), 2)

    def test_no_weekday_selected_is_invalid(self):
        monday = _next_weekday(0)
        response = self.client.post(RECURRING_URL, {
            "staff_member": self.staff.pk,
            "start_time": "09:00",
            "end_time": "10:00",
            "date_from": monday.isoformat(),
            "date_until": (monday + timedelta(days=7)).isoformat(),
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(AppointmentSlot.objects.filter(company=self.company).exists())

    def test_end_time_before_start_time_is_invalid(self):
        monday = _next_weekday(0)
        response = self.client.post(RECURRING_URL, _recurring_data(
            weekdays=["0"],
            start_time="10:00",
            end_time="09:00",
            date_from=monday,
            date_until=monday + timedelta(days=7),
            staff_member=self.staff,
        ))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(AppointmentSlot.objects.filter(company=self.company).exists())

    def test_date_until_beyond_one_year_is_invalid(self):
        today = timezone.now().date()
        over_limit = today + timedelta(days=366)
        monday = _next_weekday(0)
        response = self.client.post(RECURRING_URL, _recurring_data(
            weekdays=["0"],
            start_time="09:00",
            end_time="10:00",
            date_from=monday,
            date_until=over_limit,
            staff_member=self.staff,
        ))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(AppointmentSlot.objects.filter(company=self.company).exists())

    def test_date_until_before_date_from_is_invalid(self):
        monday = _next_weekday(0)
        response = self.client.post(RECURRING_URL, _recurring_data(
            weekdays=["0"],
            start_time="09:00",
            end_time="10:00",
            date_from=monday + timedelta(days=7),
            date_until=monday,
            staff_member=self.staff,
        ))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(AppointmentSlot.objects.filter(company=self.company).exists())


class AdminRegistrationTests(TestCase):
    def test_model_registered_in_admin(self):
        from django.contrib import admin as django_admin
        self.assertIn(AppointmentSlot, django_admin.site._registry)

    def test_admin_list_display(self):
        admin_instance = AppointmentSlotAdmin(AppointmentSlot, AdminSite())
        self.assertEqual(
            admin_instance.list_display,
            ("company", "start_at", "end_at", "status", "created_at", "updated_at"),
        )
