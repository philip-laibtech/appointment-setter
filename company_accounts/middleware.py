from django.conf import settings
from django.utils import translation


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
