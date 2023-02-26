# Generated by Django 4.1.5 on 2023-01-30 08:13

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("eligibility", "0002_geiq_eligibility_models"),
        ("approvals", "0003_fill_approval_origin"),
    ]

    operations = [
        migrations.AddField(
            model_name="approval",
            name="eligibility_diagnosis",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="eligibility.eligibilitydiagnosis",
                verbose_name="Diagnostic d'éligibilité",
            ),
        ),
    ]