from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from django import forms
from django.utils.translation import gettext_lazy as _

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

    class Meta:
        model = CompanyAccount
        fields = ("business_name", "email")
        labels = {
            "business_name": _("Business name"),
            "email": _("Email"),
        }
        widgets = {
            "email": forms.EmailInput(attrs={"autocomplete": "email"}),
        }

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
