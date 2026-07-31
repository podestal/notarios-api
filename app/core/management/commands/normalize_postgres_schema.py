"""
normalize_postgres_schema management command
===========================================

Additive-only schema normalizer for PostgreSQL databases.

Usage:
    python manage.py normalize_postgres_schema taxes --database postgres --dry-run
    python manage.py normalize_postgres_schema taxes --database postgres

It first runs Django migrations for the app on the target database
(e.g. ``migrate taxes --database=postgres`` so ``taxes_sunat_outbox`` exists),
then compares models against the live schema and adds missing columns.
It never drops, renames, or alters existing columns.
"""
from typing import Dict, Optional, Tuple

from django.apps import apps
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connections
from django.db.models import (
    AutoField,
    BigAutoField,
    BigIntegerField,
    BinaryField,
    BooleanField,
    CharField,
    DateField,
    DateTimeField,
    DecimalField,
    Field,
    FloatField,
    ForeignKey,
    IntegerField,
    JSONField,
    SmallIntegerField,
    TextField,
    UUIDField,
)


class Command(BaseCommand):
    help = (
        "Runs Django migrations for the app on PostgreSQL, then safely adds "
        "any remaining missing columns. Optionally creates missing unmanaged tables."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "app_label",
            type=str,
            help="Django app label to normalize (e.g., taxes)",
        )
        parser.add_argument(
            "--database",
            default="postgres",
            help="Django database alias to normalize (default: postgres)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print planned changes without applying them",
        )
        parser.add_argument(
            "--create-tables",
            action="store_true",
            help="Create missing tables using model fields (basic columns and primary key only)",
        )
        parser.add_argument(
            "--skip-migrate",
            action="store_true",
            help="Skip ``migrate <app> --database=<database>`` and only add missing columns",
        )

    def handle(self, *args, **options):
        app_label: str = options["app_label"]
        database: str = options["database"]
        dry_run: bool = options["dry_run"]
        create_tables: bool = options["create_tables"]
        skip_migrate: bool = options["skip_migrate"]

        try:
            app_config = apps.get_app_config(app_label)
        except LookupError:
            self.stderr.write(self.style.ERROR(f"App '{app_label}' not found"))
            return

        if database not in connections:
            self.stderr.write(self.style.ERROR(f"Database alias '{database}' not found"))
            return

        connection = connections[database]
        if connection.vendor != "postgresql":
            self.stderr.write(
                self.style.ERROR(
                    f"Database alias '{database}' is '{connection.vendor}', not postgresql"
                )
            )
            return

        if not skip_migrate:
            self._run_app_migrations(
                app_label=app_label,
                database=database,
                dry_run=dry_run,
            )

        with connection.cursor() as cursor:
            for model in app_config.get_models():
                table_name = model._meta.db_table
                table_ref = self._resolve_table(cursor, table_name)

                if table_ref is None:
                    if not create_tables:
                        self.stdout.write(
                            self.style.WARNING(
                                f"Table '{table_name}' does not exist in the search_path; skipping"
                            )
                        )
                        continue

                    create_sql = self._generate_create_table_sql(model, connection)
                    if not create_sql:
                        self.stdout.write(
                            self.style.WARNING(
                                f"Table '{table_name}' does not exist and could not generate CREATE TABLE; skipping"
                            )
                        )
                        continue

                    if dry_run:
                        self.stdout.write(self.style.NOTICE(f"[DRY-RUN] {create_sql};"))
                    else:
                        try:
                            cursor.execute(create_sql)
                            self.stdout.write(
                                self.style.SUCCESS(f"Created table '{table_name}'")
                            )
                        except Exception as exc:
                            self.stderr.write(
                                self.style.WARNING(
                                    f"Failed to create table '{table_name}': {exc}"
                                )
                            )
                            continue
                    table_ref = self._resolve_table(cursor, table_name)

                if table_ref is None:
                    continue

                existing_columns = self._fetch_existing_columns(cursor, table_ref)
                table_sql = self._quote_table_ref(connection, table_ref)

                for field in model._meta.get_fields():
                    column_name, column_sql = self._field_to_sql(field)
                    if not column_name or not column_sql:
                        continue
                    if column_name in existing_columns:
                        continue

                    column = connection.ops.quote_name(column_name)
                    alter = f"ALTER TABLE {table_sql} ADD COLUMN IF NOT EXISTS {column} {column_sql} NULL"

                    if dry_run:
                        self.stdout.write(self.style.NOTICE(f"[DRY-RUN] {alter};"))
                    else:
                        try:
                            cursor.execute(alter)
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"Added column {table_ref[0]}.{table_ref[1]}.{column_name}"
                                )
                            )
                        except Exception as exc:
                            self.stderr.write(
                                self.style.WARNING(
                                    f"Failed to add {table_ref[0]}.{table_ref[1]}.{column_name}: {exc}"
                                )
                            )

        if dry_run:
            self.stdout.write(self.style.SUCCESS("Dry run completed"))
        else:
            self.stdout.write(self.style.SUCCESS("PostgreSQL normalization completed"))

    def _run_app_migrations(
        self, *, app_label: str, database: str, dry_run: bool
    ) -> None:
        """Apply Django migrations for this app on the target PostgreSQL DB."""
        cmd = f"migrate {app_label} --database={database}"
        if dry_run:
            self.stdout.write(self.style.NOTICE(f"[DRY-RUN] would run: python manage.py {cmd}"))
            try:
                call_command(
                    "migrate",
                    app_label,
                    database=database,
                    plan=True,
                    verbosity=1,
                )
            except TypeError:
                # Older Django without plan= support — notice only.
                pass
            return

        self.stdout.write(self.style.NOTICE(f"Running: python manage.py {cmd}"))
        call_command(
            "migrate",
            app_label,
            database=database,
            verbosity=1,
        )
        self.stdout.write(
            self.style.SUCCESS(f"Migrations applied for '{app_label}' on '{database}'")
        )

    def _resolve_table(self, cursor, table_name: str) -> Optional[Tuple[str, str]]:
        if "." in table_name:
            schema, name = table_name.split(".", 1)
            cursor.execute(
                """
                SELECT table_schema, table_name
                FROM information_schema.tables
                WHERE table_schema = %s
                  AND table_name = %s
                """,
                [schema, name],
            )
            row = cursor.fetchone()
            return (row[0], row[1]) if row else None

        cursor.execute(
            """
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_name = %s
              AND table_schema = ANY (current_schemas(false))
            ORDER BY array_position(current_schemas(false), table_schema)
            LIMIT 1
            """,
            [table_name],
        )
        row = cursor.fetchone()
        return (row[0], row[1]) if row else None

    def _fetch_existing_columns(
        self, cursor, table_ref: Tuple[str, str]
    ) -> Dict[str, str]:
        schema, table_name = table_ref
        cursor.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = %s
              AND table_name = %s
            """,
            [schema, table_name],
        )
        return {row[0]: row[1] for row in cursor.fetchall()}

    def _field_to_sql(self, field) -> Tuple[Optional[str], Optional[str]]:
        if not isinstance(field, Field):
            return None, None
        if getattr(field, "many_to_many", False) or getattr(field, "one_to_many", False):
            return None, None

        column_name = getattr(field, "column", None)
        if not column_name:
            return None, None

        if isinstance(field, (AutoField, BigAutoField)):
            return None, None

        if isinstance(field, ForeignKey):
            internal_type = field.target_field.get_internal_type()
            sql_type = self._map_internal_type(internal_type, field.target_field)
            return column_name, sql_type

        internal_type = field.get_internal_type()
        sql_type = self._map_internal_type(internal_type, field)
        return column_name, sql_type

    def _generate_create_table_sql(self, model, connection) -> Optional[str]:
        table_name = model._meta.db_table
        column_defs = []
        primary_keys = []

        for field in model._meta.get_fields():
            if not isinstance(field, Field):
                continue
            if getattr(field, "many_to_many", False) or getattr(field, "one_to_many", False):
                continue

            column_name = getattr(field, "column", None)
            if not column_name:
                continue

            column = connection.ops.quote_name(column_name)
            internal_type = (
                field.target_field.get_internal_type()
                if isinstance(field, ForeignKey)
                else field.get_internal_type()
            )
            sql_type = self._map_internal_type(internal_type, field)
            if not sql_type:
                continue

            if getattr(field, "primary_key", False):
                pk_type = self._primary_key_type(internal_type, sql_type)
                column_defs.append(f"  {column} {pk_type} NOT NULL")
                primary_keys.append(column)
            else:
                column_defs.append(f"  {column} {sql_type} NULL")

        if not column_defs:
            return None

        pk_clause = ""
        if primary_keys:
            pk_clause = f",\n  PRIMARY KEY ({', '.join(primary_keys)})"

        table_sql = self._quote_table_name(connection, table_name)
        columns_sql = ",\n".join(column_defs) + pk_clause
        return f"CREATE TABLE {table_sql} (\n{columns_sql}\n)"

    def _primary_key_type(self, internal_type: str, sql_type: str) -> str:
        if internal_type == "AutoField":
            return "SERIAL"
        if internal_type == "BigAutoField":
            return "BIGSERIAL"
        return sql_type

    def _quote_table_name(self, connection, table_name: str) -> str:
        if "." not in table_name:
            return connection.ops.quote_name(table_name)
        schema, name = table_name.split(".", 1)
        return (
            f"{connection.ops.quote_name(schema)}."
            f"{connection.ops.quote_name(name)}"
        )

    def _quote_table_ref(self, connection, table_ref: Tuple[str, str]) -> str:
        schema, table_name = table_ref
        return (
            f"{connection.ops.quote_name(schema)}."
            f"{connection.ops.quote_name(table_name)}"
        )

    def _map_internal_type(self, internal_type: str, field: Field) -> Optional[str]:
        if internal_type == "AutoField":
            return "INTEGER"
        if internal_type == "BigAutoField":
            return "BIGINT"
        if internal_type == "CharField":
            max_length = getattr(field, "max_length", 255) or 255
            return f"VARCHAR({max_length})"
        if internal_type == "TextField":
            return "TEXT"
        if internal_type in ("IntegerField", "PositiveIntegerField"):
            return "INTEGER"
        if internal_type in ("BigIntegerField", "PositiveBigIntegerField"):
            return "BIGINT"
        if internal_type in ("SmallIntegerField", "PositiveSmallIntegerField"):
            return "SMALLINT"
        if internal_type == "BooleanField":
            return "BOOLEAN"
        if internal_type == "DateField":
            return "DATE"
        if internal_type == "DateTimeField":
            return "TIMESTAMP"
        if internal_type == "FloatField":
            return "DOUBLE PRECISION"
        if internal_type == "DecimalField":
            max_digits = getattr(field, "max_digits", 10) or 10
            decimal_places = getattr(field, "decimal_places", 2) or 2
            return f"NUMERIC({max_digits},{decimal_places})"
        if internal_type == "BinaryField":
            return "BYTEA"
        if internal_type == "JSONField":
            return "JSONB"
        if internal_type == "UUIDField":
            return "UUID"

        return "TEXT"
