from django.db import migrations


def add_numdoc_plantilla_if_not_exists(apps, schema_editor):
    # Skip if not MySQL
    if schema_editor.connection.vendor != 'mysql':
        return

    # Check if column exists
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("""
            SELECT COUNT(*)
            FROM information_schema.columns
            WHERE table_schema = DATABASE()
            AND table_name = 'libros'
            AND column_name = 'numdoc_plantilla'
        """)
        if cursor.fetchone()[0] == 0:
            # Column doesn't exist, so add it
            cursor.execute("""
                ALTER TABLE libros
                ADD COLUMN numdoc_plantilla VARCHAR(11) NULL
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
            AND table_name = 'libros'
            AND column_name = 'numdoc_plantilla'
        """)
        if cursor.fetchone()[0] > 0:
            # Column exists, so remove it
            cursor.execute("""
                ALTER TABLE libros
                DROP COLUMN numdoc_plantilla
            """)


class Migration(migrations.Migration):

    dependencies = [
        ('notaria', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(
            add_numdoc_plantilla_if_not_exists,
            reverse_migration
        )
    ] 