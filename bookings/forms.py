from captcha.fields import CaptchaField

from django import forms


class BookingForm(forms.Form):
    # Honeypot — must remain empty; bots tend to fill every visible text field.
    # Hidden via CSS in the template. Never shown to real users.
    website = forms.CharField(required=False, widget=forms.TextInput())

    customer_first_name = forms.CharField(
        max_length=100,
        label="First name",
        widget=forms.TextInput(attrs={"autocomplete": "given-name"}),
    )
    customer_last_name = forms.CharField(
        max_length=100,
        label="Last name",
        widget=forms.TextInput(attrs={"autocomplete": "family-name"}),
    )
    customer_email = forms.EmailField(
        label="Email address",
        widget=forms.EmailInput(attrs={"autocomplete": "email"}),
    )
    customer_phone = forms.CharField(
        max_length=30,
        required=False,
        label="Phone number (optional)",
        widget=forms.TextInput(attrs={"autocomplete": "tel"}),
    )
    customer_message = forms.CharField(
        required=False,
        label="Message (optional)",
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    privacy_accepted = forms.BooleanField(
        required=True,
        label="I accept the privacy policy.",
        error_messages={"required": "You must accept the privacy policy to proceed."},
    )
    captcha = CaptchaField(
        error_messages={"invalid": "Incorrect security code. Please try again."},
    )

    def clean_website(self):
        value = self.cleaned_data.get("website", "")
        if value:
            raise forms.ValidationError("Invalid form submission.")
        return value

    def clean_customer_first_name(self):
        return self.cleaned_data["customer_first_name"].strip()

    def clean_customer_last_name(self):
        return self.cleaned_data["customer_last_name"].strip()

    def clean_customer_email(self):
        email = self.cleaned_data["customer_email"].strip().lower()
        # Validate after normalisation
        forms.EmailField().validate(email)
        return email

    def clean_customer_phone(self):
        return self.cleaned_data.get("customer_phone", "").strip()

    def clean_customer_message(self):
        return self.cleaned_data.get("customer_message", "").strip()
