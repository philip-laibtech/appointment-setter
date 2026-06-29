import hashlib
import secrets

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _


class CompanyAccountManager(BaseUserManager):
    def create_user(self, email, password, business_name, **extra_fields):
        if not email:
            raise ValueError("Email is required.")
        if not business_name:
            raise ValueError("Business name is required.")
        email = self.normalize_email(email)
        user = self.model(email=email, business_name=business_name, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password, business_name, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email, password, business_name, **extra_fields)


class CompanyAccount(AbstractBaseUser, PermissionsMixin):
    class BookingConfirmationMode(models.TextChoices):
        AUTOMATIC = "automatic", "Automatic confirmation"
        MANUAL = "manual", "Manual confirmation"

    class Language(models.TextChoices):
        GERMAN = "de", _("Deutsch")
        FRENCH = "fr", _("Français")
        ITALIAN = "it", _("Italiano")
        ENGLISH = "en", _("English")

    email = models.EmailField(unique=True)
    business_name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, blank=True)
    street = models.CharField(max_length=255, blank=True, default="")
    plz = models.CharField(max_length=20, blank=True, default="")
    location = models.CharField(max_length=255, blank=True, default="")
    phone = models.CharField(max_length=50, blank=True, default="")
    website = models.URLField(max_length=255, blank=True, default="")
    public_page_enabled = models.BooleanField(default=True)
    timezone = models.CharField(max_length=64, default="Europe/Zurich")
    show_staff_names_publicly = models.BooleanField(default=True)
    enable_any_employee_option = models.BooleanField(default=True)
    slot_interval_minutes = models.PositiveIntegerField(default=15)
    booking_confirmation_mode = models.CharField(
        max_length=20,
        choices=BookingConfirmationMode.choices,
        default=BookingConfirmationMode.AUTOMATIC,
    )
    language = models.CharField(
        max_length=2,
        choices=Language.choices,
        default=Language.GERMAN,
        verbose_name=_("Interface language"),
        help_text=_("Language used for your dashboard, public booking page, and notification emails."),
    )
    tos_accepted_at = models.DateTimeField(null=True, blank=True, default=None)
    tos_version = models.CharField(max_length=20, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["business_name"]

    objects = CompanyAccountManager()

    class Meta:
        verbose_name = "Company Account"
        verbose_name_plural = "Company Accounts"

    def __str__(self):
        return self.email

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._generate_unique_slug()
        super().save(*args, **kwargs)

    def _generate_unique_slug(self):
        base = slugify(self.business_name)
        slug = base
        counter = 1
        while CompanyAccount.objects.filter(slug=slug).exists():
            slug = f"{base}-{counter}"
            counter += 1
        return slug


class DeletionRequest(models.Model):
    company = models.OneToOneField(
        CompanyAccount,
        on_delete=models.CASCADE,
        related_name="deletion_request",
    )
    token = models.CharField(max_length=64, unique=True, editable=False)
    requested_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_urlsafe(32)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"DeletionRequest({self.company_id}) @ {self.requested_at}"


class AccountDeletionLog(models.Model):
    """Audit record that survives account deletion.

    GDPR note: no FK to CompanyAccount. Stores a SHA-256 hash of the
    normalised email (non-reversible — verifiable but not PII) and the
    business name (organisational data, not personal data for legal entities;
    may be personal data for sole traders — acceptable under legitimate
    interest for demonstrating compliance with erasure requests).
    Retain this log for the period defined in your privacy policy, then purge.
    """
    company_email_hash = models.CharField(max_length=64, db_index=True)
    business_name = models.CharField(max_length=255)
    deletion_token = models.CharField(max_length=64)
    requested_at = models.DateTimeField()
    executed_at = models.DateTimeField(auto_now_add=True)
    confirmed_by = models.CharField(max_length=255, blank=True, default="")

    @staticmethod
    def hash_email(email: str) -> str:
        return hashlib.sha256(email.strip().lower().encode()).hexdigest()

    def __str__(self):
        return f"AccountDeletionLog({self.business_name}) executed {self.executed_at:%Y-%m-%d}"
