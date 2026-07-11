import os
import sys
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.utils.translation import gettext_lazy as _

_TESTING = "test" in sys.argv

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-dev-only-change-before-production",
)

DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() == "true"

ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost 127.0.0.1").split()

# Django admin mount path. Must be overridden to a unique, non-guessable value
# in production so the admin isn't reachable at the well-known /admin/ path.
DJANGO_ADMIN_URL = os.environ.get("DJANGO_ADMIN_URL", "")
if not DJANGO_ADMIN_URL:
    if DEBUG or _TESTING:
        DJANGO_ADMIN_URL = "admin/"
    else:
        raise ImproperlyConfigured(
            "DJANGO_ADMIN_URL must be set to a unique path when DJANGO_DEBUG=false."
        )
if not DJANGO_ADMIN_URL.endswith("/"):
    DJANGO_ADMIN_URL += "/"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sitemaps",
    "captcha",
    "csp",
    "django_otp",
    "django_otp.plugins.otp_totp",
    "django_otp.plugins.otp_static",
    "company_accounts",
    "landing",
    "availability",
    "staff_members",
    "services",
    "bookings",
    "notifications",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "csp.middleware.CSPMiddleware",
    "core.middleware.PermissionsPolicyMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_otp.middleware.OTPMiddleware",
    "company_accounts.middleware.TosGateMiddleware",
    "company_accounts.middleware.CompanyLanguageMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "core.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "bookings.context_processors.pending_bookings_count",
            ],
        },
    },
]

WSGI_APPLICATION = "core.wsgi.application"

_db_engine = os.environ.get("DB_ENGINE") or "django.db.backends.sqlite3"
_db_name = os.environ.get("DB_NAME") or str(BASE_DIR / "db.sqlite3")

_db_options = {}
if _db_engine == "django.db.backends.mysql":
    # utf8mb4 stores full Unicode (incl. emoji); STRICT_TRANS_TABLES makes
    # MySQL reject/truncate-error on invalid data instead of silently
    # coercing it, matching Django's own field validation.
    _db_options["charset"] = "utf8mb4"
    _db_options["init_command"] = "SET sql_mode='STRICT_TRANS_TABLES'"

    # Encrypt the connection to MySQL by default. REQUIRED enforces TLS
    # without pinning a CA (fine for localhost/self-signed setups); set
    # DB_SSL_CA to a CA bundle path to additionally verify the server
    # certificate (VERIFY_CA/VERIFY_IDENTITY), or DB_SSL_MODE=DISABLED to
    # turn this off for a trusted local-only connection.
    _db_ssl_mode = os.environ.get("DB_SSL_MODE", "REQUIRED").upper()
    if _db_ssl_mode != "DISABLED":
        _db_options["ssl_mode"] = _db_ssl_mode
        _db_ssl_ca = os.environ.get("DB_SSL_CA", "")
        if _db_ssl_ca:
            _db_options["ssl"] = {"ca": _db_ssl_ca}

DATABASES = {
    "default": {
        "ENGINE": _db_engine,
        "NAME": _db_name,
        "USER": os.environ.get("DB_USER", ""),
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "HOST": os.environ.get("DB_HOST", ""),
        "PORT": os.environ.get("DB_PORT", ""),
        "OPTIONS": _db_options,
    }
}

AUTH_USER_MODEL = "company_accounts.CompanyAccount"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "company_accounts:login"
LOGIN_REDIRECT_URL = "company_accounts:dashboard"
LOGOUT_REDIRECT_URL = "company_accounts:login"

LANGUAGE_CODE = "de"
LANGUAGES = [
    ("de", _("German")),
    ("fr", _("French")),
    ("it", _("Italian")),
    ("en", _("English")),
]
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = "Europe/Zurich"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Email
EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "true").lower() == "true"
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "noreply@example.com")
SUPPORT_EMAIL = os.environ.get("SUPPORT_EMAIL", "")

# Security headers — enforced in production (DEBUG=False)
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# The app sits behind a reverse proxy (nginx) that terminates TLS and
# forwards plain HTTP internally. Without this, SECURE_SSL_REDIRECT above
# sees every request as insecure and redirect-loops. Only safe because the
# proxy is configured to always overwrite X-Forwarded-Proto itself — same
# spoofing caveat as RATELIMIT_IP_META_KEY below.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Session cookie expires when the browser closes, AND the server-side session
# itself expires after 2 weeks (Django's SESSION_COOKIE_AGE default) —
# whichever comes first. Matches the privacy policy's session cookie claim.
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

