from django.db import migrations


def drop_expires_at_if_present(apps, schema_editor):
    """
    Older DBs still have NOT NULL expires_at from a previous 0001.
    The model no longer has that field, so MySQL rejects INSERT without a value.
    """
    connection = schema_editor.connection
    model = apps.get_model("signatum", "NotarizationReservation")
    table = model._meta.db_table

    with connection.cursor() as cursor:
        try:
            description = connection.introspection.get_table_description(cursor, table)
        except Exception:
            return

    names = []
    for col in description:
        names.append(col.name if hasattr(col, "name") else col[0])
    if "expires_at" not in names:
        return

    quoted_table = connection.ops.quote_name(table)
    quoted_col = connection.ops.quote_name("expires_at")
    with connection.cursor() as cursor:
        cursor.execute(f"ALTER TABLE {quoted_table} DROP COLUMN {quoted_col}")


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("signatum", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(drop_expires_at_if_present, noop_reverse),
    ]
