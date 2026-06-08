import uuid

from django.db import migrations, models


def populate_public_ids(apps, schema_editor):
    ServiceOffering = apps.get_model("services", "ServiceOffering")
    for obj in ServiceOffering.objects.all():
        obj.public_id = uuid.uuid4()
        obj.save(update_fields=["public_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("services", "0001_initial"),
    ]

    operations = [
        # Step 1: add nullable (no unique constraint yet)
        migrations.AddField(
            model_name="serviceoffering",
            name="public_id",
            field=models.UUIDField(null=True, editable=False),
        ),
        # Step 2: populate a unique UUID for every existing row
        migrations.RunPython(populate_public_ids, migrations.RunPython.noop),
        # Step 3: enforce non-null + unique
        migrations.AlterField(
            model_name="serviceoffering",
            name="public_id",
            field=models.UUIDField(default=uuid.uuid4, unique=True, editable=False),
        ),
    ]
