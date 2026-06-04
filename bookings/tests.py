from datetime import date as date_type
from datetime import timedelta
from datetime import timezone as dt_tz

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from availability.models import AppointmentSlot
from services.models import ServiceOffering, StaffServiceOffering
from staff_members.models import StaffMember

from .models import Booking

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_company(email, business_name="Test Co", public_page_enabled=True, is_active=True):
    return User.objects.create_user(
        email=email,
        password="testpassword123",
        business_name=business_name,
        public_page_enabled=public_page_enabled,
        is_active=is_active,
    )


def _make_staff(company, name="Alice", is_active=True):
    return StaffMember.objects.create(company=company, name=name, is_active=is_active)


def _make_service(company, name="Consultation", duration=30, is_active=True):
    return ServiceOffering.objects.create(
        company=company, name=name, duration_minutes=duration, is_active=is_active,
    )


def _assign(staff, service, is_active=True):
    return StaffServiceOffering.objects.create(
        staff_member=staff, service_offering=service, is_active=is_active,
    )


def _make_availability(company, staff, start_offset_hours=2, duration_hours=4, status="available"):
    """Create an AppointmentSlot availability window."""
    now = timezone.now()
    start = now + timedelta(hours=start_offset_hours)
    end = start + timedelta(hours=duration_hours)
    return AppointmentSlot.objects.create(
        company=company, staff_member=staff, start_at=start, end_at=end, status=status,
    )


