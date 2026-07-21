import json

from django.conf import settings
from django.shortcuts import redirect
from django.utils.translation import gettext as _
from django.views.generic import TemplateView

# Escape characters that could prematurely close a <script> tag or otherwise
# break out of the JSON-LD block when embedded directly in HTML.
_JSONLD_ESCAPES = {
    ord("<"): "\\u003C",
    ord(">"): "\\u003E",
    ord("&"): "\\u0026",
}


def _ld_json(data):
    return json.dumps(data).translate(_JSONLD_ESCAPES)


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

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["pricing_schema"] = _ld_json(
            {
                "@context": "https://schema.org",
                "@type": "Service",
                "name": "Terminklick",
                "description": _(
                    "One plan, everything included: 18 CHF per month or "
                    "160 CHF billed yearly."
                ),
                "provider": {
                    "@type": "Organization",
                    "name": "Laib Technologies GmbH",
                },
                "offers": [
                    {
                        "@type": "Offer",
                        "price": "18.00",
                        "priceCurrency": "CHF",
                        "priceSpecification": {
                            "@type": "UnitPriceSpecification",
                            "price": "18.00",
                            "priceCurrency": "CHF",
                            "billingDuration": "P1M",
                        },
                    },
                    {
                        "@type": "Offer",
                        "price": "160.00",
                        "priceCurrency": "CHF",
                        "priceSpecification": {
                            "@type": "UnitPriceSpecification",
                            "price": "160.00",
                            "priceCurrency": "CHF",
                            "billingDuration": "P1Y",
                        },
                    },
                ],
            }
        )
        return context


class FeaturesView(TemplateView):
    template_name = "landing/features.html"


class AboutView(TemplateView):
    template_name = "landing/about.html"


class ContactView(TemplateView):
    template_name = "landing/contact.html"


class FaqView(TemplateView):
    template_name = "landing/faq.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qa_pairs = [
            (
                _("What is Terminklick?"),
                _(
                    "Terminklick gives your business a public booking page. "
                    "Customers pick a staff member, a service, and a time "
                    "slot, and the booking lands directly in your "
                    "dashboard. No phone calls needed."
                ),
            ),
            (
                _("Do my customers need to create an account?"),
                _(
                    "No. Customers book with just their name, email, and "
                    "phone number. They manage or cancel their booking "
                    "later through a private link sent by email, without "
                    "ever registering."
                ),
            ),
            (
                _("How long does setup take?"),
                _(
                    "Most businesses add their staff, services, and "
                    "availability, and publish their booking page within "
                    "the same day. There's no onboarding call required."
                ),
            ),
            (
                _("Is there a limit on staff, services, or bookings?"),
                _(
                    "No. Your plan includes unlimited staff members, "
                    "services, and bookings."
                ),
            ),
            (
                _("Can I review bookings before they're confirmed?"),
                _(
                    "Yes. Choose manual confirmation in your settings and "
                    "every request waits for your approval. Or leave it on "
                    "automatic and bookings confirm themselves the moment "
                    "a slot is chosen."
                ),
            ),
            (
                _("How do I set my availability?"),
                _(
                    "Define recurring weekly hours in a few clicks, or add "
                    "one-off blocks for specific dates. You can change "
                    "either at any time."
                ),
            ),
            (
                _("Can two customers book the same time slot by mistake?"),
                _(
                    "No. Once a slot is booked or has a pending request, "
                    "it's no longer offered to other customers, so "
                    "double-booking isn't possible."
                ),
            ),
            (
                _("Can a customer cancel their own booking?"),
                _(
                    "Yes, at any time, using the private link they "
                    "received by email. No account or phone call needed."
                ),
            ),
            (
                _("Is my account protected by two-factor authentication?"),
                _(
                    "You can turn on optional two-factor authentication "
                    "(TOTP, using any standard authenticator app) with "
                    "single-use backup codes in your account settings."
                ),
            ),
            (
                _("Does Terminklick track my customers?"),
                _(
                    "No. There are no third-party trackers, ad cookies, or "
                    "analytics scripts on the public booking page or your "
                    "dashboard."
                ),
            ),
            (
                _("What happens to customer data over time?"),
                _(
                    "Customer contact details are anonymised automatically "
                    "a set number of days after the appointment. Customers "
                    "can also request an export or deletion of their own "
                    "data at any time through their private booking link."
                ),
            ),
            (
                _("How much does Terminklick cost?"),
                _(
                    "18 CHF a month, or 160 CHF billed yearly. See our "
                    "pricing page for full details."
                ),
            ),
            (
                _("Do you offer more than one plan?"),
                _(
                    "No, one plan includes every feature, so there's "
                    "nothing to compare or upgrade later."
                ),
            ),
            (
                _("What languages is Terminklick available in?"),
                _(
                    "German, French, Italian, and English: for your "
                    "dashboard, your public booking page, and every email "
                    "sent to your customers."
                ),
            ),
        ]
        context["faq_schema"] = _ld_json(
            {
                "@context": "https://schema.org",
                "@type": "FAQPage",
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": question,
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": answer,
                        },
                    }
                    for question, answer in qa_pairs
                ],
            }
        )
        return context


class DocumentationView(TemplateView):
    template_name = "landing/documentation.html"


class RobotsTxtView(TemplateView):
    template_name = "landing/robots.txt"
    content_type = "text/plain"
