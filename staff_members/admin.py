from django.contrib import admin

from .models import StaffMember


@admin.register(StaffMember)
class StaffMemberAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "email", "phone", "is_active", "created_at")
    list_filter = ("is_active", "company")
    search_fields = ("name", "email")
    ordering = ("company", "name")
