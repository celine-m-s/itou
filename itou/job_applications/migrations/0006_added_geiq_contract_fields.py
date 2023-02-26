# Generated by Django 4.1.7 on 2023-03-09 14:34

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("job_applications", "0005_remove_jobapplication_created_from_pe_approval"),
    ]

    operations = [
        migrations.AddField(
            model_name="jobapplication",
            name="contract_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("APPRENTICESHIP", "Contrat d'apprentissage"),
                    ("PROFESSIONAL_TRAINING", "Contrat de professionalisation"),
                    ("OTHER", "Autre type de contrat"),
                ],
                max_length=30,
                verbose_name="Type de contrat",
            ),
        ),
        migrations.AddField(
            model_name="jobapplication",
            name="contract_type_details",
            field=models.TextField(blank=True, verbose_name="Précisions sur le type de contrat"),
        ),
        migrations.AddField(
            model_name="jobapplication",
            name="nb_hours_per_week",
            field=models.PositiveSmallIntegerField(
                blank=True,
                null=True,
                validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(48)],
                verbose_name="Nombre d'heures par semaine",
            ),
        ),
        migrations.AddConstraint(
            model_name="jobapplication",
            constraint=models.CheckConstraint(
                check=models.Q(
                    models.Q(
                        ("contract_type__in", ["PROFESSIONAL_TRAINING", "APPRENTICESHIP"]),
                        ("contract_type_details", ""),
                        ("nb_hours_per_week__gt", 0),
                    ),
                    models.Q(
                        ("contract_type", "OTHER"),
                        ("nb_hours_per_week__gt", 0),
                        models.Q(("contract_type_details", ""), _negated=True),
                    ),
                    models.Q(("contract_type", ""), ("contract_type_details", ""), ("nb_hours_per_week", None)),
                    _connector="OR",
                ),
                name="geiq_fields_coherence",
                violation_error_message="Incohérence dans les champs concernant le contrat GEIQ",
            ),
        ),
    ]