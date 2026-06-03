from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils.text import slugify


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
    email = models.EmailField(unique=True)
    business_name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, blank=True)
    public_page_enabled = models.BooleanField(default=True)
    timezone = models.CharField(max_length=64, default="Europe/Zurich")
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
