from django.urls import path

from .views import HomeView, PrivacyPolicyView, TermsOfServiceView

app_name = "landing"

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("privacy/", PrivacyPolicyView.as_view(), name="privacy_policy"),
    path("terms/", TermsOfServiceView.as_view(), name="terms_of_service"),
]
