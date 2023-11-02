# Generated by Django 4.2.7 on 2023-11-06 09:24

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("companies", "0007_rename_siae_company"),
        ("approvals", "0018_rename_siae_staff"),
    ]

    operations = [
        migrations.AlterField(
            model_name="prolongation",
            name="declared_by_siae",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="companies.company",
                verbose_name="SIAE du déclarant",
            ),
        ),
        migrations.AlterField(
            model_name="prolongationrequest",
            name="declared_by_siae",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="companies.company",
                verbose_name="SIAE du déclarant",
            ),
        ),
        migrations.AlterField(
            model_name="suspension",
            name="siae",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="approvals_suspended",
                to="companies.company",
                verbose_name="SIAE",
            ),
        ),
    ]