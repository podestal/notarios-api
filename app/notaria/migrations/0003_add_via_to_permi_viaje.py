from django.db import migrations


def add_missing_columns_to_permi_viaje(apps, schema_editor):
    # Skip if not MySQL
    if schema_editor.connection.vendor != 'mysql':
        return

    with schema_editor.connection.cursor() as cursor:
        # First, check which columns exist
        cursor.execute("""
            SELECT COLUMN_NAME 
            FROM information_schema.columns 
            WHERE table_schema = DATABASE()
            AND table_name = 'permi_viaje'
        """)
        existing_columns = {row[0] for row in cursor.fetchall()}

        # Define the columns we want to ensure exist
        columns_to_add = {
            'via': 'VARCHAR(255)',
            'fecha_desde': 'DATE',
            'fecha_hasta': 'DATE'
        }

        # Add any missing columns
        for col_name, col_type in columns_to_add.items():
            if col_name not in existing_columns:
                cursor.execute(f"""
                    ALTER TABLE permi_viaje
                    ADD COLUMN {col_name} {col_type} NULL
                """)


def reverse_migration(apps, schema_editor):
    # Skip if not MySQL
    if schema_editor.connection.vendor != 'mysql':
        return

    # Check and remove columns if they exist
    with schema_editor.connection.cursor() as cursor:
        columns_to_remove = ['via', 'fecha_desde', 'fecha_hasta']
        
        for col_name in columns_to_remove:
            cursor.execute("""
                SELECT COUNT(*)
                FROM information_schema.columns
                WHERE table_schema = DATABASE()
                AND table_name = 'permi_viaje'
                AND column_name = %s
            """, [col_name])
            
            if cursor.fetchone()[0] > 0:
                cursor.execute(f"""
                    ALTER TABLE permi_viaje
                    DROP COLUMN {col_name}
                """)


class Migration(migrations.Migration):

    dependencies = [
        ('notaria', '0002_add_numdoc_plantilla'),
    ]

    operations = [
        migrations.RunPython(
            add_missing_columns_to_permi_viaje,
            reverse_migration
        )
    ] 