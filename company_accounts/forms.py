from captcha.fields import CaptchaField

from django.conf import settings
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django_otp import match_token

from .models import CompanyAccount


class CompanyRegistrationForm(forms.ModelForm):
    password1 = forms.CharField(
        label=_("Password"),
        max_length=128,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label=_("Confirm password"),
        max_length=128,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    tos_accepted = forms.BooleanField(
        required=True,
        error_messages={"required": _("You must accept the Terms of Service to register.")},
    )
    captcha = CaptchaField(
        error_messages={"invalid": _("Incorrect security code. Please try again.")},
    )

    class Meta:
        model = CompanyAccount
        fields = ("business_name", "email", "phone")
        labels = {
            "business_name": _("Business name"),
            "email": _("Email"),
            "phone": _("Phone"),
        }
        widgets = {
            "email": forms.EmailInput(attrs={"autocomplete": "email"}),
            "phone": forms.TextInput(attrs={"autocomplete": "tel"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["phone"].required = True
        self.fields["phone"].error_messages["required"] = _("A phone number is required so we can verify your identity if you request account deletion.")

    def clean_email(self):
        email = self.cleaned_data.get("email", "")
        return CompanyAccount.objects.normalize_email(email)

    def clean_password2(self):
        p1 = self.cleaned_data.get("password1", "")
        p2 = self.cleaned_data.get("password2", "")
        if p1 and p2 and p1 != p2:
            raise ValidationError(_("Passwords do not match."))
        return p2

    def _post_clean(self):
        super()._post_clean()
        password = self.cleaned_data.get("password2")
        if password:
            try:
                password_validation.validate_password(password, self.instance)
            except ValidationError as error:
                self.add_error("password2", error)

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        user.tos_accepted_at = timezone.now()
        user.tos_version = settings.CURRENT_TOS_VERSION
        if commit:
            user.save()
        return user


class CompanySettingsForm(forms.ModelForm):
    class Meta:
        model = CompanyAccount
        fields = (
            "business_name",
            "street",
            "plz",
            "location",
            "phone",
            "website",
            "public_page_enabled",
            "show_staff_names_publicly",
            "enable_any_employee_option",
            "booking_confirmation_mode",
            "language",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["business_name"].error_messages["required"] = _("Business name is required.")
        self.fields["language"].required = False

    def clean_business_name(self):
        name = self.cleaned_data.get("business_name", "").strip()
        if not name:
            raise ValidationError(_("Business name is required."))
        return name

    def clean_booking_confirmation_mode(self):
        mode = self.cleaned_data.get("booking_confirmation_mode", "")
        valid = {c[0] for c in CompanyAccount.BookingConfirmationMode.choices}
        if mode not in valid:
            raise ValidationError(_("Select a valid confirmation mode."))
        return mode

    def clean_language(self):
        language = self.cleaned_data.get("language", "")
        if not language:
            return self.instance.language
        valid = {c[0] for c in CompanyAccount.Language.choices}
        if language not in valid:
            raise ValidationError(_("Select a valid language."))
        return language


class CompanyLoginForm(AuthenticationForm):
    username = forms.EmailField(
        label=_("Email"),
        widget=forms.EmailInput(attrs={"autocomplete": "email", "autofocus": True}),
    )


class TOTPSetupForm(forms.Form):
    """Confirms a freshly generated, unconfirmed TOTPDevice during 2FA setup."""

    token = forms.CharField(
        label=_("Verification code"),
        min_length=6,
        max_length=6,
        widget=forms.TextInput(attrs={
            "inputmode": "numeric",
            "autocomplete": "one-time-code",
            "autofocus": True,
        }),
    )

    def __init__(self, *args, device, **kwargs):
        self.device = device
        super().__init__(*args, **kwargs)

    def clean_token(self):
        token = self.cleaned_data.get("token", "").strip()
        if not token.isdigit():
            raise ValidationError(_("Enter the 6-digit code shown in your authenticator app."))
        return token

    def clean(self):
        cleaned = super().clean()
        token = cleaned.get("token")
        if token and not self.device.verify_token(token):
            raise ValidationError(_("That code is incorrect or has expired. Please try again."))
        return cleaned


class TwoFactorVerifyForm(forms.Form):
    """Verifies a TOTP or backup code during login, after the password has already checked out."""

    token = forms.CharField(
        label=_("Authentication code"),
        max_length=16,
        widget=forms.TextInput(attrs={
            "inputmode": "numeric",
            "autocomplete": "one-time-code",
            "autofocus": True,
        }),
    )

    def __init__(self, *args, user, **kwargs):
        self.user = user
        self.matched_device = None
        super().__init__(*args, **kwargs)

    def clean_token(self):
        token = self.cleaned_data.get("token", "").strip().replace(" ", "")
        if not token:
            raise ValidationError(_("Enter a code."))
        return token

    def clean(self):
        cleaned = super().clean()
        token = cleaned.get("token")
        if token:
            device = match_token(self.user, token)
            if device is None:
                raise ValidationError(
                    _("Invalid or expired code. You can also use one of your backup codes.")
                )
            self.matched_device = device
        return cleaned


class PasswordConfirmForm(forms.Form):
    """Re-confirms the current password before a sensitive 2FA action (disable, regenerate codes)."""

    password = forms.CharField(
        label=_("Current password"),
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password", "autofocus": True}),
    )

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_password(self):
        password = self.cleaned_data.get("password", "")
        if not password or not self.user.check_password(password):
            raise ValidationError(_("Incorrect password."))
        return password
