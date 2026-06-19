import logging

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger(__name__)
from django.db import transaction
from django.utils import timezone

from availability.models import AppointmentSlot
from bookings.models import Booking
from company_accounts.models import AccountDeletionLog, CompanyAccount, DeletionRequest


class Command(BaseCommand):
    help = (
        "Permanently delete a company account and all associated data after "
        "phone verification has been completed. Always do a --dry-run first."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            required=True,
            help="Email address of the company account to delete.",
        )
        parser.add_argument(
            "--confirmed-by",
            required=True,
            dest="confirmed_by",
            help="Name or identifier of the support agent who verified the account holder by phone.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without making any changes.",
        )

    def handle(self, *args, **options):
        email = options["email"].strip().lower()
        confirmed_by = options["confirmed_by"].strip()
        dry_run = options["dry_run"]

        try:
            company = CompanyAccount.objects.get(email__iexact=email)
        except CompanyAccount.DoesNotExist:
            raise CommandError(f'No company account found with email "{email}".')

        booking_count = Booking.objects.filter(company=company).count()
        slot_count = AppointmentSlot.objects.filter(company=company).count()
        staff_count = company.staff_members.count()
        service_count = company.service_offerings.count()

        deletion_request = getattr(company, "deletion_request", None)

        self.stdout.write("")
        self.stdout.write(f"  Business : {company.business_name}")
        self.stdout.write(f"  Email    : {company.email}")
        self.stdout.write(f"  Phone    : {company.phone or '(none)'}")
        self.stdout.write(f"  Request  : {deletion_request.token if deletion_request else '(no request on file)'}")
        self.stdout.write("")
        self.stdout.write("  Records that will be permanently deleted:")
        self.stdout.write(f"    {booking_count} booking(s)")
        self.stdout.write(f"    {slot_count} appointment slot(s)")
        self.stdout.write(f"    {staff_count} staff member(s) (+ their service assignments)")
        self.stdout.write(f"    {service_count} service(s)")
        self.stdout.write(f"    1 company account")
        self.stdout.write("")

        if dry_run:
            self.stdout.write(self.style.WARNING("[dry-run] No changes made."))
            return

        confirm = input("Type the business name exactly to confirm deletion: ").strip()
        if confirm != company.business_name:
            raise CommandError("Business name did not match. Aborting.")

        with transaction.atomic():
            log = AccountDeletionLog.objects.create(
                company_email_hash=AccountDeletionLog.hash_email(company.email),
                business_name=company.business_name,
                deletion_token=deletion_request.token if deletion_request else "",
                requested_at=deletion_request.requested_at if deletion_request else timezone.now(),
                confirmed_by=confirmed_by,
            )

            Booking.objects.filter(company=company).delete()
            AppointmentSlot.objects.filter(company=company).delete()
            company.delete()

        farewell_email = email
        support_email = settings.SUPPORT_EMAIL
        subject = f"Your account has been deleted — {log.business_name}"
        body = (
            f"Hello,\n\n"
            f"This confirms that your Appointment Setter account ({log.business_name}) "
            f"and all associated data have been permanently deleted as requested.\n\n"
            f"Reference: {log.deletion_token or 'N/A'}\n"
            f"Deleted at: {log.executed_at.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
            f"If you did not request this, please contact us immediately at {support_email}.\n\n"
            f"Appointment Setter"
        )
        try:
            send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [farewell_email])
        except Exception:
            logger.exception("Failed to send farewell confirmation email to %s for company %s", farewell_email, log.pk)

        self.stdout.write(self.style.SUCCESS(
            f"Deleted company \"{log.business_name}\". "
            f"Audit log entry created (id={log.pk})."
        ))