def _make_start_at(offset_hours=2):
    """Return a future UTC-aware datetime rounded to the next 15-min boundary."""
    now = timezone.now()
    t = now + timedelta(hours=offset_hours)
    # Round up to next 15-min boundary
    minutes = (t.minute // 15 + 1) * 15
    return t.replace(minute=0, second=0, microsecond=0) + timedelta(minutes=minutes)


def _entry_url(company):
    return reverse("bookings:entry", kwargs={"company_slug": company.slug})


def _service_url(company, staff):
    return reverse("bookings:service_select", kwargs={
        "company_slug": company.slug, "staff_id": staff.pk,
    })


def _slot_url(company, staff, service):
    return reverse("bookings:slot_select", kwargs={
        "company_slug": company.slug, "staff_id": staff.pk, "service_id": service.pk,
    })


def _time_url(company, staff, service, target_date):
    return reverse("bookings:time_select", kwargs={
        "company_slug": company.slug,
        "staff_id": staff.pk,
        "service_id": service.pk,
        "date": target_date.strftime("%Y-%m-%d"),
    })


def _book_url(company, staff, service, start_at):
    return reverse("bookings:book", kwargs={
        "company_slug": company.slug,
        "staff_id": staff.pk,
        "service_id": service.pk,
        "date": start_at.strftime("%Y-%m-%d"),
        "start_time": start_at.strftime("%H-%M"),
    })


def _valid_post_data():
    return {
        "customer_first_name": "Jane",
        "customer_last_name": "Doe",
        "customer_email": "jane@example.com",
        "customer_phone": "",
        "customer_message": "",
        "privacy_accepted": "on",
        "website": "",
    }


def _create_booking(company, staff, service, start_at, end_at):
    return Booking.objects.create(
        company=company,
        staff_member=staff,
        service_offering=service,
        start_at=start_at,
        end_at=end_at,
        customer_first_name="Jane",
        customer_last_name="Doe",
        customer_email="jane@example.com",
        privacy_accepted_at=timezone.now(),
    )


# ---------------------------------------------------------------------------
# 1. Public Entry
# ---------------------------------------------------------------------------

class PublicEntryTests(TestCase):
    def test_enabled_company_returns_200(self):
        company = _make_company("co@example.com")
        _make_staff(company, "Alice")
        _make_staff(company, "Bob")
        response = self.client.get(_entry_url(company))
        self.assertEqual(response.status_code, 200)

    def test_disabled_public_page_shows_unavailable(self):
        company = _make_company("disabled@example.com", public_page_enabled=False)
        response = self.client.get(_entry_url(company))
        self.assertTemplateUsed(response, "bookings/public_unavailable.html")

    def test_zero_active_staff_shows_unavailable(self):
        company = _make_company("nostaff@example.com")
        _make_staff(company, "Inactive", is_active=False)
        response = self.client.get(_entry_url(company))
        self.assertTemplateUsed(response, "bookings/public_unavailable.html")

    def test_one_active_staff_redirects_to_service_select(self):
        company = _make_company("onestaff@example.com")
        staff = _make_staff(company)
        response = self.client.get(_entry_url(company))
        self.assertRedirects(response, _service_url(company, staff))

    def test_multiple_active_staff_shows_staff_select(self):
        company = _make_company("multi@example.com")
        _make_staff(company, "Alice")
        _make_staff(company, "Bob")
        response = self.client.get(_entry_url(company))
        self.assertTemplateUsed(response, "bookings/public_staff_select.html")

    def test_staff_select_only_shows_active_staff(self):
        company = _make_company("active@example.com")
        _make_staff(company, "Active One")
        _make_staff(company, "Active Two")
        _make_staff(company, "Inactive", is_active=False)
        response = self.client.get(_entry_url(company))
        names = [s.name for s in response.context["staff_members"]]
        self.assertIn("Active One", names)
        self.assertNotIn("Inactive", names)


# ---------------------------------------------------------------------------
# 2. Service Selection
# ---------------------------------------------------------------------------

class ServiceSelectTests(TestCase):
    def setUp(self):
        self.company = _make_company("svc@example.com")
        self.other = _make_company("other@example.com")
        self.staff = _make_staff(self.company)
        self.service = _make_service(self.company)
        _assign(self.staff, self.service)

    def test_staff_not_belonging_to_company_returns_404(self):
        other_staff = _make_staff(self.other, "Eve")
        url = reverse("bookings:service_select", kwargs={
            "company_slug": self.company.slug, "staff_id": other_staff.pk,
        })
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_inactive_staff_returns_404(self):
        inactive = _make_staff(self.company, "Inactive", is_active=False)
        url = reverse("bookings:service_select", kwargs={
            "company_slug": self.company.slug, "staff_id": inactive.pk,
        })
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_only_active_assigned_services_shown(self):
        response = self.client.get(_service_url(self.company, self.staff))
        services = list(response.context["services"])
        self.assertIn(self.service, services)
        self.assertEqual(len(services), 1)

    def test_inactive_service_not_shown(self):
        inactive_svc = _make_service(self.company, "Inactive", is_active=False)
        _assign(self.staff, inactive_svc)
        services = list(self.client.get(_service_url(self.company, self.staff)).context["services"])
        self.assertNotIn(inactive_svc, services)

    def test_other_company_service_not_shown(self):
        other_svc = _make_service(self.other, "Other Service")
        other_staff = _make_staff(self.other, "OtherStaff")
        _assign(other_staff, other_svc)
        services = list(self.client.get(_service_url(self.company, self.staff)).context["services"])
        self.assertNotIn(other_svc, services)

    def test_unassigned_service_not_shown(self):
        unassigned = _make_service(self.company, "Unassigned")
        services = list(self.client.get(_service_url(self.company, self.staff)).context["services"])
        self.assertNotIn(unassigned, services)


# ---------------------------------------------------------------------------
# 3. Day Selection (slot_select)
# ---------------------------------------------------------------------------

class DaySelectTests(TestCase):
    def setUp(self):
        self.company = _make_company("day@example.com")
        self.staff = _make_staff(self.company)
        self.service = _make_service(self.company, duration=30)
        _assign(self.staff, self.service)
        # 4-hour availability window starting in 2 hours
        self.avail = _make_availability(self.company, self.staff, start_offset_hours=2, duration_hours=4)

    def test_days_with_availability_are_shown(self):
        response = self.client.get(_slot_url(self.company, self.staff, self.service))
        self.assertEqual(response.status_code, 200)
        days = response.context["days"]
        self.assertGreater(len(days), 0)

    def test_no_availability_shows_empty_list(self):
        company = _make_company("empty@example.com")
        staff = _make_staff(company)
        service = _make_service(company, duration=30)
        _assign(staff, service)
        response = self.client.get(_slot_url(company, staff, service))
        self.assertEqual(response.context["days"], [])

    def test_service_not_belonging_to_company_returns_404(self):
        other = _make_company("dayother@example.com")
        other_svc = _make_service(other)
        url = reverse("bookings:slot_select", kwargs={
            "company_slug": self.company.slug,
            "staff_id": self.staff.pk,
            "service_id": other_svc.pk,
        })
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_unassigned_service_returns_404(self):
        unassigned = _make_service(self.company, "Unassigned")
        url = reverse("bookings:slot_select", kwargs={
            "company_slug": self.company.slug,
            "staff_id": self.staff.pk,
            "service_id": unassigned.pk,
        })
        self.assertEqual(self.client.get(url).status_code, 404)


# ---------------------------------------------------------------------------
# 4. Time-Window Selection (time_select)
# ---------------------------------------------------------------------------

class TimeSelectTests(TestCase):
    def setUp(self):
        self.company = _make_company("time@example.com")
        self.staff = _make_staff(self.company)
        self.service = _make_service(self.company, duration=30)
        _assign(self.staff, self.service)
        self.avail = _make_availability(self.company, self.staff, start_offset_hours=2, duration_hours=4)
        self.target_date = (timezone.now() + timedelta(hours=2)).date()

    def test_available_windows_shown(self):
        response = self.client.get(_time_url(self.company, self.staff, self.service, self.target_date))
        self.assertEqual(response.status_code, 200)
        windows = response.context["windows"]
        self.assertGreater(len(windows), 0)

    def test_already_booked_window_not_shown(self):
        start_at = _make_start_at(offset_hours=3)
        end_at = start_at + timedelta(minutes=30)
        _create_booking(self.company, self.staff, self.service, start_at, end_at)
        response = self.client.get(_time_url(self.company, self.staff, self.service, start_at.date()))
        windows = response.context["windows"]
        self.assertNotIn(start_at, windows)

    def test_past_windows_not_shown(self):
        response = self.client.get(_time_url(self.company, self.staff, self.service, self.target_date))
        now = timezone.now()
        windows = response.context["windows"]
        for w in windows:
            self.assertGreater(w, now)

    def test_slot_too_short_produces_no_windows(self):
        # Service requires 240 min but availability is only 4 hours = 240 min.
        # 240-min windows in a 240-min slot: only one window at the very start (end aligns exactly).
        # Make availability too short: 20-min window with 30-min service → 0 windows.
        company = _make_company("short@example.com")
        staff = _make_staff(company)
        service = _make_service(company, duration=30)
        _assign(staff, service)
        now = timezone.now()
        short_avail = AppointmentSlot.objects.create(
            company=company,
            staff_member=staff,
            start_at=now + timedelta(hours=2),
            end_at=now + timedelta(hours=2, minutes=20),
            status=AppointmentSlot.Status.AVAILABLE,
        )
        target_date = (now + timedelta(hours=2)).date()
        response = self.client.get(_time_url(company, staff, service, target_date))
        self.assertEqual(response.context["windows"], [])

    def test_slots_from_other_staff_not_shown(self):
        other_staff = _make_staff(self.company, "Bob")
        _assign(other_staff, self.service)
        _make_availability(self.company, other_staff, start_offset_hours=2, duration_hours=4)
        # Only self.staff windows should appear when requesting self.staff's times
        response = self.client.get(_time_url(self.company, self.staff, self.service, self.target_date))
        self.assertEqual(response.status_code, 200)

    def test_blocked_window_not_shown(self):
        now = timezone.now()
        block_start = now + timedelta(hours=3)
        block_end = block_start + timedelta(hours=1)
        AppointmentSlot.objects.create(
            company=self.company,
            staff_member=self.staff,
            start_at=block_start,
            end_at=block_end,
            status=AppointmentSlot.Status.BLOCKED,
        )
        response = self.client.get(_time_url(self.company, self.staff, self.service, self.target_date))
        windows = response.context["windows"]
        for w in windows:
            window_end = w + timedelta(minutes=self.service.duration_minutes)
            # No window should overlap with the blocked range
            self.assertFalse(w < block_end and window_end > block_start)


# ---------------------------------------------------------------------------
# 5. Booking Creation
# ---------------------------------------------------------------------------

class BookingFormTests(TestCase):
    def setUp(self):
        self.company = _make_company("book@example.com")
        self.staff = _make_staff(self.company)
        self.service = _make_service(self.company, duration=30)
        _assign(self.staff, self.service)
        self.avail = _make_availability(self.company, self.staff, start_offset_hours=2, duration_hours=4)
        self.start_at = _make_start_at(offset_hours=3)
        self.url = _book_url(self.company, self.staff, self.service, self.start_at)

    def test_get_shows_booking_form(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "bookings/public_booking_form.html")

    def test_missing_first_name_rejected(self):
        data = {**_valid_post_data(), "customer_first_name": ""}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Booking.objects.filter(company=self.company).exists())

    def test_missing_last_name_rejected(self):
        data = {**_valid_post_data(), "customer_last_name": ""}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Booking.objects.filter(company=self.company).exists())

    def test_missing_email_rejected(self):
        data = {**_valid_post_data(), "customer_email": ""}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Booking.objects.filter(company=self.company).exists())

    def test_missing_privacy_rejected(self):
        data = {k: v for k, v in _valid_post_data().items() if k != "privacy_accepted"}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Booking.objects.filter(company=self.company).exists())

    def test_valid_booking_creates_booking_record(self):
        self.client.post(self.url, _valid_post_data())
        self.assertEqual(Booking.objects.filter(company=self.company).count(), 1)

    def test_valid_booking_stores_correct_start_and_end(self):
        self.client.post(self.url, _valid_post_data())
        booking = Booking.objects.get(company=self.company)
        self.assertEqual(booking.start_at, self.start_at)
        self.assertEqual(booking.end_at, self.start_at + timedelta(minutes=self.service.duration_minutes))

    def test_booking_assigned_to_correct_objects(self):
        self.client.post(self.url, _valid_post_data())
        booking = Booking.objects.get(company=self.company)
        self.assertEqual(booking.staff_member, self.staff)
        self.assertEqual(booking.service_offering, self.service)

    def test_customer_email_is_normalised(self):
        data = {**_valid_post_data(), "customer_email": " JANE@Example.COM "}
        self.client.post(self.url, data)
        booking = Booking.objects.get(company=self.company)
        self.assertEqual(booking.customer_email, "jane@example.com")

    def test_valid_booking_redirects_to_confirmation(self):
        response = self.client.post(self.url, _valid_post_data())
        booking = Booking.objects.get(company=self.company)
        expected = reverse("bookings:confirmed", kwargs={
            "company_slug": self.company.slug, "public_token": booking.public_token,
        })
        self.assertRedirects(response, expected)

    def test_other_company_staff_returns_404(self):
        other = _make_company("otherbk@example.com")
        other_staff = _make_staff(other, "Eve")
        other_service = _make_service(other)
        _assign(other_staff, other_service)
        _make_availability(other, other_staff)
        url = reverse("bookings:book", kwargs={
            "company_slug": self.company.slug,
            "staff_id": other_staff.pk,
            "service_id": other_service.pk,
            "date": self.start_at.strftime("%Y-%m-%d"),
            "start_time": self.start_at.strftime("%H-%M"),
        })
        self.assertEqual(self.client.post(url, _valid_post_data()).status_code, 404)

    def test_unassigned_service_returns_404(self):
        unassigned = _make_service(self.company, "Unassigned")
        url = reverse("bookings:book", kwargs={
            "company_slug": self.company.slug,
            "staff_id": self.staff.pk,
            "service_id": unassigned.pk,
            "date": self.start_at.strftime("%Y-%m-%d"),
            "start_time": self.start_at.strftime("%H-%M"),
        })
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_time_outside_availability_returns_404(self):
        # Request a time with no availability window covering it
        far_future = timezone.now() + timedelta(days=30)
        url = _book_url(self.company, self.staff, self.service, far_future.replace(minute=0, second=0, microsecond=0))
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_past_time_returns_404(self):
        from datetime import datetime
        past = datetime(2000, 1, 1, 10, 0, 0, tzinfo=dt_tz.utc)
        url = reverse("bookings:book", kwargs={
            "company_slug": self.company.slug,
            "staff_id": self.staff.pk,
            "service_id": self.service.pk,
            "date": "2000-01-01",
            "start_time": "10-00",
        })
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_slot_too_short_returns_404(self):
        # Service needs 30 min but availability window is only 20 min wide
        company = _make_company("toosmall@example.com")
        staff = _make_staff(company)
        service = _make_service(company, duration=30)
        _assign(staff, service)
        now = timezone.now()
        AppointmentSlot.objects.create(
            company=company, staff_member=staff,
            start_at=now + timedelta(hours=2),
            end_at=now + timedelta(hours=2, minutes=20),
            status=AppointmentSlot.Status.AVAILABLE,
        )
        start = (now + timedelta(hours=2)).replace(second=0, microsecond=0)
        url = _book_url(company, staff, service, start)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_double_booking_prevented(self):
        # Book the first time
        self.client.post(self.url, _valid_post_data())
        self.assertEqual(Booking.objects.filter(company=self.company).count(), 1)
        # Second attempt for the same time window should 404
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Booking.objects.filter(company=self.company).count(), 1)


