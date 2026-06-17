from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class AppointmentSlot(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "available", _("Available")
        BOOKED = "booked", _("Booked")
        BLOCKED = "blocked", _("Blocked")
        PENDING_CONFIRMATION = "pending_confirmation", _("Pending Confirmation")

    company = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="appointment_slots",
    )
    staff_member = models.ForeignKey(
        "staff_members.StaffMember",
        on_delete=models.PROTECT,
        related_name="appointment_slots",
        null=True,
        blank=True,
    )
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.AVAILABLE,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Open Hours"
        verbose_name_plural = "Open Hours"
        ordering = ["start_at"]
        indexes = [
            models.Index(fields=["company", "start_at"]),
            models.Index(fields=["company", "status"]),
            models.Index(fields=["company", "start_at", "status"]),
            models.Index(fields=["staff_member", "start_at"]),
        ]

    def __str__(self):
        staff = self.staff_member.name if self.staff_member_id else "Unassigned"
        return f"{self.company} / {staff} — {self.start_at:%Y-%m-%d %H:%M} to {self.end_at:%H:%M} [{self.status}]"
