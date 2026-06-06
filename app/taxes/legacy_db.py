from django.db import connections

POSTGRES_DB = "postgres"


def next_serial_id(table: str, pk_column: str, *, using: str = POSTGRES_DB) -> int:
    """
    Next PK for a legacy Postgres table.

    Syncs the serial sequence to MAX(pk) when it has fallen behind imported data.
    """
    if not table.isidentifier() or not pk_column.isidentifier():
        raise ValueError("Invalid table or column name")

    with connections[using].cursor() as cursor:
        cursor.execute(
            f"""
            SELECT setval(
                pg_get_serial_sequence(%s, %s),
                COALESCE((SELECT MAX({pk_column}) FROM {table}), 0)
            )
            """,
            [table, pk_column],
        )
        cursor.execute(
            "SELECT nextval(pg_get_serial_sequence(%s, %s))",
            [table, pk_column],
        )
        row = cursor.fetchone()

    if not row or row[0] is None:
        raise RuntimeError(f"No serial sequence for {table}.{pk_column}")

    return int(row[0])
