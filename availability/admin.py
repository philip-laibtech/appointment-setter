from django.contrib import admin

from .models import AppointmentSlot


@admin.register(AppointmentSlot)
class AppointmentSlotAdmin(admin.ModelAdmin):
    list_display = ("company", "start_at", "end_at", "status", "created_at", "updated_at")
    list_filter = ("status", "start_at")
    search_fields = ("company__email", "company__business_name")
    ordering = ("start_at",)
    readonly_fields = ("created_at", "updated_at")
