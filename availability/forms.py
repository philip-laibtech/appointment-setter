from datetime import datetime, timedelta

from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from staff_members.models import StaffMember

from .models import AppointmentSlot

_MIN_DURATION = timedelta(minutes=5)
_MAX_DURATION = timedelta(hours=8)
_MAX_LOOKAHEAD_DAYS = 365


def _time_duration(start_time, end_time):
    """Return a timedelta between two time objects on the same day."""
    return (
        datetime(2000, 1, 1, end_time.hour, end_time.minute, end_time.second)
        - datetime(2000, 1, 1, start_time.hour, start_time.minute, start_time.second)
    )


def _staff_queryset(company):
    return StaffMember.objects.filter(company=company, is_active=True)


class OpenHoursForm(forms.Form):
    staff_member = forms.ModelChoiceField(
        queryset=StaffMember.objects.none(),
        label=_("Staff member"),
        empty_label=_("— Select staff member —"),
    )
    date = forms.DateField(
        label=_("Date"),
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        input_formats=["%Y-%m-%d"],
    )
    start_time = forms.TimeField(
        label=_("From"),
        widget=forms.TimeInput(attrs={"type": "time"}),
        input_formats=["%H:%M", "%H:%M:%S"],
    )
    end_time = forms.TimeField(
        label=_("To"),
        widget=forms.TimeInput(attrs={"type": "time"}),
        input_formats=["%H:%M", "%H:%M:%S"],
    )

    def __init__(self, *args, company=None, instance_pk=None, **kwargs):
        self.company = company
        self.instance_pk = instance_pk
        super().__init__(*args, **kwargs)
        self.fields["date"].widget.attrs["min"] = timezone.localdate().isoformat()

        if company is not None:
            qs = _staff_queryset(company)
            self.fields["staff_member"].queryset = qs
            if qs.count() == 1:
                self.fields["staff_member"].initial = qs.first()

    def clean(self):
        cleaned_data = super().clean()
        staff_member = cleaned_data.get("staff_member")
        date = cleaned_data.get("date")
        start_time = cleaned_data.get("start_time")
        end_time = cleaned_data.get("end_time")

        if not all([staff_member, date, start_time, end_time]):
            return cleaned_data

        if self.company is not None and staff_member.company != self.company:
            self.add_error("staff_member", _("Invalid staff member."))
            return cleaned_data

        start_at = timezone.make_aware(datetime.combine(date, start_time))
        end_at = timezone.make_aware(datetime.combine(date, end_time))
        now = timezone.now()

        if start_at <= now:
            self.add_error("start_time", _("Start time must be in the future."))
            return cleaned_data

        if end_at <= start_at:
            self.add_error("end_time", _("End time must be after start time."))
            return cleaned_data

        duration = end_at - start_at
        if duration < _MIN_DURATION:
            self.add_error("end_time", _("Duration must be at least 5 minutes."))
            return cleaned_data
        if duration > _MAX_DURATION:
            self.add_error("end_time", _("Duration must not exceed 8 hours."))
            return cleaned_data

        overlap_qs = AppointmentSlot.objects.filter(
            staff_member=staff_member,
            status__in=[AppointmentSlot.Status.AVAILABLE, AppointmentSlot.Status.BLOCKED],
            start_at__lt=end_at,
            end_at__gt=start_at,
        )
        if self.instance_pk:
            overlap_qs = overlap_qs.exclude(pk=self.instance_pk)
        if overlap_qs.exists():
            raise forms.ValidationError(
                _("These hours overlap with an existing slot for this staff member. Please choose a different time.")
            )

        cleaned_data["start_at"] = start_at
        cleaned_data["end_at"] = end_at
        return cleaned_data


class RecurringHoursForm(forms.Form):
    WEEKDAYS = [
        ("0", _("Mon")),
        ("1", _("Tue")),
        ("2", _("Wed")),
        ("3", _("Thu")),
        ("4", _("Fri")),
        ("5", _("Sat")),
        ("6", _("Sun")),
    ]

    staff_member = forms.ModelChoiceField(
        queryset=StaffMember.objects.none(),
        label=_("Staff member"),
        empty_label=_("— Select staff member —"),
    )
    weekdays = forms.MultipleChoiceField(
        choices=WEEKDAYS,
        label=_("Repeat on"),
        error_messages={"required": _("Select at least one day of the week.")},
    )
    start_time = forms.TimeField(
        label=_("From"),
        widget=forms.TimeInput(attrs={"type": "time"}),
        input_formats=["%H:%M", "%H:%M:%S"],
    )
    end_time = forms.TimeField(
        label=_("To"),
        widget=forms.TimeInput(attrs={"type": "time"}),
        input_formats=["%H:%M", "%H:%M:%S"],
    )
    date_from = forms.DateField(
        label=_("Starting from"),
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    date_until = forms.DateField(
        label=_("Until"),
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    def __init__(self, *args, company=None, **kwargs):
        self.company = company
        super().__init__(*args, **kwargs)
        today = timezone.localdate()
        max_date = (today + timedelta(days=_MAX_LOOKAHEAD_DAYS)).isoformat()
        self.fields["date_from"].widget.attrs.update({
            "min": today.isoformat(),
            "max": max_date,
        })
        self.fields["date_until"].widget.attrs.update({
            "min": today.isoformat(),
            "max": max_date,
        })

        if company is not None:
            qs = _staff_queryset(company)
            self.fields["staff_member"].queryset = qs
            if qs.count() == 1:
                self.fields["staff_member"].initial = qs.first()

    def clean(self):
        cleaned_data = super().clean()
        staff_member = cleaned_data.get("staff_member")
        start_time = cleaned_data.get("start_time")
        end_time = cleaned_data.get("end_time")
        date_from = cleaned_data.get("date_from")
        date_until = cleaned_data.get("date_until")

        if staff_member and self.company is not None and staff_member.company != self.company:
            self.add_error("staff_member", _("Invalid staff member."))

        # ── Time validation ────────────────────────────────
        if start_time and end_time:
            if end_time <= start_time:
                self.add_error("end_time", _("End time must be after start time."))
            else:
                duration = _time_duration(start_time, end_time)
                if duration < _MIN_DURATION:
                    self.add_error("end_time", _("Duration must be at least 5 minutes."))
                elif duration > _MAX_DURATION:
                    self.add_error("end_time", _("Duration must not exceed 8 hours."))

        # ── Date validation ────────────────────────────────
        today = timezone.localdate()
        max_date = today + timedelta(days=_MAX_LOOKAHEAD_DAYS)

        if date_from:
            if date_from < today:
                self.add_error("date_from", _("Start date must be today or in the future."))
            elif date_from > max_date:
                self.add_error("date_from", _("Start date must be within one year from today."))

        if date_until:
            if date_until > max_date:
                self.add_error("date_until", _("End date must be within one year from today."))

        if date_from and date_until and not self.errors.get("date_from") and not self.errors.get("date_until"):
            if date_until < date_from:
                self.add_error("date_until", _("End date must not be before start date."))

        return cleaned_data
