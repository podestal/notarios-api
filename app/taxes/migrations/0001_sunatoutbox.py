from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="SunatOutbox",
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
                (
                    "kind",
                    models.CharField(
                        choices=[("recibo", "Recibo"), ("resumen", "Resumen")],
                        db_index=True,
                        max_length=16,
                    ),
                ),
                ("target_id", models.PositiveIntegerField(db_index=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("processing", "Processing"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=16,
                    ),
                ),
                (
                    "phase",
                    models.CharField(
                        choices=[("send", "Send"), ("poll", "Poll ticket")],
                        default="send",
                        max_length=8,
                    ),
                ),
                ("attempt_count", models.PositiveIntegerField(default=0)),
                ("max_attempts", models.PositiveIntegerField(default=36)),
                ("next_retry_at", models.DateTimeField(db_index=True)),
                ("last_error", models.TextField(blank=True, default="")),
                (
                    "celery_task_id",
                    models.CharField(blank=True, default="", max_length=255),
                ),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "db_table": "taxes_sunat_outbox",
                "indexes": [
                    models.Index(
                        fields=["status", "next_retry_at"],
                        name="taxes_sunat_ob_st_nr_idx",
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("kind", "target_id"),
                        name="taxes_sunat_ob_kind_tgt_uniq",
                    )
                ],
            },
        ),
    ]