# ---------------------------------------------------------------------------
# 6. Booking Confirmation
# ---------------------------------------------------------------------------

class BookingConfirmedTests(TestCase):
    def setUp(self):
        self.company = _make_company("conf@example.com")
        self.other = _make_company("confother@example.com")
        self.staff = _make_staff(self.company)
        self.service = _make_service(self.company)
        _assign(self.staff, self.service)
        self.start_at = _make_start_at()
        self.end_at = self.start_at + timedelta(minutes=30)

    def test_valid_token_shows_confirmation(self):
        booking = _create_booking(self.company, self.staff, self.service, self.start_at, self.end_at)
        url = reverse("bookings:confirmed", kwargs={
            "company_slug": self.company.slug, "public_token": booking.public_token,
        })
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "bookings/public_booking_confirmed.html")

    def test_other_company_token_returns_404(self):
        other_staff = _make_staff(self.other, "Eve")
        other_svc = _make_service(self.other)
        _assign(other_staff, other_svc)
        other_booking = _create_booking(
            self.other, other_staff, other_svc, self.start_at, self.end_at,
        )
        url = reverse("bookings:confirmed", kwargs={
            "company_slug": self.company.slug, "public_token": other_booking.public_token,
        })
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_invalid_token_returns_404(self):
        url = reverse("bookings:confirmed", kwargs={
            "company_slug": self.company.slug, "public_token": "not-a-real-token",
        })
        self.assertEqual(self.client.get(url).status_code, 404)


