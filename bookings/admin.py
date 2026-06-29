import csv

from django.contrib import admin
from django.http import HttpResponse

from .models import Booking


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = (
        "company",
        "staff_member",
        "service_offering",
        "start_at",
        "end_at",
        "customer_email",
        "status",
        "privacy_policy_version",
        "created_at",
    )
    list_filter = (
        "company",
        "staff_member",
        "service_offering",
        "status",
        "privacy_policy_version",
        "created_at",
    )
    search_fields = (
        "customer_first_name",
        "customer_last_name",
        "customer_email",
        "company__email",
        "company__business_name",
        "staff_member__name",
        "service_offering__name",
    )
    ordering = ("-start_at",)
    readonly_fields = (
        "company",
        "staff_member",
        "service_offering",
        "appointment_slot",
        "start_at",
        "end_at",
        "customer_first_name",
        "customer_last_name",
        "customer_email",
        "customer_phone",
        "customer_message",
        "privacy_accepted_at",
        "privacy_policy_version",
        "anonymized_at",
        "public_token",
        "created_at",
        "updated_at",
    )
    actions = ["export_consent_records_as_csv"]

    @admin.action(description="Export consent records (CSV) for selected bookings")
    def export_consent_records_as_csv(self, request, queryset):
        """GDPR Art. 7 — lets an operator demonstrate when/which policy version a customer accepted."""
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="consent_records.csv"'
        writer = csv.writer(response)
        writer.writerow(["booking_id", "company", "customer_email", "privacy_accepted_at", "privacy_policy_version"])
        for booking in queryset:
            writer.writerow([
                booking.pk,
                booking.company.business_name,
                booking.customer_email,
                booking.privacy_accepted_at.isoformat(),
                booking.privacy_policy_version,
            ])
        return response
