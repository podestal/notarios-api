from django.db import migrations


def add_fields_if_not_exist(apps, schema_editor):
    # Skip if not MySQL
    if schema_editor.connection.vendor != 'mysql':
        return

    # Fields to add with their definitions
    fields = {
        'recibo_empresa': 'VARCHAR(200)',
        'fecha_ocupa': 'DATE',
        'declara_ser': 'VARCHAR(200)',
        'propietario': 'VARCHAR(200)',
        'recibido': 'VARCHAR(200)',
        'numero_recibo': 'VARCHAR(60)',
        'mes_facturado': 'VARCHAR(60)'
    }

    # Check and add each field
    with schema_editor.connection.cursor() as cursor:
        for field_name, field_type in fields.items():
            # Check if field exists
            cursor.execute("""
                SELECT COUNT(*)
                FROM information_schema.columns
                WHERE table_schema = DATABASE()
                AND table_name = 'cert_domiciliario'
                AND column_name = %s
            """, [field_name])
            
            if cursor.fetchone()[0] == 0:
                # Field doesn't exist, so add it
                cursor.execute(f"""
                    ALTER TABLE cert_domiciliario
                    ADD COLUMN {field_name} {field_type} NULL
                """)


def reverse_migration(apps, schema_editor):
    # Skip if not MySQL
    if schema_editor.connection.vendor != 'mysql':
        return

    # Fields to remove
    fields = [
        'recibo_empresa',
        'fecha_ocupa',
        'declara_ser',
        'propietario',
        'recibido',
        'numero_recibo',
        'mes_facturado'
    ]

    # Check and remove each field
    with schema_editor.connection.cursor() as cursor:
        for field_name in fields:
            # Check if field exists
            cursor.execute("""
                SELECT COUNT(*)
                FROM information_schema.columns
                WHERE table_schema = DATABASE()
                AND table_name = 'cert_domiciliario'
                AND column_name = %s
            """, [field_name])
            
            if cursor.fetchone()[0] > 0:
                # Field exists, so remove it
                cursor.execute(f"""
                    ALTER TABLE cert_domiciliario
                    DROP COLUMN {field_name}
                """)


class Migration(migrations.Migration):

    dependencies = []  # No dependencies needed

    operations = [
        migrations.RunPython(
            add_fields_if_not_exist,
            reverse_migration
        )
    ] 