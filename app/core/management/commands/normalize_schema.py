"""
normalize_schema management command
===================================

Purpose
-------
Safely align a live MariaDB schema with your Django models by:
- Creating missing tables (optional, via --create-tables)
- Adding any missing columns to existing tables

This command is additive-only. It never drops, renames, or alters existing columns.
It aims to be a pragmatic normalizer for legacy or backup databases that may be
missing fields or entire tables compared to your current Django models.

Usage
-----
Dry-run (preview changes only):
    python manage.py normalize_schema notaria --dry-run

Create missing tables and preview:
    python manage.py normalize_schema notaria --create-tables --dry-run

Apply changes:
    python manage.py normalize_schema notaria

Create missing tables and apply:
    python manage.py normalize_schema notaria --create-tables

Behavior
--------
- Scopes to a single Django app label (e.g., "notaria").
- For each model:
  * If the table is missing and --create-tables is set:
      - Generates a basic CREATE TABLE with primary key and columns inferred
        from model fields (conservative SQL types).
  * If the table exists:
      - Compares existing columns against model fields and runs:
            ALTER TABLE <table> ADD COLUMN IF NOT EXISTS <column> <type> NULL
        for any missing columns.
- Skips M2M and reverse relations.
- Skips non-additive operations (no drops, renames, or type changes).

Type Mapping (MariaDB 10.5+)
----------------------------
- AutoField        -> INT
- BigAutoField     -> BIGINT
- CharField        -> VARCHAR(max_length)
- TextField        -> TEXT
- IntegerField     -> INT
- BigIntegerField  -> BIGINT
- SmallIntegerField-> SMALLINT
- BooleanField     -> TINYINT(1)
- DateField        -> DATE
- DateTimeField    -> DATETIME
- FloatField       -> DOUBLE
- DecimalField     -> DECIMAL(max_digits, decimal_places)
- BinaryField      -> BLOB
- JSONField        -> JSON
- UUIDField        -> CHAR(32)

Safety Notes
------------
- Designed for MariaDB/MySQL; tested with MariaDB 10.5.
- Assumes default database/schema (uses DATABASE()).
- Generated columns default to NULL to avoid intrusive constraints.
- Foreign key constraints and secondary indexes are not created by this tool.

Limitations
-----------
- Does not handle renames, type changes, drops, or index/constraint creation.
- CREATE TABLE output is intentionally minimal (no FKs or indexes).
- If your models rely on complex constraints or custom SQL, use Django migrations.

Exit Status and Output
----------------------
- Prints each action taken (or [DRY-RUN] for previews).
- Exits successfully even if some statements fail, while logging a warning.
"""
from typing import Dict, Optional, Tuple
from django.core.management.base import BaseCommand
from django.db import connection
from django.apps import apps
from django.db.models import (
    Field, CharField, TextField, IntegerField, BigIntegerField, SmallIntegerField,
    BooleanField, DateField, DateTimeField, FloatField, DecimalField, BinaryField,
    JSONField, ForeignKey, AutoField, BigAutoField, UUIDField
)


