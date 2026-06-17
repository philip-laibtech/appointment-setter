from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from captcha.models import CaptchaStore

from availability.models import AppointmentSlot
from bookings.models import Booking
from services.models import ServiceOffering, StaffServiceOffering
from staff_members.models import StaffMember

from . import services

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_company(email, business_name="Test Co", confirmation_mode=None):
    company = User.objects.create_user(
        email=email,
        password="testpassword123",
        business_name=business_name,
    )
    if confirmation_mode:
        company.booking_confirmation_mode = confirmation_mode
        company.save(update_fields=["booking_confirmation_mode"])
    return company


def _make_staff(company, name="Alice"):
    return StaffMember.objects.create(company=company, name=name, is_active=True)


def _make_service(company, name="Consultation", duration=30):
    return ServiceOffering.objects.create(
        company=company, name=name, duration_minutes=duration, is_active=True,
    )


def _make_booking(company, staff, service, status=Booking.Status.CONFIRMED):
    now = timezone.now()
    return Booking.objects.create(
        company=company,
        staff_member=staff,
        service_offering=service,
        start_at=now + timedelta(hours=2),
        end_at=now + timedelta(hours=2, minutes=service.duration_minutes),
        customer_first_name="Jane",
        customer_last_name="Doe",
        customer_email="jane@example.com",
        customer_phone="555-1234",
        customer_message="Looking forward to it.",
        privacy_accepted_at=now,
        status=status,
    )


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class NotificationServiceTests(TestCase):
    def setUp(self):
        mail.outbox = []
        self.company = _make_company("company@example.com")
        self.staff = _make_staff(self.company)
        self.service = _make_service(self.company)

    def test_customer_request_received_email_sent_for_pending_booking(self):
        booking = _make_booking(self.company, self.staff, self.service, status=Booking.Status.PENDING)
        services.send_booking_request_received_to_customer(booking)

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["jane@example.com"])
        self.assertTrue(message.subject)

    def test_customer_confirmed_email_sent_for_confirmed_booking(self):
        booking = _make_booking(self.company, self.staff, self.service, status=Booking.Status.CONFIRMED)
        services.send_booking_confirmed_to_customer(booking)

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["jane@example.com"])
        self.assertTrue(message.subject)

    def test_company_new_booking_email_sent_for_confirmed_booking(self):
        booking = _make_booking(self.company, self.staff, self.service, status=Booking.Status.CONFIRMED)
        services.send_new_booking_to_company(booking)

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["company@example.com"])
        self.assertTrue(message.subject)

    def test_company_new_booking_request_email_sent_for_pending_booking(self):
        booking = _make_booking(self.company, self.staff, self.service, status=Booking.Status.PENDING)
        services.send_new_booking_request_to_company(booking)

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["company@example.com"])
        self.assertTrue(message.subject)

    def test_customer_declined_email_sent(self):
        booking = _make_booking(self.company, self.staff, self.service, status=Booking.Status.DECLINED)
        services.send_booking_declined_to_customer(booking)

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["jane@example.com"])
        self.assertTrue(message.subject)

    def test_customer_email_does_not_go_to_company(self):
        booking = _make_booking(self.company, self.staff, self.service, status=Booking.Status.CONFIRMED)
        services.send_booking_confirmed_to_customer(booking)

        self.assertNotIn("company@example.com", mail.outbox[0].to)

    def test_company_email_does_not_go_to_customer(self):
        booking = _make_booking(self.company, self.staff, self.service, status=Booking.Status.CONFIRMED)
        services.send_new_booking_to_company(booking)

        self.assertNotIn("jane@example.com", mail.outbox[0].to)

    def test_created_notifications_for_pending_booking(self):
        booking = _make_booking(self.company, self.staff, self.service, status=Booking.Status.PENDING)
        services.send_booking_created_notifications(booking)

        self.assertEqual(len(mail.outbox), 2)
        recipients = {tuple(m.to) for m in mail.outbox}
        self.assertIn(("jane@example.com",), recipients)
        self.assertIn(("company@example.com",), recipients)

    def test_created_notifications_for_confirmed_booking(self):
        booking = _make_booking(self.company, self.staff, self.service, status=Booking.Status.CONFIRMED)
        services.send_booking_created_notifications(booking)

        self.assertEqual(len(mail.outbox), 2)
        recipients = {tuple(m.to) for m in mail.outbox}
        self.assertIn(("jane@example.com",), recipients)
        self.assertIn(("company@example.com",), recipients)

    def test_created_notifications_does_not_send_declined_email(self):
        booking = _make_booking(self.company, self.staff, self.service, status=Booking.Status.DECLINED)
        services.send_booking_created_notifications(booking)

        self.assertEqual(len(mail.outbox), 0)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class NotificationPrivacyTests(TestCase):
    def setUp(self):
        mail.outbox = []
        self.company = _make_company("company2@example.com")
        self.staff = _make_staff(self.company)
        self.service = _make_service(self.company)

    def test_customer_email_does_not_include_internal_ids(self):
        booking = _make_booking(self.company, self.staff, self.service, status=Booking.Status.CONFIRMED)
        services.send_booking_confirmed_to_customer(booking)

        body = mail.outbox[0].body
        self.assertNotIn(booking.public_token, body)

    def test_customer_declined_email_does_not_include_customer_message(self):
        booking = _make_booking(self.company, self.staff, self.service, status=Booking.Status.DECLINED)
        services.send_booking_declined_to_customer(booking)

        body = mail.outbox[0].body
        self.assertNotIn(booking.customer_message, body)

    def test_company_email_includes_customer_contact_details(self):
        booking = _make_booking(self.company, self.staff, self.service, status=Booking.Status.CONFIRMED)
        services.send_new_booking_to_company(booking)

        body = mail.outbox[0].body
        self.assertIn(booking.customer_email, body)
        self.assertIn(booking.customer_phone, body)

    def test_no_email_sent_to_other_company(self):
        other_company = _make_company("other@example.com")
        booking = _make_booking(self.company, self.staff, self.service, status=Booking.Status.CONFIRMED)
        services.send_new_booking_to_company(booking)

        self.assertNotIn(other_company.email, mail.outbox[0].to)


