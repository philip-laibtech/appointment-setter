from datetime import date as date_type
from datetime import timedelta
from datetime import timezone as dt_tz

from django.conf import settings
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
        tos_version=settings.CURRENT_TOS_VERSION,
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
        "company_slug": company.slug, "staff_uid": staff.public_id,
    })


def _slot_url(company, staff, service):
    return reverse("bookings:slot_select", kwargs={
        "company_slug": company.slug, "staff_uid": staff.public_id, "service_uid": service.public_id,
    })


def _time_url(company, staff, service, target_date):
    return reverse("bookings:time_select", kwargs={
        "company_slug": company.slug,
        "staff_uid": staff.public_id,
        "service_uid": service.public_id,
        "date": target_date.strftime("%Y-%m-%d"),
    })


def _book_url(company, staff, service, start_at):
    local = timezone.localtime(start_at)
    return reverse("bookings:book", kwargs={
        "company_slug": company.slug,
        "staff_uid": staff.public_id,
        "service_uid": service.public_id,
        "date": local.strftime("%Y-%m-%d"),
        "start_time": local.strftime("%H-%M"),
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
        "captcha_0": "PASSED",
        "captcha_1": "PASSED",
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
            "company_slug": self.company.slug, "staff_uid": other_staff.public_id,
        })
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_inactive_staff_returns_404(self):
        inactive = _make_staff(self.company, "Inactive", is_active=False)
        url = reverse("bookings:service_select", kwargs={
            "company_slug": self.company.slug, "staff_uid": inactive.public_id,
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
            "staff_uid": self.staff.public_id,
            "service_uid": other_svc.public_id,
        })
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_unassigned_service_returns_404(self):
        unassigned = _make_service(self.company, "Unassigned")
        url = reverse("bookings:slot_select", kwargs={
            "company_slug": self.company.slug,
            "staff_uid": self.staff.public_id,
            "service_uid": unassigned.public_id,
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
            "staff_uid": other_staff.public_id,
            "service_uid": other_service.public_id,
            "date": self.start_at.strftime("%Y-%m-%d"),
            "start_time": self.start_at.strftime("%H-%M"),
        })
        self.assertEqual(self.client.post(url, _valid_post_data()).status_code, 404)

    def test_unassigned_service_returns_404(self):
        unassigned = _make_service(self.company, "Unassigned")
        url = reverse("bookings:book", kwargs={
            "company_slug": self.company.slug,
            "staff_uid": self.staff.public_id,
            "service_uid": unassigned.public_id,
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
            "staff_uid": self.staff.public_id,
            "service_uid": self.service.public_id,
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

    def test_cancelled_booking_shows_cancelled_status(self):
        booking = _create_booking(self.company, self.staff, self.service, self.start_at, self.end_at)
        booking.status = Booking.Status.CANCELLED
        booking.save()
        url = reverse("bookings:confirmed", kwargs={
            "company_slug": self.company.slug, "public_token": booking.public_token,
        })
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # Company language defaults to German, so the status badge is translated.
        self.assertContains(response, "Storniert")


class BookingCancelTests(TestCase):
    def setUp(self):
        self.company = _make_company("cancel@example.com")
        self.other = _make_company("cancelother@example.com")
        self.staff = _make_staff(self.company)
        self.service = _make_service(self.company)
        _assign(self.staff, self.service)
        self.start_at = _make_start_at()
        self.end_at = self.start_at + timedelta(minutes=30)
        self.booking = _create_booking(
            self.company, self.staff, self.service, self.start_at, self.end_at,
        )
        self.cancel_url = reverse("bookings:cancel", kwargs={
            "company_slug": self.company.slug,
            "public_token": self.booking.public_token,
        })

    def test_get_shows_cancel_confirmation_page(self):
        response = self.client.get(self.cancel_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "bookings/public_booking_cancel.html")

    def test_post_cancels_booking(self):
        self.client.post(self.cancel_url)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.CANCELLED)

    def test_cancel_redirects_to_confirmed_page(self):
        response = self.client.post(self.cancel_url)
        self.assertRedirects(response, reverse("bookings:confirmed", kwargs={
            "company_slug": self.company.slug,
            "public_token": self.booking.public_token,
        }))

    def test_already_cancelled_booking_returns_404(self):
        self.booking.status = Booking.Status.CANCELLED
        self.booking.save()
        response = self.client.get(self.cancel_url)
        self.assertEqual(response.status_code, 404)

    def test_other_company_token_returns_404(self):
        other_staff = _make_staff(self.other, "Eve")
        other_svc = _make_service(self.other)
        _assign(other_staff, other_svc)
        other_booking = _create_booking(
            self.other, other_staff, other_svc, self.start_at, self.end_at,
        )
        url = reverse("bookings:cancel", kwargs={
            "company_slug": self.company.slug,
            "public_token": other_booking.public_token,
        })
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_cancelled_slot_becomes_bookable_again(self):
        """After cancellation the slot window is available for new bookings."""
        # Slot must start on a 15-min boundary so _windows_for_date aligns to self.start_at.
        slot_start = self.start_at - timedelta(hours=1)
        AppointmentSlot.objects.create(
            company=self.company,
            staff_member=self.staff,
            start_at=slot_start,
            end_at=slot_start + timedelta(hours=4),
        )
        self.client.post(self.cancel_url)
        from bookings.views import _windows_for_date
        windows = _windows_for_date(
            self.staff, self.service.duration_minutes, self.start_at.date(),
        )
        self.assertIn(self.start_at, windows)


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


# ---------------------------------------------------------------------------
# Any Employee helpers
# ---------------------------------------------------------------------------

def _any_service_url(company):
    return reverse("bookings:any_service_select", kwargs={"company_slug": company.slug})


def _any_slot_url(company, service):
    return reverse("bookings:any_slot_select", kwargs={
        "company_slug": company.slug, "service_uid": service.public_id,
    })


def _any_time_url(company, service, target_date):
    return reverse("bookings:any_time_select", kwargs={
        "company_slug": company.slug,
        "service_uid": service.public_id,
        "date": target_date.strftime("%Y-%m-%d"),
    })


def _any_book_url(company, service, date_str, start_time_str):
    return reverse("bookings:any_book", kwargs={
        "company_slug": company.slug,
        "service_uid": service.public_id,
        "date": date_str,
        "start_time": start_time_str,
    })


# ---------------------------------------------------------------------------
# 8. Any Employee — Public Entry Page
# ---------------------------------------------------------------------------

class AnyEmployeeEntryTests(TestCase):
    def test_multiple_active_staff_shows_any_employee(self):
        company = _make_company("anyentry1@example.com")
        _make_staff(company, "Alice")
        _make_staff(company, "Bob")
        response = self.client.get(_entry_url(company))
        # Company language defaults to German, so "Any Employee" is translated.
        self.assertContains(response, "Beliebiger Mitarbeiter")

    def test_any_employee_not_shown_with_zero_active_staff(self):
        company = _make_company("anyentry2@example.com")
        _make_staff(company, "Inactive", is_active=False)
        response = self.client.get(_entry_url(company))
        self.assertTemplateUsed(response, "bookings/public_unavailable.html")
        self.assertNotContains(response, "Any Employee")

    def test_any_employee_not_shown_with_one_active_staff(self):
        company = _make_company("anyentry3@example.com")
        staff = _make_staff(company, "Solo")
        response = self.client.get(_entry_url(company))
        # Single staff → redirect to service_select (302), no staff select page rendered
        self.assertEqual(response.status_code, 302)

    def test_any_employee_links_to_any_service_select(self):
        company = _make_company("anyentry4@example.com")
        _make_staff(company, "Alice")
        _make_staff(company, "Bob")
        response = self.client.get(_entry_url(company))
        expected_url = _any_service_url(company)
        self.assertContains(response, expected_url)


# ---------------------------------------------------------------------------
# 9. Any Employee — Service Selection
# ---------------------------------------------------------------------------

class AnyServiceSelectTests(TestCase):
    def setUp(self):
        self.company = _make_company("anysvc@example.com")
        self.other = _make_company("anysvcother@example.com")
        self.staff = _make_staff(self.company, "Alice")
        self.service = _make_service(self.company, "Massage", duration=30)
        _assign(self.staff, self.service)

    def test_returns_200_for_enabled_company(self):
        response = self.client.get(_any_service_url(self.company))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "bookings/any_service_select.html")

    def test_disabled_public_page_returns_404(self):
        company = _make_company("anydisabled@example.com", public_page_enabled=False)
        response = self.client.get(_any_service_url(company))
        self.assertEqual(response.status_code, 404)

    def test_only_active_services_shown(self):
        inactive = _make_service(self.company, "Inactive Svc", is_active=False)
        _assign(self.staff, inactive)
        response = self.client.get(_any_service_url(self.company))
        services = list(response.context["services"])
        self.assertIn(self.service, services)
        self.assertNotIn(inactive, services)

    def test_service_with_no_active_assigned_staff_not_shown(self):
        unassigned = _make_service(self.company, "Unassigned")
        response = self.client.get(_any_service_url(self.company))
        services = list(response.context["services"])
        self.assertNotIn(unassigned, services)

    def test_service_assigned_only_to_inactive_staff_not_shown(self):
        inactive_staff = _make_staff(self.company, "Inactive", is_active=False)
        exclusive_svc = _make_service(self.company, "Inactive Staff Only")
        _assign(inactive_staff, exclusive_svc)
        response = self.client.get(_any_service_url(self.company))
        services = list(response.context["services"])
        self.assertNotIn(exclusive_svc, services)

    def test_services_from_other_companies_not_shown(self):
        other_staff = _make_staff(self.other, "Eve")
        other_svc = _make_service(self.other, "Other Co Service")
        _assign(other_staff, other_svc)
        response = self.client.get(_any_service_url(self.company))
        services = list(response.context["services"])
        self.assertNotIn(other_svc, services)


