import secrets

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


def _generate_public_token():
    return secrets.token_urlsafe(32)


class Booking(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        CANCELLED = "cancelled", "Cancelled"
        DECLINED = "declined", "Declined"

    company = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="bookings",
    )
    staff_member = models.ForeignKey(
        "staff_members.StaffMember",
        on_delete=models.PROTECT,
        related_name="bookings",
    )
    service_offering = models.ForeignKey(
        "services.ServiceOffering",
        on_delete=models.PROTECT,
        related_name="bookings",
    )
    # Reference to the availability window this booking falls within.
    # Nullable: the window may be deleted/restructured without losing the booking record.
    appointment_slot = models.ForeignKey(
        "availability.AppointmentSlot",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bookings",
    )
    # The actual booked time window, carved from the availability window above.
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()

    customer_first_name = models.CharField(max_length=100)
    customer_last_name = models.CharField(max_length=100)
    customer_email = models.EmailField()
    customer_phone = models.CharField(max_length=30, blank=True, default="")
    customer_message = models.TextField(blank=True, default="")
    privacy_accepted_at = models.DateTimeField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.CONFIRMED,
    )
    public_token = models.CharField(max_length=64, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["company"]),
            models.Index(fields=["staff_member"]),
            models.Index(fields=["service_offering"]),
            models.Index(fields=["status"]),
            models.Index(fields=["start_at"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["public_token"]),
        ]

    def save(self, *args, **kwargs):
        if not self.public_token:
            self.public_token = _generate_public_token()
        super().save(*args, **kwargs)

    def clean(self):
        errors = {}
        if self.staff_member_id and self.company_id:
            if self.staff_member.company_id != self.company_id:
                errors["staff_member"] = "Staff member does not belong to this company."
        if self.service_offering_id and self.company_id:
            if self.service_offering.company_id != self.company_id:
                errors["service_offering"] = "Service does not belong to this company."
        if self.appointment_slot_id and self.staff_member_id:
            if self.appointment_slot.staff_member_id != self.staff_member_id:
                errors["appointment_slot"] = "Slot does not belong to this staff member."
        if self.start_at and self.end_at and self.start_at >= self.end_at:
            errors["end_at"] = "End time must be after start time."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return (
            f"{self.customer_first_name} {self.customer_last_name} "
            f"— {self.service_offering} "
            f"[{self.start_at:%Y-%m-%d %H:%M}]"
        )
