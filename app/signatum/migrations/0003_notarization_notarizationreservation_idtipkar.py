from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("signatum", "0002_drop_expires_at_if_present"),
    ]

    operations = [
        migrations.AddField(
            model_name="notarizationreservation",
            name="idtipkar",
            field=models.IntegerField(default=1, help_text="Tipo de kardex; pending lock and correlatives are independent per tipo."),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="notarization",
            name="idtipkar",
            field=models.IntegerField(default=1, help_text="Tipo de kardex; correlatives and locks are scoped per tipo."),
            preserve_default=False,
        ),
    ]
