from django.contrib import admin
from django.shortcuts import render
from django.urls import path, include
from django.views.defaults import permission_denied as _default_403
from django_ratelimit.exceptions import Ratelimited


def handler403(request, exception=None):
    if isinstance(exception, Ratelimited):
        return render(request, "429.html", status=429)
    return _default_403(request, exception)


urlpatterns = [
    path("admin/", admin.site.urls),
    path("captcha/", include("captcha.urls")),
    path("", include("company_accounts.urls")),
    path("availability/", include("availability.urls")),
    path("staff/", include("staff_members.urls")),
    path("services/", include("services.urls")),
    path("", include("bookings.urls")),
    path("", include("landing.urls")),
]
