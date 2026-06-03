from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import CompanyAccount


@admin.register(CompanyAccount)
class CompanyAccountAdmin(UserAdmin):
    model = CompanyAccount
    list_display = ("email", "business_name", "slug", "public_page_enabled", "timezone", "created_at", "updated_at")
    list_filter = ("public_page_enabled", "is_staff", "is_active")
    search_fields = ("email", "business_name")
    ordering = ("email",)
    readonly_fields = ("created_at", "updated_at", "slug")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Company", {"fields": ("business_name", "slug", "timezone", "public_page_enabled")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "business_name", "password1", "password2", "is_staff", "is_active"),
        }),
    )
