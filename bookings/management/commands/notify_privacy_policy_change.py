from django.conf import settings
from django.core.management.base import BaseCommand
from django.urls import reverse
from django.utils import timezone

from bookings.models import Booking
from notifications.services import send_privacy_policy_update_to_customer


class Command(BaseCommand):
    help = (
        "Notify customers with an active upcoming booking that the Privacy Policy "
        "has changed. Run manually once after bumping settings.PRIVACY_POLICY_VERSION "
        "(AUDIT.md 6.5). One email per booking — a customer with several upcoming "
        "bookings receives one notification per booking."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--site-url",
            required=True,
            help='Absolute origin to link to the privacy policy, e.g. "https://yourdomain.com".',
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show how many customers would be notified without sending anything.",
        )

    def handle(self, *args, **options):
        privacy_policy_url = options["site_url"].rstrip("/") + reverse("landing:privacy_policy")

        qs = Booking.objects.filter(
            status__in=[Booking.Status.CONFIRMED, Booking.Status.PENDING],
            start_at__gte=timezone.now(),
            anonymized_at__isnull=True,
        ).select_related("company", "service_offering", "staff_member")
        count = qs.count()

        if options["dry_run"]:
            self.stdout.write(f"[dry-run] {count} customer(s) would be notified.")
            return

        for booking in qs:
            send_privacy_policy_update_to_customer(booking, privacy_policy_url)

        self.stdout.write(self.style.SUCCESS(f"Notified {count} customer(s) of the privacy policy update."))
