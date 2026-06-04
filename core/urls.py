from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("company-accounts/", include("company_accounts.urls")),
    path("availability/", include("availability.urls")),
    path("staff/", include("staff_members.urls")),
    path("services/", include("services.urls")),
    path("", include("landing.urls")),
]
