from django.conf import settings
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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["policy_version"] = settings.PRIVACY_POLICY_VERSION
        context["last_updated"] = settings.PRIVACY_POLICY_LAST_UPDATED
        return context


class TermsOfServiceView(TemplateView):
    template_name = "landing/terms_of_service.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["tos_version"] = settings.CURRENT_TOS_VERSION
        context["last_updated"] = settings.CURRENT_TOS_LAST_UPDATED
        return context


class LegalNoticeView(TemplateView):
    template_name = "landing/legal_notice.html"


class PricingView(TemplateView):
    template_name = "landing/pricing.html"


class FeaturesView(TemplateView):
    template_name = "landing/features.html"


class AboutView(TemplateView):
    template_name = "landing/about.html"


class ContactView(TemplateView):
    template_name = "landing/contact.html"


class FaqView(TemplateView):
    template_name = "landing/faq.html"


class RobotsTxtView(TemplateView):
    template_name = "landing/robots.txt"
    content_type = "text/plain"
