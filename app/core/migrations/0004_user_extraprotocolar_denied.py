from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0003_user_protocolar_denied"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="extraprotocolar_denied",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text=(
                    "Extra type keys this user cannot create or digitize "
                    "(permisos_viaje, poderes, cartas, libros, domiciliario, …). "
                    "Empty means all are allowed."
                ),
                verbose_name="Extraprotocolares denegados",
            ),
        ),
    ]
