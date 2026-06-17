from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import translation


_TOS_GATE_EXEMPT_PREFIXES = (
    "/tos-reaccept/",
    "/login/",
    "/logout/",
    "/register/",
    "/password-reset/",
    "/admin/",
    "/privacy/",
    "/terms/",
    "/b/",        # public booking flow
    "/captcha/",
    "/static/",
)


class TosGateMiddleware:
    """Redirect authenticated users to re-accept the ToS when it has been updated.

    Runs after AuthenticationMiddleware. Skips public and auth-related paths so
    the gate never blocks login, logout, or the re-acceptance page itself.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (
            user is not None
            and user.is_authenticated
            and not any(request.path.startswith(p) for p in _TOS_GATE_EXEMPT_PREFIXES)
            and request.path != "/"
            and getattr(user, "tos_version", "") != settings.CURRENT_TOS_VERSION
        ):
            reaccept_url = reverse("company_accounts:tos_reaccept")
            return redirect(f"{reaccept_url}?next={request.path}")

        return self.get_response(request)


class CompanyLanguageMiddleware:
    """Activate the authenticated company's configured interface language.

    Must run after AuthenticationMiddleware so request.user is available.
    The company's configured language is authoritative for authenticated
    requests and is not influenced by the Accept-Language header.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        valid_codes = {code for code, _label in settings.LANGUAGES}

        if user is not None and user.is_authenticated:
            language = getattr(user, "language", "")
            if language not in valid_codes:
                language = settings.LANGUAGE_CODE
            translation.activate(language)
            request.LANGUAGE_CODE = translation.get_language()

        try:
            response = self.get_response(request)
        finally:
            translation.deactivate()

        return response