# ---------------------------------------------------------------------------
# 7. Security
# ---------------------------------------------------------------------------

class BookingSecurityTests(TestCase):
    def setUp(self):
        self.company = _make_company("sec@example.com")
        self.other = _make_company("secother@example.com")
        self.staff = _make_staff(self.company)
        self.service = _make_service(self.company)
        _assign(self.staff, self.service)
        self.avail = _make_availability(self.company, self.staff, start_offset_hours=2, duration_hours=4)
        self.start_at = _make_start_at(offset_hours=3)
        self.url = _book_url(self.company, self.staff, self.service, self.start_at)

    def test_post_data_cannot_override_company(self):
        other_staff = _make_staff(self.other, "Eve")
        other_svc = _make_service(self.other)
        _assign(other_staff, other_svc)
        _make_availability(self.other, other_staff)
        data = {
            **_valid_post_data(),
            "company": self.other.pk,
            "staff_member": other_staff.pk,
            "service_offering": other_svc.pk,
        }
        self.client.post(self.url, data)
        booking = Booking.objects.filter(company=self.company).first()
        self.assertIsNotNone(booking)
        self.assertEqual(booking.staff_member, self.staff)
        self.assertFalse(Booking.objects.filter(company=self.other).exists())

    def test_honeypot_rejects_bot_submission(self):
        data = {**_valid_post_data(), "website": "http://spam.example.com"}
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Booking.objects.filter(company=self.company).exists())

    def test_public_pages_do_not_expose_inactive_services(self):
        inactive_svc = _make_service(self.company, "Inactive Service", is_active=False)
        _assign(self.staff, inactive_svc)
        services = list(self.client.get(_service_url(self.company, self.staff)).context["services"])
        self.assertNotIn(inactive_svc, services)

    def test_public_pages_do_not_expose_inactive_staff(self):
        inactive = _make_staff(self.company, "Inactive", is_active=False)
        _make_staff(self.company, "Another Active")
        staff_list = list(self.client.get(_entry_url(self.company)).context["staff_members"])
        self.assertNotIn(inactive, staff_list)
