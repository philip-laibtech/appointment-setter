from django.shortcuts import redirect
from django.views.generic import TemplateView


class HomeView(TemplateView):
    template_name = "landing/home.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("company_accounts:dashboard")
        return super().dispatch(request, *args, **kwargs)


class PrivacyPolicyView(TemplateView):
    template_name = "landing/privacy_policy.html"


class TermsOfServiceView(TemplateView):
    template_name = "landing/terms_of_service.html"


class LegalNoticeView(TemplateView):
    template_name = "landing/legal_notice.html"
