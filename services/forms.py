from django import forms

from staff_members.models import StaffMember

from .models import ServiceOffering


def _active_staff_qs(company):
    return StaffMember.objects.filter(company=company, is_active=True)


class ServiceOfferingForm(forms.ModelForm):
    assigned_staff_members = forms.ModelMultipleChoiceField(
        queryset=StaffMember.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Assign to staff members",
    )

    class Meta:
        model = ServiceOffering
        fields = ["name", "description", "duration_minutes"]

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        if company is not None:
            self.fields["assigned_staff_members"].queryset = _active_staff_qs(company)
        self.fields["name"].widget.attrs.update({"maxlength": 200, "autofocus": True})

    def clean_name(self):
        return self.cleaned_data["name"].strip()

    def clean_description(self):
        return self.cleaned_data.get("description", "").strip()

    def clean_duration_minutes(self):
        value = self.cleaned_data.get("duration_minutes")
        if value is None:
            return value
        if value < 5:
            raise forms.ValidationError("Duration must be at least 5 minutes.")
        if value > 480:
            raise forms.ValidationError("Duration must not exceed 480 minutes (8 hours).")
        return value

    def clean_assigned_staff_members(self):
        members = self.cleaned_data.get("assigned_staff_members") or []
        if self.company is not None:
            for member in members:
                if member.company != self.company:
                    raise forms.ValidationError(
                        "Invalid staff member selection."
                    )
                if not member.is_active:
                    raise forms.ValidationError(
                        "Only active staff members can be assigned."
                    )
        return members


class ServiceOfferingEditForm(ServiceOfferingForm):
    class Meta(ServiceOfferingForm.Meta):
        fields = ["name", "description", "duration_minutes", "is_active"]
