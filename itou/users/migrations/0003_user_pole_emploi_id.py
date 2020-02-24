# Generated by Django 2.2.9 on 2020-01-30 13:42

import django.core.validators
from django.db import migrations, models
import itou.utils.validators


class Migration(migrations.Migration):

    dependencies = [("users", "0002_user_created_by")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="pole_emploi_id",
            field=models.CharField(
                blank=True,
                help_text="7 chiffres suivis d'une 1 lettre ou d'un chiffre.",
                max_length=8,
                validators=[
                    itou.utils.validators.validate_pole_emploi_id,
                    django.core.validators.MinLengthValidator(8),
                ],
                verbose_name="Identifiant Pôle emploi",
            ),
        )
    ]