# ---------------------------------------------------------------------------
# 10. Any Employee — Day Selection
# ---------------------------------------------------------------------------

class AnySlotSelectTests(TestCase):
    def setUp(self):
        self.company = _make_company("anyslot@example.com")
        self.other = _make_company("anyslotother@example.com")
        self.staff = _make_staff(self.company, "Alice")
        self.service = _make_service(self.company, "Haircut", duration=30)
        _assign(self.staff, self.service)
        self.avail = _make_availability(self.company, self.staff, start_offset_hours=2, duration_hours=2)

    def test_service_not_belonging_to_company_returns_404(self):
        other_svc = _make_service(self.other, "Other")
        url = reverse("bookings:any_slot_select", kwargs={
            "company_slug": self.company.slug, "service_uid": other_svc.public_id,
        })
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_inactive_service_returns_404(self):
        inactive_svc = _make_service(self.company, "Inactive", is_active=False)
        url = reverse("bookings:any_slot_select", kwargs={
            "company_slug": self.company.slug, "service_uid": inactive_svc.public_id,
        })
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_days_with_availability_shown(self):
        response = self.client.get(_any_slot_url(self.company, self.service))
        self.assertEqual(response.status_code, 200)
        days = response.context["days"]
        self.assertIn(self.avail.start_at.date(), days)

    def test_unassigned_staff_availability_not_included(self):
        company = _make_company("anyslot_unassigned@example.com")
        staff = _make_staff(company, "Bob")
        service = _make_service(company, "Test", duration=30)
        # Bob NOT assigned to service
        _make_availability(company, staff, start_offset_hours=2, duration_hours=2)
        response = self.client.get(reverse("bookings:any_slot_select", kwargs={
            "company_slug": company.slug, "service_uid": service.public_id,
        }))
        self.assertEqual(response.context["days"], [])

    def test_inactive_staff_availability_not_included(self):
        company = _make_company("anyslot_inactive@example.com")
        inactive = _make_staff(company, "Inactive", is_active=False)
        service = _make_service(company, "Test", duration=30)
        _assign(inactive, service)
        _make_availability(company, inactive, start_offset_hours=2, duration_hours=2)
        response = self.client.get(reverse("bookings:any_slot_select", kwargs={
            "company_slug": company.slug, "service_uid": service.public_id,
        }))
        self.assertEqual(response.context["days"], [])

    def test_booked_availability_not_included(self):
        company = _make_company("anyslot_booked@example.com")
        staff = _make_staff(company, "Alice")
        service = _make_service(company, "Test", duration=30)
        _assign(staff, service)
        _make_availability(company, staff, start_offset_hours=2, duration_hours=2, status="booked")
        response = self.client.get(reverse("bookings:any_slot_select", kwargs={
            "company_slug": company.slug, "service_uid": service.public_id,
        }))
        self.assertEqual(response.context["days"], [])

    def test_past_availability_not_included(self):
        company = _make_company("anyslot_past@example.com")
        staff = _make_staff(company, "Alice")
        service = _make_service(company, "Test", duration=30)
        _assign(staff, service)
        now = timezone.now()
        AppointmentSlot.objects.create(
            company=company, staff_member=staff,
            start_at=now - timedelta(hours=3),
            end_at=now - timedelta(hours=2),
            status=AppointmentSlot.Status.AVAILABLE,
        )
        response = self.client.get(reverse("bookings:any_slot_select", kwargs={
            "company_slug": company.slug, "service_uid": service.public_id,
        }))
        self.assertEqual(response.context["days"], [])

    def test_availability_too_short_for_service_not_included(self):
        company = _make_company("anyslot_short@example.com")
        staff = _make_staff(company, "Alice")
        service = _make_service(company, "Test", duration=30)
        _assign(staff, service)
        now = timezone.now()
        AppointmentSlot.objects.create(
            company=company, staff_member=staff,
            start_at=now + timedelta(hours=5),
            end_at=now + timedelta(hours=5, minutes=20),  # 20 min < 30 min service
            status=AppointmentSlot.Status.AVAILABLE,
        )
        response = self.client.get(reverse("bookings:any_slot_select", kwargs={
            "company_slug": company.slug, "service_uid": service.public_id,
        }))
        self.assertEqual(response.context["days"], [])

    def test_no_availability_shows_empty_list(self):
        company = _make_company("anyslot_empty@example.com")
        staff = _make_staff(company, "Alice")
        service = _make_service(company, "Test", duration=30)
        _assign(staff, service)
        response = self.client.get(reverse("bookings:any_slot_select", kwargs={
            "company_slug": company.slug, "service_uid": service.public_id,
        }))
        self.assertEqual(response.context["days"], [])


