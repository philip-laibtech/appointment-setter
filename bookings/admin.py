from django.contrib import admin

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
        "created_at",
    )
    list_filter = ("company", "staff_member", "service_offering", "status", "created_at")
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
        "public_token",
        "created_at",
        "updated_at",
    )
