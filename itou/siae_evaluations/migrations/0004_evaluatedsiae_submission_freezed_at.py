# Generated by Django 4.1.9 on 2023-05-24 14:03

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("siae_evaluations", "0003_reset_evaluated_siae_notified_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="evaluatedsiae",
            name="submission_freezed_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Transmission bloquée pour la SIAE le"),
        ),
    ]