from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Count
from django.utils import timezone

from bookings.anonymisation import anonymised_field_values, anonymised_public_token_expression
from bookings.models import Booking
from company_accounts.models import CompanyAccount
from notifications.services import send_anonymisation_summary_to_company


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

        # Snapshot per-company counts before the update for the optional
        # transparency notification (AUDIT.md 6.1).
        per_company_counts = dict(
            qs.values("company_id").annotate(count=Count("id")).values_list("company_id", "count")
        )

        now = timezone.now()
        qs.update(
            **anonymised_field_values(now),
            public_token=anonymised_public_token_expression(),
        )

        companies = CompanyAccount.objects.in_bulk(per_company_counts.keys())
        for company_id, company_count in per_company_counts.items():
            company = companies.get(company_id)
            if company:
                send_anonymisation_summary_to_company(company, company_count)

        self.stdout.write(
            self.style.SUCCESS(
                f"Anonymised {count} booking(s) "
                f"(retention: {retention_days} days, cutoff: {cutoff.date()})."
            )
        )