class Command(BaseCommand):
    help = "Safely normalizes MariaDB schema by adding missing columns for the given app's models. Optionally creates missing tables."

    def add_arguments(self, parser):
        parser.add_argument(
            "app_label",
            type=str,
            help="Django app label to normalize (e.g., notaria)",
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

    def handle(self, *args, **options):
        app_label: str = options["app_label"]
        dry_run: bool = options["dry_run"]
        create_tables: bool = options["create_tables"]

        try:
            app_config = apps.get_app_config(app_label)
        except LookupError:
            self.stderr.write(self.style.ERROR(f"App '{app_label}' not found"))
            return

        with connection.cursor() as cursor:
            for model in app_config.get_models():
                table_name = model._meta.db_table
                if not self._table_exists(cursor, table_name):
                    if not create_tables:
                        self.stdout.write(self.style.WARNING(f"Table '{table_name}' does not exist; skipping"))
                        continue
                    create_sql = self._generate_create_table_sql(model)
                    if not create_sql:
                        self.stdout.write(self.style.WARNING(f"Table '{table_name}' does not exist and could not generate CREATE TABLE; skipping"))
                        continue
                    if dry_run:
                        self.stdout.write(self.style.NOTICE(f"[DRY-RUN] {create_sql};"))
                    else:
                        try:
                            cursor.execute(create_sql)
                            self.stdout.write(self.style.SUCCESS(f"Created table '{table_name}'"))
                        except Exception as exc:
                            self.stderr.write(self.style.WARNING(f"Failed to create table '{table_name}': {exc}"))
                            continue

                existing_columns = self._fetch_existing_columns(cursor, table_name)
                for field in model._meta.get_fields():
                    column_name, column_sql = self._field_to_sql(field)
                    if not column_name or not column_sql:
                        continue
                    if column_name in existing_columns:
                        continue
                    alter = f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column_name} {column_sql} NULL"
                    if dry_run:
                        self.stdout.write(self.style.NOTICE(f"[DRY-RUN] {alter};"))
                    else:
                        try:
                            cursor.execute(alter)
                            self.stdout.write(self.style.SUCCESS(f"Added column {table_name}.{column_name}"))
                        except Exception as exc:
                            self.stderr.write(self.style.WARNING(f"Failed to add {table_name}.{column_name}: {exc}"))

        if dry_run:
            self.stdout.write(self.style.SUCCESS("Dry run completed"))
        else:
            self.stdout.write(self.style.SUCCESS("Normalization completed"))

    def _table_exists(self, cursor, table_name: str) -> bool:
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
              AND table_name = %s
            """,
            [table_name],
        )
        return cursor.fetchone()[0] > 0

    def _fetch_existing_columns(self, cursor, table_name: str) -> Dict[str, str]:
        cursor.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = DATABASE()
              AND table_name = %s
            """,
            [table_name],
        )
        return {row[0]: row[1] for row in cursor.fetchall()}

    def _field_to_sql(self, field) -> Tuple[Optional[str], Optional[str]]:
        # Skip M2M and reverse relations
        if not isinstance(field, Field):
            return None, None
        if getattr(field, "many_to_many", False) or getattr(field, "one_to_many", False):
            return None, None

        column_name = getattr(field, "column", None)
        if not column_name:
            return None, None

        # Primary key auto fields are likely present; skip creating
        if isinstance(field, (AutoField, BigAutoField)):
            return None, None

        # ForeignKey uses the DB type of its target column (usually INT/BIGINT)
        if isinstance(field, ForeignKey):
            internal_type = field.target_field.get_internal_type()
            sql_type = self._map_internal_type(internal_type, field)
            return column_name, sql_type

        internal_type = field.get_internal_type()
        sql_type = self._map_internal_type(internal_type, field)
        return column_name, sql_type

    def _generate_create_table_sql(self, model) -> Optional[str]:
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

            # Primary key handling
            if getattr(field, "primary_key", False):
                # Choose a sensible SQL type for PK
                internal_type = field.get_internal_type()
                sql_type = self._map_internal_type(internal_type, field)
                # Prefer AUTO_INCREMENT only for integer-like PKs
                if internal_type in ("AutoField", "BigAutoField", "IntegerField", "BigIntegerField", "PositiveIntegerField", "PositiveBigIntegerField"):
                    column_defs.append(f"  {column_name} {sql_type} NOT NULL AUTO_INCREMENT")
                else:
                    column_defs.append(f"  {column_name} {sql_type} NOT NULL")
                primary_keys.append(column_name)
                continue

            # Non-PK fields
            if isinstance(field, ForeignKey):
                internal_type = field.target_field.get_internal_type()
                sql_type = self._map_internal_type(internal_type, field)
            else:
                internal_type = field.get_internal_type()
                sql_type = self._map_internal_type(internal_type, field)

            if not sql_type:
                continue
            # Default to NULL to be non-intrusive
            column_defs.append(f"  {column_name} {sql_type} NULL")

        if not column_defs:
            return None

        pk_clause = ""
        if primary_keys:
            pk_cols = ", ".join(primary_keys)
            pk_clause = f",\n  PRIMARY KEY ({pk_cols})"

        columns_sql = ",\n".join(column_defs) + pk_clause
        return f"CREATE TABLE {table_name} (\n{columns_sql}\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"

    def _map_internal_type(self, internal_type: str, field: Field) -> Optional[str]:
        # Map Django field internal types to MariaDB column types (conservative, NULL by default)
        if internal_type == "AutoField":
            return "INT"
        if internal_type == "BigAutoField":
            return "BIGINT"
        if internal_type == "CharField":
            max_length = getattr(field, "max_length", 255) or 255
            return f"VARCHAR({max_length})"
        if internal_type == "TextField":
            return "TEXT"
        if internal_type in ("IntegerField", "PositiveIntegerField"):
            return "INT"
        if internal_type in ("BigIntegerField", "PositiveBigIntegerField"):
            return "BIGINT"
        if internal_type in ("SmallIntegerField", "PositiveSmallIntegerField"):
            return "SMALLINT"
        if internal_type == "BooleanField":
            return "TINYINT(1)"
        if internal_type == "DateField":
            return "DATE"
        if internal_type == "DateTimeField":
            return "DATETIME"
        if internal_type == "FloatField":
            return "DOUBLE"
        if internal_type == "DecimalField":
            max_digits = getattr(field, "max_digits", 10) or 10
            decimal_places = getattr(field, "decimal_places", 2) or 2
            return f"DECIMAL({max_digits},{decimal_places})"
        if internal_type == "BinaryField":
            return "BLOB"
        if internal_type == "JSONField":
            # MariaDB 10.5 stores JSON as LONGTEXT with validation; using JSON type is fine too
            return "JSON"
        if internal_type == "UUIDField":
            return "CHAR(32)"

        # Fallback to TEXT to avoid type errors on unknown mappings
        return "TEXT"
