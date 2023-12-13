# Generated by Django 4.2.8 on 2023-12-13 15:48

import django.core.validators
from django.db import migrations, models

import itou.utils.validators


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0025_rename_siae_staff"),
    ]

    operations = [
        migrations.AddField(
            model_name="jobseekerprofile",
            name="lack_of_pole_emploi_id_reason",
            field=models.CharField(
                blank=True,
                choices=[
                    ("FORGOTTEN", "Identifiant Pôle emploi oublié"),
                    ("NOT_REGISTERED", "Non inscrit auprès de Pôle emploi"),
                ],
                help_text=(
                    "Indiquez la raison de l'absence d'identifiant Pôle emploi.<br>"
                    "Renseigner l'identifiant Pôle emploi des candidats inscrits permet "
                    "d'instruire instantanément votre demande.<br>Dans le cas contraire "
                    "un délai de deux jours est nécessaire pour effectuer manuellement "
                    "les vérifications d’usage."
                ),
                verbose_name="pas d'identifiant Pôle emploi\xa0?",
            ),
        ),
        migrations.AddField(
            model_name="jobseekerprofile",
            name="pole_emploi_id",
            field=models.CharField(
                blank=True,
                help_text="7 chiffres suivis d'une 1 lettre ou d'un chiffre.",
                max_length=8,
                validators=[
                    itou.utils.validators.validate_pole_emploi_id,
                    django.core.validators.MinLengthValidator(8),
                ],
                verbose_name="identifiant Pôle emploi",
            ),
        ),
    ]
