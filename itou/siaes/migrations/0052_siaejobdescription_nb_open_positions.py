# Generated by Django 4.0.2 on 2022-02-22 09:32

from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("siaes", "0051_siae_provided_support"),
    ]

    operations = [
        migrations.AddField(
            model_name="siaejobdescription",
            name="nb_open_positions",
            field=models.PositiveIntegerField(
                default=1,
                validators=[MinValueValidator(1)],
                verbose_name="Nombre de postes ouverts",
            ),
        ),
    ]
