# Generated manually for SisgenSendJob models

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sisgen", "0002_sisgensoapresponse"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SisgenSendJob",
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
                    "celery_task_id",
                    models.CharField(
                        blank=True, db_index=True, default="", max_length=255
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("running", "Running"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("payload", models.JSONField(default=dict)),
                ("progress_processed", models.PositiveIntegerField(default=0)),
                ("progress_total", models.PositiveIntegerField(default=0)),
                ("result", models.JSONField(blank=True, null=True)),
                ("error", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sisgen_send_jobs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="SisgenSendJobDocument",
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
                ("kardex", models.CharField(db_index=True, max_length=32)),
                ("idkardex", models.CharField(blank=True, default="", max_length=32)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("running", "Running"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                            ("skipped", "Skipped"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=16,
                    ),
                ),
                ("batch_index", models.PositiveSmallIntegerField(default=0)),
                (
                    "attempt",
                    models.CharField(
                        blank=True,
                        choices=[("batch", "Batch"), ("single", "Single")],
                        default="",
                        max_length=16,
                    ),
                ),
                ("message", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "job",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="documents",
                        to="sisgen.sisgensendjob",
                    ),
                ),
                (
                    "submission_response",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="send_job_documents",
                        to="sisgen.sisgensoapresponse",
                    ),
                ),
            ],
            options={
                "ordering": ["id"],
            },
        ),
        migrations.AddIndex(
            model_name="sisgensendjob",
            index=models.Index(
                fields=["user", "-created_at"], name="sisgen_sisg_user_id_created_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="sisgensendjob",
            index=models.Index(
                fields=["status", "-created_at"], name="sisgen_sisg_status_created_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="sisgensendjobdocument",
            index=models.Index(
                fields=["job", "status"], name="sisgen_sisg_job_id_status_idx"
            ),
        ),
        migrations.AddConstraint(
            model_name="sisgensendjobdocument",
            constraint=models.UniqueConstraint(
                fields=("job", "kardex"), name="sisgen_send_job_document_unique_kardex"
            ),
        ),
    ]