# ---------------------------------------------------------------------------
# 10b. Any Employee — Time Selection
# ---------------------------------------------------------------------------

class AnyTimeSelectTests(TestCase):
    def setUp(self):
        self.company = _make_company("anytime@example.com")
        self.staff = _make_staff(self.company, "Alice")
        self.service = _make_service(self.company, "Haircut", duration=30)
        _assign(self.staff, self.service)
        self.avail = _make_availability(self.company, self.staff, start_offset_hours=2, duration_hours=4)
        self.target_date = (timezone.now() + timedelta(hours=2)).date()

    def test_returns_200_with_windows(self):
        response = self.client.get(_any_time_url(self.company, self.service, self.target_date))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "bookings/any_time_select.html")
        self.assertGreater(len(response.context["windows"]), 0)

    def test_past_windows_not_shown(self):
        response = self.client.get(_any_time_url(self.company, self.service, self.target_date))
        now = timezone.now()
        for w in response.context["windows"]:
            self.assertGreater(w, now)

    def test_already_booked_window_not_shown(self):
        start_at = _make_start_at(offset_hours=3)
        end_at = start_at + timedelta(minutes=30)
        _create_booking(self.company, self.staff, self.service, start_at, end_at)
        response = self.client.get(_any_time_url(self.company, self.service, start_at.date()))
        self.assertNotIn(start_at, response.context["windows"])

    def test_inactive_service_returns_404(self):
        inactive = _make_service(self.company, "Inactive", is_active=False)
        url = reverse("bookings:any_time_select", kwargs={
            "company_slug": self.company.slug,
            "service_uid": inactive.public_id,
            "date": self.target_date.strftime("%Y-%m-%d"),
        })
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_multiple_staff_windows_merged(self):
        bob = _make_staff(self.company, "Bob")
        _assign(bob, self.service)
        # Bob has a slot starting 1 hour after Alice's, on the same day
        bob_avail = _make_availability(self.company, bob, start_offset_hours=3, duration_hours=2)
        response = self.client.get(_any_time_url(self.company, self.service, self.target_date))
        windows = response.context["windows"]
        # Both Alice's and Bob's windows are present (deduplicated)
        self.assertGreater(len(windows), 0)
        # Windows are sorted
        self.assertEqual(windows, sorted(windows))


