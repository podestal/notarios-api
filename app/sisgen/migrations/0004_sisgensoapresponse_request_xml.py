from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sisgen", "0003_sisgensendjob"),
    ]

    operations = [
        migrations.AddField(
            model_name="sisgensoapresponse",
            name="request_xml",
            field=models.TextField(blank=True, default=""),
        ),
    ]
