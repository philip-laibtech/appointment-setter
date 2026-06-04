import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("availability", "0001_initial"),
        ("staff_members", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="appointmentslot",
            name="staff_member",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="appointment_slots",
                to="staff_members.staffmember",
            ),
        ),
        migrations.AddIndex(
            model_name="appointmentslot",
            index=models.Index(fields=["staff_member", "start_at"], name="availabilit_staff_m_idx"),
        ),
    ]
