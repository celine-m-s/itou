# Generated by Django 4.1.3 on 2022-11-25 10:54

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("jobs", "0002_create_full_text_trigger"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="rome",
            name="code_isco",
        ),
        migrations.RemoveField(
            model_name="rome",
            name="riasec_major",
        ),
        migrations.RemoveField(
            model_name="rome",
            name="riasec_minor",
        ),
    ]