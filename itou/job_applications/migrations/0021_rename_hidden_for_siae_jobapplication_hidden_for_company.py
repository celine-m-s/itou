# Generated by Django 4.2.7 on 2023-11-10 09:44

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("job_applications", "0020_rename_sender_siae_jobapplication_sender_company"),
    ]

    operations = [
        migrations.RenameField(
            model_name="jobapplication",
            old_name="hidden_for_siae",
            new_name="hidden_for_company",
        ),
    ]
