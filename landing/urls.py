from django.urls import path

from .views import (
    AboutView,
    ContactView,
    DocumentationView,
    FaqView,
    FeaturesView,
    HomeView,
    LegalNoticeView,
    PricingView,
    PrivacyPolicyView,
    TermsOfServiceView,
)

# Only the language-prefixable marketing/legal pages live here — this
# urlconf is wrapped in i18n_patterns() by core/urls.py. robots.txt and
# sitemap.xml must stay at a single, unprefixed root path, so they're
# registered directly in core/urls.py instead.
app_name = "landing"

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("privacy/", PrivacyPolicyView.as_view(), name="privacy_policy"),
    path("terms/", TermsOfServiceView.as_view(), name="terms_of_service"),
    path("legal/", LegalNoticeView.as_view(), name="legal_notice"),
    path("pricing/", PricingView.as_view(), name="pricing"),
    path("features/", FeaturesView.as_view(), name="features"),
    path("about/", AboutView.as_view(), name="about"),
    path("contact/", ContactView.as_view(), name="contact"),
    path("faq/", FaqView.as_view(), name="faq"),
    path("docs/", DocumentationView.as_view(), name="documentation"),
]
