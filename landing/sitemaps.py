from django.contrib.sitemaps import Sitemap
from django.urls import reverse


class StaticViewSitemap(Sitemap):
    # Only the public marketing/legal pages — public booking pages
    # (bookings:entry) are intentionally left out: their deeper steps carry
    # secret public_token URLs that must never be indexed (see robots.txt).
    changefreq = "monthly"
    protocol = "https"

    # Emit one <url> entry per language (using settings.LANGUAGES), each
    # carrying <xhtml:link rel="alternate" hreflang="..."> pointers to every
    # other language version plus an x-default, matching the hreflang tags
    # rendered in templates/base.html and the i18n_patterns() routing in
    # core/urls.py (German is unprefixed, so this reuses the same URLs).
    i18n = True
    alternates = True
    x_default = True

    def items(self):
        return [
            "landing:home",
            "landing:pricing",
            "landing:features",
            "landing:about",
            "landing:contact",
            "landing:faq",
            "landing:documentation",
            "landing:privacy_policy",
            "landing:terms_of_service",
            "landing:legal_notice",
        ]

    def location(self, item):
        return reverse(item)

    def priority(self, item):
        return 1.0 if item == "landing:home" else 0.5
