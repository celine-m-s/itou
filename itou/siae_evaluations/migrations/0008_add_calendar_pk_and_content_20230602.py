# Generated by Django 4.1.9 on 2023-06-02 14:09

from pathlib import Path

from django.conf import settings
from django.db import migrations


def _create_active_campaigns_calendar(apps, _):
    EvaluationCampaign = apps.get_model("siae_evaluations", "EvaluationCampaign")
    Calendar = apps.get_model("siae_evaluations", "Calendar")
    # We could have used `EvaluationCampagin.objects.in_progress()`` but managers are not accessible
    # in migrations unless explicitelly set from the beginning.
    active_campaigns = EvaluationCampaign.objects.filter(ended_at=None).all()
    if active_campaigns:
        calendar, _ = Calendar.objects.get_or_create(name=active_campaigns.first().name)
        if not calendar.html:
            file_path = Path(settings.APPS_DIR) / "templates" / "siae_evaluations" / "default_calendar_html.html"
            with open(file_path, encoding="utf-8") as file:
                calendar.html = file.read()
                calendar.save()
        for campaign in active_campaigns:
            campaign.calendar_id = calendar.pk
        active_campaigns.bulk_update(active_campaigns, fields=["calendar_id"])


class Migration(migrations.Migration):
    dependencies = [
        ("siae_evaluations", "0007_evaluationcampaign_calendar"),
    ]

    operations = [
        migrations.RunPython(_create_active_campaigns_calendar, migrations.RunPython.noop, elidable=True),
    ]
