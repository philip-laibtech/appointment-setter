from django import forms

from .models import StaffMember


class StaffMemberForm(forms.ModelForm):
    class Meta:
        model = StaffMember
        fields = ["name", "email", "phone"]

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
