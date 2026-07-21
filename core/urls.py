from django.conf import settings
from django.conf.urls.i18n import i18n_patterns
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.shortcuts import render
from django.urls import path, include
from django.views.defaults import permission_denied as _default_403
from django_otp.admin import OTPAdminSite
from django_ratelimit.exceptions import Ratelimited

from core.views import health_check
from landing.sitemaps import StaticViewSitemap
from landing.views import RobotsTxtView

# Require a verified OTP device to use the admin, regardless of the optional
# 2FA setting for regular company accounts (admin grants full PII access).
admin.site.__class__ = OTPAdminSite


def handler403(request, exception=None):
    if isinstance(exception, Ratelimited):
        return render(request, "429.html", status=429)
    return _default_403(request, exception)


urlpatterns = [
    path("healthz/", health_check),
    path(settings.DJANGO_ADMIN_URL, admin.site.urls),
    path("captcha/", include("captcha.urls")),
    path("", include("company_accounts.urls")),
    path("availability/", include("availability.urls")),
    path("staff/", include("staff_members.urls")),
    path("services/", include("services.urls")),
    path("", include("bookings.urls")),
    path("robots.txt", RobotsTxtView.as_view(), name="robots_txt"),
    path(
        "sitemap.xml",
        sitemap,
        {"sitemaps": {"static": StaticViewSitemap}},
        name="sitemap",
    ),
] + i18n_patterns(
    path("", include("landing.urls")),
    prefix_default_language=False,
)
