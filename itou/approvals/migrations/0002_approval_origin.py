# Generated by Django 4.1.5 on 2023-01-26 10:39

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("approvals", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="approval",
            name="origin",
            field=models.CharField(
                choices=[
                    ("default", "Créé normalement via les emplois"),
                    ("pe_approval", "Créé lors d'un import d'Agrément Pole Emploi"),
                    ("ai_stock", "Créé lors de l'import du stock AI"),
                    ("admin", "Créé depuis l'admin"),
                ],
                default="default",
                max_length=30,
                verbose_name="Origine du pass",
            ),
        ),
    ]