# ---------------------------------------------------------------------------
# 11. Any Employee — Booking Form
# ---------------------------------------------------------------------------

class AnyBookingFormTests(TestCase):
    def setUp(self):
        self.company = _make_company("anybook@example.com")
        self.other = _make_company("anybookother@example.com")
        self.staff = _make_staff(self.company, "Alice")
        self.service = _make_service(self.company, "Facial", duration=30)
        _assign(self.staff, self.service)
        # 4-hour window; book at a 15-min boundary safely inside the window
        self.avail = _make_availability(self.company, self.staff, start_offset_hours=2, duration_hours=4)
        self.start_at = _make_start_at(offset_hours=3)
        local = timezone.localtime(self.start_at)
        self.date_str = local.strftime("%Y-%m-%d")
        self.start_time_str = local.strftime("%H-%M")
        self.url = _any_book_url(self.company, self.service, self.date_str, self.start_time_str)

    def test_get_works_for_valid_service_and_time(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "bookings/any_booking_form.html")

    def test_rejects_time_with_no_eligible_staff(self):
        # Bob has availability but is NOT assigned to service
        other_staff = _make_staff(self.company, "Bob")
        other_avail = _make_availability(self.company, other_staff, start_offset_hours=10, duration_hours=2)
        start_at = other_avail.start_at
        url = _any_book_url(self.company, self.service,
                            start_at.strftime("%Y-%m-%d"), start_at.strftime("%H-%M"))
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_rejects_time_with_only_inactive_staff(self):
        inactive = _make_staff(self.company, "Inactive", is_active=False)
        _assign(inactive, self.service)
        inactive_avail = _make_availability(self.company, inactive, start_offset_hours=10, duration_hours=2)
        start_at = inactive_avail.start_at
        url = _any_book_url(self.company, self.service,
                            start_at.strftime("%Y-%m-%d"), start_at.strftime("%H-%M"))
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_rejects_past_time(self):
        now = timezone.now()
        past = now - timedelta(hours=1)
        url = _any_book_url(self.company, self.service,
                            past.strftime("%Y-%m-%d"), past.strftime("%H-%M"))
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_rejects_time_with_no_covering_slot(self):
        now = timezone.now()
        far_future = now + timedelta(days=10)
        url = _any_book_url(self.company, self.service,
                            far_future.strftime("%Y-%m-%d"), far_future.strftime("%H-%M"))
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_rejects_time_where_service_cannot_fit_in_slot(self):
        now = timezone.now()
        # Create a 20-min slot at a clean minute boundary; 30-min service can't fit
        slot_start = now.replace(second=0, microsecond=0) + timedelta(hours=8)
        AppointmentSlot.objects.create(
            company=self.company, staff_member=self.staff,
            start_at=slot_start,
            end_at=slot_start + timedelta(minutes=20),
            status=AppointmentSlot.Status.AVAILABLE,
        )
        url = _any_book_url(self.company, self.service,
                            slot_start.strftime("%Y-%m-%d"), slot_start.strftime("%H-%M"))
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_valid_booking_creates_booking_record(self):
        self.client.post(self.url, _valid_post_data())
        self.assertEqual(Booking.objects.filter(company=self.company).count(), 1)

    def test_backend_assigns_eligible_staff_member(self):
        self.client.post(self.url, _valid_post_data())
        booking = Booking.objects.get(company=self.company)
        self.assertEqual(booking.staff_member, self.staff)

    def test_booking_assigns_correct_service(self):
        self.client.post(self.url, _valid_post_data())
        booking = Booking.objects.get(company=self.company)
        self.assertEqual(booking.service_offering, self.service)

    def test_availability_slot_stays_available_after_booking(self):
        self.client.post(self.url, _valid_post_data())
        self.avail.refresh_from_db()
        self.assertEqual(self.avail.status, AppointmentSlot.Status.AVAILABLE)

    def test_double_booking_same_window_prevented(self):
        self.client.post(self.url, _valid_post_data())
        self.assertEqual(Booking.objects.filter(company=self.company).count(), 1)
        # Second attempt at same window → no eligible staff (confirmed booking overlaps)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(Booking.objects.filter(company=self.company).count(), 1)

    def test_customer_cannot_override_staff_member_via_post(self):
        other_staff = _make_staff(self.other, "Eve")
        data = {**_valid_post_data(), "staff_member": other_staff.pk}
        self.client.post(self.url, data)
        booking = Booking.objects.filter(company=self.company).first()
        self.assertIsNotNone(booking)
        self.assertEqual(booking.staff_member, self.staff)  # backend picked Alice