# ---------------------------------------------------------------------------
# i18n: notification emails
# ---------------------------------------------------------------------------

@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class NotificationLanguageTests(TestCase):
    def setUp(self):
        mail.outbox = []

    def _make_company_with_language(self, email, language, business_name="Test Co"):
        company = _make_company(email, business_name=business_name)
        company.language = language
        company.save(update_fields=["language"])
        return company

    def test_customer_request_received_email_in_german_by_default(self):
        company = self._make_company_with_language("de_company@example.com", "de")
        staff = _make_staff(company)
        service = _make_service(company)
        booking = _make_booking(company, staff, service, status=Booking.Status.PENDING)
        services.send_booking_request_received_to_customer(booking)

        message = mail.outbox[0]
        self.assertEqual(message.subject, "Ihre Buchungsanfrage wurde erhalten")
        self.assertIn("Hallo Jane,", message.body)

    def test_customer_confirmed_email_in_french(self):
        company = self._make_company_with_language("fr_company@example.com", "fr")
        staff = _make_staff(company)
        service = _make_service(company)
        booking = _make_booking(company, staff, service, status=Booking.Status.CONFIRMED)
        services.send_booking_confirmed_to_customer(booking)

        message = mail.outbox[0]
        self.assertEqual(message.subject, "Votre réservation est confirmée")
        self.assertIn("Bonjour Jane,", message.body)

    def test_customer_declined_email_in_italian(self):
        company = self._make_company_with_language("it_company@example.com", "it")
        staff = _make_staff(company)
        service = _make_service(company)
        booking = _make_booking(company, staff, service, status=Booking.Status.DECLINED)
        services.send_booking_declined_to_customer(booking)

        message = mail.outbox[0]
        self.assertEqual(message.subject, "La tua richiesta di prenotazione è stata rifiutata")
        self.assertIn("Ciao Jane,", message.body)

    def test_customer_cancelled_email_in_company_language(self):
        company = self._make_company_with_language("fr_cancel@example.com", "fr")
        staff = _make_staff(company)
        service = _make_service(company)
        booking = _make_booking(company, staff, service, status=Booking.Status.CONFIRMED)
        services.send_booking_cancelled_to_customer(booking)

        message = mail.outbox[0]
        self.assertEqual(message.subject, "Votre rendez-vous a été annulé")

    def test_company_new_booking_email_in_company_language(self):
        company = self._make_company_with_language("it_newbooking@example.com", "it")
        staff = _make_staff(company)
        service = _make_service(company)
        booking = _make_booking(company, staff, service, status=Booking.Status.CONFIRMED)
        services.send_new_booking_to_company(booking)

        message = mail.outbox[0]
        self.assertIn("Servizio:", message.body)

    def test_company_new_booking_request_email_in_company_language(self):
        company = self._make_company_with_language("fr_newrequest@example.com", "fr")
        staff = _make_staff(company)
        service = _make_service(company)
        booking = _make_booking(company, staff, service, status=Booking.Status.PENDING)
        services.send_new_booking_request_to_company(booking)

        message = mail.outbox[0]
        self.assertIn("Service :", message.body)

    def test_customer_provided_name_not_translated_in_email(self):
        company = self._make_company_with_language("fr_customername@example.com", "fr")
        staff = _make_staff(company)
        service = _make_service(company)
        booking = _make_booking(company, staff, service, status=Booking.Status.CONFIRMED)
        booking.customer_first_name = "Pending"
        booking.save(update_fields=["customer_first_name"])
        services.send_booking_confirmed_to_customer(booking)

        message = mail.outbox[0]
        # "Pending" is a customer-provided name and must not be translated to "En attente"
        self.assertIn("Bonjour Pending,", message.body)

    def test_active_language_restored_after_sending_email(self):
        from django.utils import translation

        translation.activate("de")
        company = self._make_company_with_language("fr_restore@example.com", "fr")
        staff = _make_staff(company)
        service = _make_service(company)
        booking = _make_booking(company, staff, service, status=Booking.Status.CONFIRMED)
        services.send_booking_confirmed_to_customer(booking)

        self.assertEqual(translation.get_language(), "de")


