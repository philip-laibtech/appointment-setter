from django.contrib import admin

from .models import ServiceOffering, StaffServiceOffering


@admin.register(ServiceOffering)
class ServiceOfferingAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "duration_minutes", "is_active", "created_at", "updated_at")
    list_filter = ("is_active", "duration_minutes", "created_at")
    search_fields = ("name", "description", "company__email", "company__business_name")
    ordering = ("company", "-is_active", "name")


@admin.register(StaffServiceOffering)
class StaffServiceOfferingAdmin(admin.ModelAdmin):
    list_display = ("staff_member", "service_offering", "is_active", "created_at", "updated_at")
    list_filter = ("is_active", "created_at")
    search_fields = ("staff_member__name", "service_offering__name")
    ordering = ("service_offering", "staff_member")
