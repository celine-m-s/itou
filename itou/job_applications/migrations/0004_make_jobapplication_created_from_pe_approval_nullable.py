# Generated by Django 4.1.5 on 2023-01-30 15:38

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("job_applications", "0003_fill_job_application_origin"),
    ]

    operations = [
        migrations.AlterField(
            model_name="jobapplication",
            name="created_from_pe_approval",
            field=models.BooleanField(
                default=False, null=True, verbose_name="Candidature créée lors de l'import d'un agrément Pole Emploi"
            ),
        ),
    ]