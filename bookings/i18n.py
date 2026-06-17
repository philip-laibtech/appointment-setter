from django.conf import settings
from django.utils import translation


def activate_company_language(company):
    """Activate the given company's configured interface language.

    Used on public booking pages so the page, form validation, and
    confirmation/decline messages are rendered in the company's
    configured language, independent of the visitor's browser settings.
    """
    valid_codes = {code for code, _label in settings.LANGUAGES}
    language = getattr(company, "language", "")
    if language not in valid_codes:
        language = settings.LANGUAGE_CODE
    translation.activate(language)