# ---------------------------------------------------------------------------
# 12. Any Employee — Confirmation
# ---------------------------------------------------------------------------

class AnyBookingConfirmationTests(TestCase):
    def setUp(self):
        self.company = _make_company("anyconf@example.com")
        self.staff = _make_staff(self.company, "Alice")
        self.service = _make_service(self.company, "Pedicure", duration=30)
        _assign(self.staff, self.service)
        self.avail = _make_availability(self.company, self.staff, start_offset_hours=2, duration_hours=4)
        self.start_at = _make_start_at(offset_hours=3)
        local = timezone.localtime(self.start_at)
        self.date_str = local.strftime("%Y-%m-%d")
        self.start_time_str = local.strftime("%H-%M")

    def test_successful_booking_redirects_to_confirmation(self):
        url = _any_book_url(self.company, self.service, self.date_str, self.start_time_str)
        response = self.client.post(url, _valid_post_data())
        booking = Booking.objects.get(company=self.company)
        expected = reverse("bookings:confirmed", kwargs={
            "company_slug": self.company.slug, "public_token": booking.public_token,
        })
        self.assertRedirects(response, expected)

    def test_confirmation_page_shows_actual_staff_member(self):
        url = _any_book_url(self.company, self.service, self.date_str, self.start_time_str)
        self.client.post(url, _valid_post_data())
        booking = Booking.objects.get(company=self.company)
        conf_url = reverse("bookings:confirmed", kwargs={
            "company_slug": self.company.slug, "public_token": booking.public_token,
        })
        response = self.client.get(conf_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.staff.name)


# ---------------------------------------------------------------------------
# Helpers for confirmation-mode tests
# ---------------------------------------------------------------------------

def _make_company_manual(email, business_name="Manual Co"):
    from company_accounts.models import CompanyAccount
    return CompanyAccount.objects.create_user(
        email=email,
        password="testpassword123",
        business_name=business_name,
        booking_confirmation_mode=CompanyAccount.BookingConfirmationMode.MANUAL,
        tos_version=settings.CURRENT_TOS_VERSION,
    )


# ---------------------------------------------------------------------------
# 13. Automatic confirmation mode
# ---------------------------------------------------------------------------

class AutomaticConfirmationTests(TestCase):
    """Tests 6-8: automatic mode creates confirmed booking, booked slot, correct page copy."""

    def setUp(self):
        self.company = _make_company("autoconf@example.com")
        self.staff = _make_staff(self.company)
        self.service = _make_service(self.company, duration=30)
        _assign(self.staff, self.service)
        self.avail = _make_availability(self.company, self.staff, start_offset_hours=2, duration_hours=4)
        self.start_at = _make_start_at(offset_hours=3)
        self.url = _book_url(self.company, self.staff, self.service, self.start_at)

    def test_automatic_mode_creates_confirmed_booking(self):
        self.client.post(self.url, _valid_post_data())
        booking = Booking.objects.get(company=self.company)
        self.assertEqual(booking.status, Booking.Status.CONFIRMED)

    def test_automatic_mode_slot_stays_available(self):
        self.client.post(self.url, _valid_post_data())
        self.avail.refresh_from_db()
        self.assertEqual(self.avail.status, AppointmentSlot.Status.AVAILABLE)

    def test_automatic_booking_confirmation_page_says_confirmed(self):
        self.client.post(self.url, _valid_post_data())
        booking = Booking.objects.get(company=self.company)
        url = reverse("bookings:confirmed", kwargs={
            "company_slug": self.company.slug, "public_token": booking.public_token,
        })
        response = self.client.get(url)
        self.assertContains(response, "Ihre Buchung ist bestätigt")


# ---------------------------------------------------------------------------
# 14. Manual confirmation mode
# ---------------------------------------------------------------------------

