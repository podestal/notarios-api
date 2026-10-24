from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="KardexChangeLog",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("kardex", models.CharField(blank=True, db_index=True, default="", max_length=30)),
                ("idkardex", models.IntegerField(blank=True, db_index=True, null=True)),
                ("table_name", models.CharField(db_index=True, max_length=64)),
                ("record_pk", models.CharField(blank=True, default="", max_length=64)),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("create", "Created"),
                            ("update", "Updated"),
                            ("delete", "Deleted"),
                        ],
                        max_length=16,
                    ),
                ),
                ("changes", models.JSONField(blank=True, default=dict)),
                ("user_id", models.IntegerField(blank=True, db_index=True, null=True)),
                ("username", models.CharField(blank=True, default="", max_length=150)),
                ("source", models.CharField(blank=True, default="", max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "kardex_change_logs",
                "ordering": ["-created_at", "-id"],
                "managed": True,
            },
        ),
        migrations.AddIndex(
            model_name="kardexchangelog",
            index=models.Index(fields=["kardex", "-created_at"], name="kardex_chan_kardex_idx"),
        ),
        migrations.AddIndex(
            model_name="kardexchangelog",
            index=models.Index(fields=["table_name", "-created_at"], name="kardex_chan_table_idx"),
        ),
        migrations.AddIndex(
            model_name="kardexchangelog",
            index=models.Index(fields=["user_id", "-created_at"], name="kardex_chan_user_idx"),
        ),
    ]
