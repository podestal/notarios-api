# Generated manually for compliance app

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="KardexComplianceCache",
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
                ("kardex", models.CharField(db_index=True, max_length=32, unique=True)),
                (
                    "idkardex",
                    models.CharField(
                        blank=True, db_index=True, default="", max_length=32
                    ),
                ),
                (
                    "idtipkar",
                    models.IntegerField(blank=True, db_index=True, null=True),
                ),
                (
                    "fechaescritura",
                    models.DateField(blank=True, db_index=True, null=True),
                ),
                ("payload", models.JSONField(default=dict)),
                ("uif_error_count", models.PositiveIntegerField(default=0)),
                ("sisgen_error_count", models.PositiveIntegerField(default=0)),
                ("sisgen_observation_count", models.PositiveIntegerField(default=0)),
                ("total_error_count", models.PositiveIntegerField(default=0)),
                ("has_errors", models.BooleanField(db_index=True, default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="compliance_cache_updates",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-updated_at"],
            },
        ),
        migrations.AddIndex(
            model_name="kardexcompliancecache",
            index=models.Index(
                fields=["fechaescritura", "has_errors"],
                name="compliance__fechaesc_8a1f2d_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="kardexcompliancecache",
            index=models.Index(
                fields=["idtipkar", "has_errors"],
                name="compliance__idtipka_4c8e91_idx",
            ),
        ),
    ]
