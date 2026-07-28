from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("signatum", "0003_correlativecounter"),
    ]

    operations = [
        migrations.AddField(
            model_name="correlativecounter",
            name="freed_num_escrituras",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text=(
                    'Freed correlative slots while higher ones remain committed. '
                    'Each entry: {"num_escritura": 147, "folio": "10"}. '
                    "Next reserve reuses the lowest escritura with its original folio."
                ),
            ),
        ),
    ]