# ---------------------------------------------------------------------------
# Booking integration tests
# ---------------------------------------------------------------------------

@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class BookingNotificationIntegrationTests(TestCase):
    def setUp(self):
        mail.outbox = []

    def _post_booking(self, company, staff, service, start_at):
        local = timezone.localtime(start_at)
        url = reverse(
            "bookings:book",
            kwargs={
                "company_slug": company.slug,
                "staff_uid": staff.public_id,
                "service_uid": service.public_id,
                "date": local.strftime("%Y-%m-%d"),
                "start_time": local.strftime("%H-%M"),
            },
        )
        captcha = CaptchaStore.objects.create(challenge="1234", response="1234")
        data = {
            "customer_first_name": "Jane",
            "customer_last_name": "Doe",
            "customer_email": "jane@example.com",
            "customer_phone": "",
            "customer_message": "",
            "privacy_accepted": "on",
            "website": "",
            "captcha_0": captcha.hashkey,
            "captcha_1": "1234",
        }
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(url, data)

    def _make_slot_and_assignment(self, company, staff, service, start_at):
        end_at = start_at + timedelta(minutes=service.duration_minutes)
        AppointmentSlot.objects.create(
            company=company,
            staff_member=staff,
            start_at=start_at - timedelta(hours=1),
            end_at=end_at + timedelta(hours=1),
            status=AppointmentSlot.Status.AVAILABLE,
        )
        StaffServiceOffering.objects.create(
            staff_member=staff, service_offering=service, is_active=True,
        )

    def _next_start_at(self):
        now = timezone.now()
        t = now + timedelta(hours=2)
        minutes = (t.minute // 15 + 1) * 15
        return t.replace(minute=0, second=0, microsecond=0) + timedelta(minutes=minutes)

    def test_automatic_booking_sends_customer_confirmed_and_company_new_booking(self):
        company = _make_company(
            "auto@example.com",
            confirmation_mode=User.BookingConfirmationMode.AUTOMATIC,
        )
        staff = _make_staff(company)
        service = _make_service(company)
        start_at = self._next_start_at()
        self._make_slot_and_assignment(company, staff, service, start_at)

        response = self._post_booking(company, staff, service, start_at)
        self.assertEqual(response.status_code, 302)

        booking = Booking.objects.get(company=company)
        self.assertEqual(booking.status, Booking.Status.CONFIRMED)

        self.assertEqual(len(mail.outbox), 2)
        subjects_to = {tuple(m.to): m.subject for m in mail.outbox}
        self.assertIn(("jane@example.com",), subjects_to)
        self.assertIn(("auto@example.com",), subjects_to)

    def test_manual_booking_sends_customer_request_and_company_request(self):
        company = _make_company(
            "manual@example.com",
            confirmation_mode=User.BookingConfirmationMode.MANUAL,
        )
        staff = _make_staff(company)
        service = _make_service(company)
        start_at = self._next_start_at()
        self._make_slot_and_assignment(company, staff, service, start_at)

        response = self._post_booking(company, staff, service, start_at)
        self.assertEqual(response.status_code, 302)

        booking = Booking.objects.get(company=company)
        self.assertEqual(booking.status, Booking.Status.PENDING)

        self.assertEqual(len(mail.outbox), 2)
        recipients = {tuple(m.to) for m in mail.outbox}
        self.assertIn(("jane@example.com",), recipients)
        self.assertIn(("manual@example.com",), recipients)

    def test_invalid_form_does_not_send_email(self):
        company = _make_company(
            "invalid@example.com",
            confirmation_mode=User.BookingConfirmationMode.AUTOMATIC,
        )
        staff = _make_staff(company)
        service = _make_service(company)
        start_at = self._next_start_at()
        self._make_slot_and_assignment(company, staff, service, start_at)

        local = timezone.localtime(start_at)
        url = reverse(
            "bookings:book",
            kwargs={
                "company_slug": company.slug,
                "staff_uid": staff.public_id,
                "service_uid": service.public_id,
                "date": local.strftime("%Y-%m-%d"),
                "start_time": local.strftime("%H-%M"),
            },
        )
        # Missing required fields -> form invalid.
        response = self.client.post(url, {"customer_first_name": "Jane"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)

    def test_manual_confirm_sends_customer_confirmed_email(self):
        company = _make_company(
            "confirm@example.com",
            confirmation_mode=User.BookingConfirmationMode.MANUAL,
        )
        staff = _make_staff(company)
        service = _make_service(company)
        booking = _make_booking(company, staff, service, status=Booking.Status.PENDING)

        self.client.force_login(company)
        url = reverse("bookings:confirm_booking", kwargs={"booking_id": booking.pk})
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(url)
        self.assertEqual(response.status_code, 302)

        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CONFIRMED)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["jane@example.com"])

    def test_manual_decline_sends_customer_declined_email(self):
        company = _make_company(
            "decline@example.com",
            confirmation_mode=User.BookingConfirmationMode.MANUAL,
        )
        staff = _make_staff(company)
        service = _make_service(company)
        booking = _make_booking(company, staff, service, status=Booking.Status.PENDING)

        self.client.force_login(company)
        url = reverse("bookings:decline_booking", kwargs={"booking_id": booking.pk})
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(url)
        self.assertEqual(response.status_code, 302)

        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.DECLINED)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["jane@example.com"])
