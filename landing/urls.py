from django.urls import path

from .views import (
    AboutView,
    ContactView,
    FaqView,
    FeaturesView,
    HomeView,
    LegalNoticeView,
    PricingView,
    PrivacyPolicyView,
    TermsOfServiceView,
)

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
]
