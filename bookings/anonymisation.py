"""Shared customer-PII anonymisation logic for Booking records.

Used by both the scheduled `anonymise_old_bookings` command (30-day
retention) and the customer-facing self-service erasure view (immediate,
on request — GDPR Art. 17). Keeping the field list in one place means the
two paths can never anonymise a booking differently.
"""
from django.db.models import CharField, Value
from django.db.models.functions import Cast, Concat
from django.utils import timezone

# Single placeholder for every cleared PII field — avoids the inconsistency
# of "[deleted]" for names but "" for email/phone/message (AUDIT.md 5.2).
PII_PLACEHOLDER = "[deleted]"


def anonymised_field_values(now=None):
    """Field values to apply when anonymising a Booking's customer PII.

    Excludes public_token — that field is unique, so a bulk update needs a
    per-row expression (see anonymised_public_token_expression) rather than
    one constant shared by every row.
    """
    return {
        "customer_first_name": PII_PLACEHOLDER,
        "customer_last_name": PII_PLACEHOLDER,
        "customer_email": PII_PLACEHOLDER,
        "customer_phone": PII_PLACEHOLDER,
        "customer_message": PII_PLACEHOLDER,
        "anonymized_at": now or timezone.now(),
    }


def anonymised_public_token_expression():
    """A per-row unique replacement for public_token (satisfies its unique constraint).

    The token is useless after anonymisation anyway (AUDIT.md 5.1) — this just
    clears it to a non-guessable-lookup, still-unique value instead of leaving
    the original secret token (and its lookup ability) alive indefinitely.
    """
    return Concat(Value("anon-"), Cast("pk", output_field=CharField()))


def anonymise_booking_instance(booking, now=None):
    """Anonymise a single Booking instance in place and save it.

    Used by the customer self-service erasure view, where only one row is
    affected and an ORM expression for public_token isn't needed.
    """
    now = now or timezone.now()
    for field, value in anonymised_field_values(now).items():
        setattr(booking, field, value)
    booking.public_token = f"anon-{booking.pk}"
    booking.save(update_fields=[*anonymised_field_values(now).keys(), "public_token"])
    return booking
