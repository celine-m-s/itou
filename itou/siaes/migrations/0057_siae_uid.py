# Generated by Django 4.0.5 on 2022-06-16 08:23

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("siaes", "0056_remove_dup_field"),
    ]

    operations = [
        migrations.AddField(
            model_name="siae",
            name="uid",
            field=models.UUIDField(db_index=True, default=uuid.uuid4),
        ),
    ]
