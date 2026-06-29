"""Internal email notification services for the booking lifecycle.

These functions are called from `bookings` after a transaction has
committed. They are not exposed via any view or public endpoint.
"""

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import translation

from bookings.models import Booking

logger = logging.getLogger(__name__)


def _send_template_email(template_prefix, to_email, context, language):
    with translation.override(language):
        subject = render_to_string(
            f"notifications/emails/{template_prefix}_subject.txt", context
        ).strip()
        body = render_to_string(
            f"notifications/emails/{template_prefix}_body.txt", context
        )
    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[to_email],
        )
    except Exception:
        logger.exception(
            "Failed to send notification email (template=%s)", template_prefix
        )


def send_booking_request_received_to_customer(booking):
    _send_template_email(
        "customer_booking_request_received",
        booking.customer_email,
        {"booking": booking},
        booking.company.language,
    )


def send_booking_confirmed_to_customer(booking):
    _send_template_email(
        "customer_booking_confirmed",
        booking.customer_email,
        {"booking": booking},
        booking.company.language,
    )


def send_booking_declined_to_customer(booking):
    _send_template_email(
        "customer_booking_declined",
        booking.customer_email,
        {"booking": booking},
        booking.company.language,
    )


def send_booking_cancelled_to_customer(booking):
    _send_template_email(
        "customer_booking_cancelled",
        booking.customer_email,
        {"booking": booking},
        booking.company.language,
    )


def send_new_booking_to_company(booking):
    _send_template_email(
        "company_new_booking",
        booking.company.email,
        {"booking": booking},
        booking.company.language,
    )


def send_new_booking_request_to_company(booking):
    _send_template_email(
        "company_new_booking_request",
        booking.company.email,
        {"booking": booking},
        booking.company.language,
    )


def send_privacy_policy_update_to_customer(booking, privacy_policy_url):
    """Notify a customer with an upcoming booking that the privacy policy changed.

    Ongoing transparency obligation (Art. 13/14) — customers who booked under
    an older policy version are told about material changes affecting them.
    Triggered manually via `python manage.py notify_privacy_policy_change`
    after bumping settings.PRIVACY_POLICY_VERSION (AUDIT.md 6.5).
    """
    _send_template_email(
        "customer_privacy_policy_updated",
        booking.customer_email,
        {"booking": booking, "privacy_policy_url": privacy_policy_url},
        booking.company.language,
    )


def send_anonymisation_summary_to_company(company, count):
    """Notify a company how many of its bookings were just anonymised.

    Optional transparency measure (AUDIT.md 6.1) — companies are the data
    controller for their customers' booking data, so they're told when it
    transitions to anonymised state, even though no action is required.
    """
    _send_template_email(
        "company_anonymisation_summary",
        company.email,
        {"company": company, "count": count},
        company.language,
    )


def send_booking_created_notifications(booking):
    """Send the appropriate customer/company emails after a booking is created."""
    if booking.status == Booking.Status.PENDING:
        send_booking_request_received_to_customer(booking)
        send_new_booking_request_to_company(booking)
    elif booking.status == Booking.Status.CONFIRMED:
        send_booking_confirmed_to_customer(booking)
        send_new_booking_to_company(booking)
