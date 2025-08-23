from django.db import migrations


def add_via_if_not_exists(apps, schema_editor):
    # Skip if not MySQL
    if schema_editor.connection.vendor != 'mysql':
        return

    # Check if column exists
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("""
            SELECT COUNT(*)
            FROM information_schema.columns
            WHERE table_schema = DATABASE()
            AND table_name = 'permi_viaje'
            AND column_name = 'via'
        """)
        if cursor.fetchone()[0] == 0:
            # Column doesn't exist, so add it
            cursor.execute("""
                ALTER TABLE permi_viaje
                ADD COLUMN via VARCHAR(255) NULL
            """)


def reverse_migration(apps, schema_editor):
    # Skip if not MySQL
    if schema_editor.connection.vendor != 'mysql':
        return

    # Check if column exists before trying to remove it
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("""
            SELECT COUNT(*)
            FROM information_schema.columns
            WHERE table_schema = DATABASE()
            AND table_name = 'permi_viaje'
            AND column_name = 'via'
        """)
        if cursor.fetchone()[0] > 0:
            # Column exists, so remove it
            cursor.execute("""
                ALTER TABLE permi_viaje
                DROP COLUMN via
            """)


class Migration(migrations.Migration):

    dependencies = [
        ('notaria', '0002_add_numdoc_plantilla'),
    ]

    operations = [
        migrations.RunPython(
            add_via_if_not_exists,
            reverse_migration
        )
    ] 