from django.db import migrations


def add_dni_destinatario_if_not_exists(apps, schema_editor):
    # Skip if not MySQL
    if schema_editor.connection.vendor != 'mysql':
        return

    # Check if column exists
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("""
            SELECT COUNT(*)
            FROM information_schema.columns
            WHERE table_schema = DATABASE()
            AND table_name = 'ingreso_cartas'
            AND column_name = 'dni_destinatario'
        """)
        if cursor.fetchone()[0] == 0:
            # Column doesn't exist, so add it
            cursor.execute("""
                ALTER TABLE ingreso_cartas
                ADD COLUMN dni_destinatario VARCHAR(30) NULL
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
            AND table_name = 'ingreso_cartas'
            AND column_name = 'dni_destinatario'
        """)
        if cursor.fetchone()[0] > 0:
            # Column exists, so remove it
            cursor.execute("""
                ALTER TABLE ingreso_cartas
                DROP COLUMN dni_destinatario
            """)


class Migration(migrations.Migration):

    dependencies = [
        ('notaria', '0003_add_via_to_permi_viaje'),
    ]

    operations = [
        migrations.RunPython(
            add_dni_destinatario_if_not_exists,
            reverse_migration
        )
    ] 