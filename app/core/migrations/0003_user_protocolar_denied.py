from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_user_taxes_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="protocolar_denied",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text=(
                    "idtipkar values this user cannot create or digitize "
                    "(1 escrituras, 2 no contenciosos, 3 transferencias, "
                    "4 garantías, 5 testamentos). Empty means all are allowed."
                ),
                verbose_name="Protocolares denegados",
            ),
        ),
    ]