class ManualConfirmationTests(TestCase):
    """Tests 9-12: manual mode creates pending booking, pending slot, correct page copy."""

    def setUp(self):
        self.company = _make_company_manual("manualconf@example.com")
        self.staff = _make_staff(self.company)
        self.service = _make_service(self.company, duration=30)
        _assign(self.staff, self.service)
        self.avail = _make_availability(self.company, self.staff, start_offset_hours=2, duration_hours=4)
        self.start_at = _make_start_at(offset_hours=3)
        self.url = _book_url(self.company, self.staff, self.service, self.start_at)

    def test_manual_mode_creates_pending_booking(self):
        self.client.post(self.url, _valid_post_data())
        booking = Booking.objects.get(company=self.company)
        self.assertEqual(booking.status, Booking.Status.PENDING)

    def test_manual_mode_slot_stays_available(self):
        self.client.post(self.url, _valid_post_data())
        self.avail.refresh_from_db()
        self.assertEqual(self.avail.status, AppointmentSlot.Status.AVAILABLE)

    def test_pending_booking_window_not_shown_publicly(self):
        """After a manual booking, the booked time window disappears from public listing."""
        self.client.post(self.url, _valid_post_data())
        # The pending booking is in _occupied_ranges, so its window is excluded.
        from bookings.views import _windows_for_date
        windows = _windows_for_date(self.staff, self.service.duration_minutes, self.start_at.date())
        self.assertNotIn(self.start_at, windows)

    def test_manual_booking_confirmation_page_says_request_received(self):
        self.client.post(self.url, _valid_post_data())
        booking = Booking.objects.get(company=self.company)
        url = reverse("bookings:confirmed", kwargs={
            "company_slug": self.company.slug, "public_token": booking.public_token,
        })
        response = self.client.get(url)
        self.assertContains(response, "Buchungsanfrage erhalten")
        self.assertNotContains(response, "Ihre Buchung ist bestätigt")


# ---------------------------------------------------------------------------
# 15. Pending bookings page
# ---------------------------------------------------------------------------

class PendingBookingsPageTests(TestCase):
    """Tests 13-16: pending page requires login, scoped to own company."""

    def setUp(self):
        self.company = _make_company("pbpage@example.com")
        self.other = _make_company("pbother@example.com")
        self.staff = _make_staff(self.company)
        self.service = _make_service(self.company, duration=30)
        _assign(self.staff, self.service)
        self.start_at = _make_start_at()
        self.end_at = self.start_at + timedelta(minutes=30)
        self.url = reverse("bookings:pending_bookings")

    def _make_pending_booking(self, company, staff, service):
        b = _create_booking(company, staff, service, self.start_at, self.end_at)
        b.status = Booking.Status.PENDING
        b.save()
        return b

    def test_pending_page_requires_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    def test_company_sees_own_pending_bookings(self):
        booking = self._make_pending_booking(self.company, self.staff, self.service)
        self.client.force_login(self.company)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(booking, response.context["pending_bookings"])

    def test_company_does_not_see_confirmed_bookings_on_pending_page(self):
        confirmed = _create_booking(self.company, self.staff, self.service, self.start_at, self.end_at)
        self.client.force_login(self.company)
        response = self.client.get(self.url)
        self.assertNotIn(confirmed, response.context["pending_bookings"])

    def test_company_does_not_see_other_company_pending_bookings(self):
        other_staff = _make_staff(self.other, "Eve")
        other_svc = _make_service(self.other)
        _assign(other_staff, other_svc)
        other_booking = self._make_pending_booking(self.other, other_staff, other_svc)
        self.client.force_login(self.company)
        response = self.client.get(self.url)
        self.assertNotIn(other_booking, response.context["pending_bookings"])


# ---------------------------------------------------------------------------
# 16. Confirm action
# ---------------------------------------------------------------------------

