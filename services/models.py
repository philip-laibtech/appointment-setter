from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class ServiceOffering(models.Model):
    company = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="service_offerings",
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    duration_minutes = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_active", "name"]
        indexes = [
            models.Index(fields=["company"]),
            models.Index(fields=["is_active"]),
            models.Index(fields=["duration_minutes"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.duration_minutes} min)"


class StaffServiceOffering(models.Model):
    staff_member = models.ForeignKey(
        "staff_members.StaffMember",
        on_delete=models.CASCADE,
        related_name="staff_service_offerings",
    )
    service_offering = models.ForeignKey(
        ServiceOffering,
        on_delete=models.CASCADE,
        related_name="staff_service_offerings",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["staff_member", "service_offering"],
                name="unique_staff_service_offering",
            )
        ]

    def clean(self):
        if (
            self.staff_member_id
            and self.service_offering_id
            and self.staff_member.company_id != self.service_offering.company_id
        ):
            raise ValidationError(
                "Staff member and service offering must belong to the same company."
            )

    def __str__(self):
        return f"{self.staff_member} — {self.service_offering}"
