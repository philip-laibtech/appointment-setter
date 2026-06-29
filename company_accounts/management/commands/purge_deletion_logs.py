from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from company_accounts.models import AccountDeletionLog


class Command(BaseCommand):
    help = (
        "Purge AccountDeletionLog entries older than "
        "settings.DELETION_LOG_RETENTION_YEARS (storage limitation — AUDIT.md 4.7/6.2)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show how many log entries would be purged without making changes.",
        )

    def handle(self, *args, **options):
        retention_years = settings.DELETION_LOG_RETENTION_YEARS
        cutoff = timezone.now().replace(year=timezone.now().year - retention_years)

        qs = AccountDeletionLog.objects.filter(executed_at__lt=cutoff)
        count = qs.count()

        if options["dry_run"]:
            self.stdout.write(
                f"[dry-run] {count} deletion log entry(ies) would be purged "
                f"(retention: {retention_years} years, cutoff: {cutoff.date()})."
            )
            return

        if count == 0:
            self.stdout.write("No deletion log entries to purge.")
            return

        qs.delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Purged {count} deletion log entry(ies) "
                f"(retention: {retention_years} years, cutoff: {cutoff.date()})."
            )
        )
