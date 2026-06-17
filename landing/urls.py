from django.urls import path

from .views import HomeView, LegalNoticeView, PrivacyPolicyView, TermsOfServiceView

app_name = "landing"

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("privacy/", PrivacyPolicyView.as_view(), name="privacy_policy"),
    path("terms/", TermsOfServiceView.as_view(), name="terms_of_service"),
    path("legal/", LegalNoticeView.as_view(), name="legal_notice"),
]
