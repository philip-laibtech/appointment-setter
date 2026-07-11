from django.contrib.sitemaps import Sitemap
from django.urls import reverse


class StaticViewSitemap(Sitemap):
    # Only the public marketing/legal pages — public booking pages
    # (bookings:entry) are intentionally left out: their deeper steps carry
    # secret public_token URLs that must never be indexed (see robots.txt).
    changefreq = "monthly"
    protocol = "https"

    def items(self):
        return [
            "landing:home",
            "landing:pricing",
            "landing:features",
            "landing:about",
            "landing:contact",
            "landing:faq",
            "landing:privacy_policy",
            "landing:terms_of_service",
            "landing:legal_notice",
        ]

    def location(self, item):
        return reverse(item)

    def priority(self, item):
        return 1.0 if item == "landing:home" else 0.5