# django-ratelimit resolves the client IP from this WSGI META key. REMOTE_ADDR
# (the default) is safe even behind a misconfigured proxy, because it cannot
# be set by the client. Only override this to a header like "HTTP_X_REAL_IP"
# if your reverse proxy is configured to always overwrite that header itself
# (never forwarding a client-supplied value) — see docs/deployment.md.
RATELIMIT_IP_META_KEY = os.environ.get("RATELIMIT_IP_META_KEY", "REMOTE_ADDR")

# Content Security Policy (django-csp 4.0)
# Inline styles are permitted across all templates; no inline scripts remain.
# Bump this string whenever the privacy policy text changes materially.
# The current value is stamped on every new Booking at creation time (GDPR audit trail).
CAPTCHA_TEST_MODE = _TESTING
RATELIMIT_ENABLE = not _TESTING

PRIVACY_POLICY_VERSION = "1.0"
# Human-readable date shown as "Last updated" on the privacy policy page.
# Update together with PRIVACY_POLICY_VERSION whenever the policy text changes.
PRIVACY_POLICY_LAST_UPDATED = "July 10, 2026"

# Bump this string whenever the Terms of Service change materially.
# The current value is stamped on every new CompanyAccount at registration.
CURRENT_TOS_VERSION = "1.0"
# Human-readable date shown as "Last updated" on the terms of service page.
# Update together with CURRENT_TOS_VERSION whenever the ToS text changes.
CURRENT_TOS_LAST_UPDATED = "July 10, 2026"

# Days after a booking's end_at before customer PII fields are anonymised.
CUSTOMER_DATA_RETENTION_DAYS = 30

# Per-account login lockout (company_accounts/lockout.py). Complements the
# IP/username rate limits on login_view with a check keyed on the submitted
# account, so a distributed/botnet attack against one account is still
# throttled even if requests are spread across many IPs.
ACCOUNT_LOCKOUT_THRESHOLD = 10
ACCOUNT_LOCKOUT_DURATION_MINUTES = 15

# Years to retain AccountDeletionLog entries (proof-of-deletion audit trail)
# before they are purged by `python manage.py purge_deletion_logs`.
DELETION_LOG_RETENTION_YEARS = 3

# Two-factor authentication (django-otp)
# Issuer name shown inside the authenticator app next to the account entry.
OTP_TOTP_ISSUER = "Terminklick"
# Number of single-use backup codes generated/regenerated for account recovery.
TWO_FACTOR_BACKUP_CODE_COUNT = 10

CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": ["'self'"],
        "script-src": ["'self'"],
        "style-src": ["'self'", "'unsafe-inline'"],
        "img-src": ["'self'", "data:"],
        "font-src": ["'self'"],
        "connect-src": ["'self'"],
        "object-src": ["'none'"],
        "base-uri": ["'self'"],
        "form-action": ["'self'"],
        "frame-ancestors": ["'none'"],
    }
}

# Structured application logging (AUDIT.md 5.3/7.2/7.3).
#
# PII-scrubbing policy: log messages in this codebase must never include
# customer_first_name, customer_last_name, customer_email, customer_phone,
# or customer_message. Use non-PII identifiers instead (booking.pk,
# company.pk) — see existing logger.exception() calls in notifications/
# services.py and company_accounts/views.py for the established pattern.
# Logs go to stdout/stderr — capture and rotate them at the process
# supervisor level (systemd journal, Docker log driver, etc.) in production.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "structured": {
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "structured",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "CRITICAL" if _TESTING else "WARNING",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "CRITICAL" if _TESTING else "INFO",
            "propagate": False,
        },
        "company_accounts": {
            "handlers": ["console"],
            "level": "CRITICAL" if _TESTING else "INFO",
            "propagate": False,
        },
        "bookings": {
            "handlers": ["console"],
            "level": "CRITICAL" if _TESTING else "INFO",
            "propagate": False,
        },
        "notifications": {
            "handlers": ["console"],
            "level": "CRITICAL" if _TESTING else "INFO",
            "propagate": False,
        },
    },
}
