from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from bookings.models import Booking


class Command(BaseCommand):
    help = (
        "Anonymise customer PII on bookings whose appointment ended more than "
        "CUSTOMER_DATA_RETENTION_DAYS days ago. Booking structure is preserved."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print how many bookings would be anonymised without making changes.",
        )

    def handle(self, *args, **options):
        retention_days = settings.CUSTOMER_DATA_RETENTION_DAYS
        cutoff = timezone.now() - timedelta(days=retention_days)

        qs = Booking.objects.filter(end_at__lt=cutoff, anonymized_at__isnull=True)
        count = qs.count()

        if options["dry_run"]:
            self.stdout.write(
                f"[dry-run] {count} booking(s) would be anonymised "
                f"(retention: {retention_days} days, cutoff: {cutoff.date()})."
            )
            return

        if count == 0:
            self.stdout.write("No bookings to anonymise.")
            return

        now = timezone.now()
        qs.update(
            customer_first_name="[deleted]",
            customer_last_name="[deleted]",
            customer_email="",
            customer_phone="",
            customer_message="",
            anonymized_at=now,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Anonymised {count} booking(s) "
                f"(retention: {retention_days} days, cutoff: {cutoff.date()})."
            )
        )
