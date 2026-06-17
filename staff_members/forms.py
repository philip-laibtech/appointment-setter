from django import forms
from django.utils.translation import gettext_lazy as _

from .models import StaffMember


class StaffMemberForm(forms.ModelForm):
    class Meta:
        model = StaffMember
        fields = ["name", "email", "phone"]
        labels = {
            "name": _("Name"),
            "email": _("Email"),
            "phone": _("Phone"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].widget.attrs.update({"autofocus": True, "maxlength": 150})
        self.fields["email"].required = False
        self.fields["phone"].required = False

    def clean_name(self):
        return self.cleaned_data["name"].strip()

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()

    def clean_phone(self):
        return self.cleaned_data["phone"].strip()


class StaffMemberEditForm(StaffMemberForm):
    class Meta(StaffMemberForm.Meta):
        fields = ["name", "email", "phone", "is_active"]
        labels = {
            **StaffMemberForm.Meta.labels,
            "is_active": _("Active"),
        }
