from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("compliance", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="kardexcompliancecache",
            name="pdt_error_count",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
