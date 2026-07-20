# Generated manually for CorrelativeCounter

from django.db import migrations, models


def seed_counters_from_notarizations(apps, schema_editor):
    Notarization = apps.get_model("signatum", "Notarization")
    CorrelativeCounter = apps.get_model("signatum", "CorrelativeCounter")

    latest_by_key = {}
    for row in Notarization.objects.all().order_by("id"):
        year = row.created_at.year if row.created_at else None
        if year is None:
            continue
        key = (year, row.idtipkar)
        latest_by_key[key] = row

    for (year, idtipkar), last in latest_by_key.items():
        try:
            next_esc = int(str(last.num_escritura or "").strip() or "0") + 1
        except ValueError:
            next_esc = 1
        try:
            next_min = int(str(last.num_minuta or "").strip() or "0") + 1
        except ValueError:
            next_min = 1
        if next_esc < 1:
            next_esc = 1
        if next_min < 1:
            next_min = 1
        CorrelativeCounter.objects.update_or_create(
            year=year,
            idtipkar=idtipkar,
            defaults={
                "next_num_escritura": next_esc,
                "next_num_minuta": next_min,
                "last_folio": (last.folio_fin or last.folio_ini or "").strip(),
            },
        )


def unseed_counters(apps, schema_editor):
    CorrelativeCounter = apps.get_model("signatum", "CorrelativeCounter")
    CorrelativeCounter.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("signatum", "0002_serienotarial"),
    ]

    operations = [
        migrations.CreateModel(
            name="CorrelativeCounter",
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
                ("year", models.PositiveIntegerField()),
                ("idtipkar", models.IntegerField()),
                ("next_num_escritura", models.PositiveIntegerField(default=1)),
                ("next_num_minuta", models.PositiveIntegerField(default=1)),
                (
                    "last_folio",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Last committed folio_fin; next reserve bumps from this.",
                        max_length=30,
                    ),
                ),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ("-year", "idtipkar"),
            },
        ),
        migrations.AddConstraint(
            model_name="correlativecounter",
            constraint=models.UniqueConstraint(
                fields=("year", "idtipkar"),
                name="signatum_correlative_counter_year_idtipkar_uniq",
            ),
        ),
        migrations.RunPython(seed_counters_from_notarizations, unseed_counters),
    ]