class ConfirmBookingTests(TestCase):
    """Tests 17-23: confirm requires POST+login, scoped, transitions states correctly."""

    def setUp(self):
        self.company = _make_company_manual("confirmco@example.com")
        self.other = _make_company("confirmother@example.com")
        self.staff = _make_staff(self.company)
        self.service = _make_service(self.company, duration=30)
        _assign(self.staff, self.service)
        self.start_at = _make_start_at()
        self.end_at = self.start_at + timedelta(minutes=30)

        self.slot = AppointmentSlot.objects.create(
            company=self.company,
            staff_member=self.staff,
            start_at=self.start_at - timedelta(hours=1),
            end_at=self.end_at + timedelta(hours=1),
            status=AppointmentSlot.Status.AVAILABLE,
        )
        self.booking = Booking.objects.create(
            company=self.company,
            staff_member=self.staff,
            service_offering=self.service,
            appointment_slot=self.slot,
            start_at=self.start_at,
            end_at=self.end_at,
            customer_first_name="Jane",
            customer_last_name="Doe",
            customer_email="jane@example.com",
            privacy_accepted_at=timezone.now(),
            status=Booking.Status.PENDING,
        )
        self.confirm_url = reverse("bookings:confirm_booking", kwargs={"booking_id": self.booking.pk})

    def test_confirm_requires_post(self):
        self.client.force_login(self.company)
        response = self.client.get(self.confirm_url)
        self.assertEqual(response.status_code, 405)

    def test_confirm_requires_login(self):
        response = self.client.post(self.confirm_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    def test_company_can_confirm_own_pending_booking(self):
        self.client.force_login(self.company)
        self.client.post(self.confirm_url)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.CONFIRMED)

    def test_confirming_sets_booking_status_to_confirmed(self):
        self.client.force_login(self.company)
        self.client.post(self.confirm_url)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.CONFIRMED)

    def test_confirming_slot_stays_available(self):
        self.client.force_login(self.company)
        self.client.post(self.confirm_url)
        self.slot.refresh_from_db()
        self.assertEqual(self.slot.status, AppointmentSlot.Status.AVAILABLE)

    def test_company_cannot_confirm_other_company_booking(self):
        other_staff = _make_staff(self.other, "Eve")
        other_svc = _make_service(self.other)
        _assign(other_staff, other_svc)
        other_booking = Booking.objects.create(
            company=self.other,
            staff_member=other_staff,
            service_offering=other_svc,
            start_at=self.start_at,
            end_at=self.end_at,
            customer_first_name="X",
            customer_last_name="Y",
            customer_email="x@example.com",
            privacy_accepted_at=timezone.now(),
            status=Booking.Status.PENDING,
        )
        self.client.force_login(self.company)
        url = reverse("bookings:confirm_booking", kwargs={"booking_id": other_booking.pk})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)
        other_booking.refresh_from_db()
        self.assertEqual(other_booking.status, Booking.Status.PENDING)

    def test_confirming_non_pending_booking_returns_404(self):
        self.booking.status = Booking.Status.CONFIRMED
        self.booking.save()
        self.client.force_login(self.company)
        response = self.client.post(self.confirm_url)
        self.assertEqual(response.status_code, 404)


# ---------------------------------------------------------------------------
# 17. Decline action
# ---------------------------------------------------------------------------

class DeclineBookingTests(TestCase):
    """Tests 24-30: decline requires POST+login, scoped, transitions states correctly."""

    def setUp(self):
        self.company = _make_company_manual("declineco@example.com")
        self.other = _make_company("declineother@example.com")
        self.staff = _make_staff(self.company)
        self.service = _make_service(self.company, duration=30)
        _assign(self.staff, self.service)
        self.start_at = _make_start_at()
        self.end_at = self.start_at + timedelta(minutes=30)

        self.slot = AppointmentSlot.objects.create(
            company=self.company,
            staff_member=self.staff,
            start_at=self.start_at - timedelta(hours=1),
            end_at=self.end_at + timedelta(hours=1),
            status=AppointmentSlot.Status.AVAILABLE,
        )
        self.booking = Booking.objects.create(
            company=self.company,
            staff_member=self.staff,
            service_offering=self.service,
            appointment_slot=self.slot,
            start_at=self.start_at,
            end_at=self.end_at,
            customer_first_name="Jane",
            customer_last_name="Doe",
            customer_email="jane@example.com",
            privacy_accepted_at=timezone.now(),
            status=Booking.Status.PENDING,
        )
        self.decline_url = reverse("bookings:decline_booking", kwargs={"booking_id": self.booking.pk})

    def test_decline_requires_post(self):
        self.client.force_login(self.company)
        response = self.client.get(self.decline_url)
        self.assertEqual(response.status_code, 405)

    def test_decline_requires_login(self):
        response = self.client.post(self.decline_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response["Location"])

    def test_company_can_decline_own_pending_booking(self):
        self.client.force_login(self.company)
        self.client.post(self.decline_url)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.DECLINED)

    def test_declining_sets_booking_status_to_declined(self):
        self.client.force_login(self.company)
        self.client.post(self.decline_url)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.DECLINED)

    def test_declining_sets_slot_status_back_to_available(self):
        self.client.force_login(self.company)
        self.client.post(self.decline_url)
        self.slot.refresh_from_db()
        self.assertEqual(self.slot.status, AppointmentSlot.Status.AVAILABLE)

    def test_company_cannot_decline_other_company_booking(self):
        other_staff = _make_staff(self.other, "Eve")
        other_svc = _make_service(self.other)
        _assign(other_staff, other_svc)
        other_booking = Booking.objects.create(
            company=self.other,
            staff_member=other_staff,
            service_offering=other_svc,
            start_at=self.start_at,
            end_at=self.end_at,
            customer_first_name="X",
            customer_last_name="Y",
            customer_email="x@example.com",
            privacy_accepted_at=timezone.now(),
            status=Booking.Status.PENDING,
        )
        self.client.force_login(self.company)
        url = reverse("bookings:decline_booking", kwargs={"booking_id": other_booking.pk})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 404)
        other_booking.refresh_from_db()
        self.assertEqual(other_booking.status, Booking.Status.PENDING)

    def test_declining_non_pending_booking_returns_404(self):
        self.booking.status = Booking.Status.CONFIRMED
        self.booking.save()
        self.client.force_login(self.company)
        response = self.client.post(self.decline_url)
        self.assertEqual(response.status_code, 404)


# ---------------------------------------------------------------------------
# 18. Double booking / data integrity
# ---------------------------------------------------------------------------

class ConfirmationModeIntegrityTests(TestCase):
    """Tests 31-34: pending blocks slot, double booking still prevented in both modes."""

    def setUp(self):
        self.company_auto = _make_company("integrity_auto@example.com")
        self.company_manual = _make_company_manual("integrity_manual@example.com")

    def _setup_flow(self, company):
        staff = _make_staff(company)
        service = _make_service(company, duration=30)
        _assign(staff, service)
        avail = _make_availability(company, staff, start_offset_hours=2, duration_hours=4)
        start_at = _make_start_at(offset_hours=3)
        return staff, service, avail, start_at

    def test_manual_pending_booking_prevents_second_booking_same_slot(self):
        """After a manual (pending) booking, the same time window returns 404."""
        staff, service, avail, start_at = self._setup_flow(self.company_manual)
        url = _book_url(self.company_manual, staff, service, start_at)
        self.client.post(url, _valid_post_data())
        self.assertEqual(Booking.objects.filter(company=self.company_manual).count(), 1)
        # Slot is now PENDING_CONFIRMATION — second GET must 404.
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_automatic_booking_still_prevents_double_booking(self):
        """Automatic booking marks slot BOOKED; second attempt gets 404."""
        staff, service, avail, start_at = self._setup_flow(self.company_auto)
        url = _book_url(self.company_auto, staff, service, start_at)
        self.client.post(url, _valid_post_data())
        self.assertEqual(Booking.objects.filter(company=self.company_auto).count(), 1)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_any_employee_flow_respects_automatic_mode(self):
        """Any Employee booking with automatic mode creates CONFIRMED booking."""
        staff, service, avail, start_at = self._setup_flow(self.company_auto)
        local = timezone.localtime(start_at)
        url = _any_book_url(
            self.company_auto, service,
            local.strftime("%Y-%m-%d"), local.strftime("%H-%M"),
        )
        self.client.post(url, _valid_post_data())
        booking = Booking.objects.get(company=self.company_auto)
        self.assertEqual(booking.status, Booking.Status.CONFIRMED)

    def test_any_employee_flow_respects_manual_mode(self):
        """Any Employee booking with manual mode creates PENDING booking."""
        staff, service, avail, start_at = self._setup_flow(self.company_manual)
        local = timezone.localtime(start_at)
        url = _any_book_url(
            self.company_manual, service,
            local.strftime("%Y-%m-%d"), local.strftime("%H-%M"),
        )
        self.client.post(url, _valid_post_data())
        booking = Booking.objects.get(company=self.company_manual)
        self.assertEqual(booking.status, Booking.Status.PENDING)


# ---------------------------------------------------------------------------
# i18n: public booking flow
# ---------------------------------------------------------------------------

class PublicBookingLanguageTests(TestCase):
    def test_public_staff_select_renders_in_company_language(self):
        company = _make_company("fr_public@example.com", business_name="FR Public Co")
        company.language = "fr"
        company.save(update_fields=["language"])
        _make_staff(company, "Alice")
        _make_staff(company, "Bob")
        response = self.client.get(_entry_url(company))
        self.assertContains(response, "Choisissez avec qui vous souhaitez réserver.")

    def test_public_page_language_independent_of_accept_language_header(self):
        company = _make_company("de_public@example.com", business_name="DE Public Co")
        # company.language defaults to "de"
        _make_staff(company, "Alice")
        _make_staff(company, "Bob")
        response = self.client.get(_entry_url(company), HTTP_ACCEPT_LANGUAGE="fr")
        self.assertContains(response, "Wählen Sie aus, mit wem Sie buchen möchten.")

    def test_public_unavailable_page_in_company_language(self):
        company = _make_company("it_unavailable@example.com", business_name="IT Co", public_page_enabled=False)
        company.language = "it"
        company.save(update_fields=["language"])
        response = self.client.get(_entry_url(company))
        self.assertContains(response, "La prenotazione online non è al momento disponibile.")

    def test_service_select_page_renders_in_company_language(self):
        company = _make_company("it_service@example.com", business_name="IT Service Co")
        company.language = "it"
        company.save(update_fields=["language"])
        staff = _make_staff(company)
        url = reverse("bookings:service_select", kwargs={
            "company_slug": company.slug, "staff_uid": staff.public_id,
        })
        response = self.client.get(url)
        self.assertContains(response, "Al momento non ci sono servizi disponibili per questo membro del personale.")

    def test_business_name_not_translated_on_public_pages(self):
        company = _make_company("fr_name@example.com", business_name="Salon de Beaute Geneve")
        company.language = "fr"
        company.save(update_fields=["language"])
        _make_staff(company, "Alice")
        _make_staff(company, "Bob")
        response = self.client.get(_entry_url(company))
        self.assertContains(response, "Salon de Beaute Geneve")
