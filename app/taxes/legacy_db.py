from django.db import connections

POSTGRES_DB = "postgres"


def next_serial_ids(
    table: str,
    pk_column: str,
    count: int = 1,
    *,
    using: str = POSTGRES_DB,
) -> list[int]:
    """
    Allocate one or more PKs for a legacy Postgres table.

    Syncs the serial sequence to MAX(pk) once, then advances it `count` times.
    Uses a transaction-scoped advisory lock to avoid duplicate IDs under concurrency
    or when allocating multiple rows before insert (e.g. bulk_create).
    """
    if not table.isidentifier() or not pk_column.isidentifier():
        raise ValueError("Invalid table or column name")
    if count < 1:
        return []

    lock_key = f"{table}.{pk_column}"

    with connections[using].cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", [lock_key])
        cursor.execute(
            f"""
            SELECT setval(
                pg_get_serial_sequence(%s, %s),
                COALESCE((SELECT MAX({pk_column}) FROM {table}), 0)
            )
            """,
            [table, pk_column],
        )

        ids = []
        for _ in range(count):
            cursor.execute(
                "SELECT nextval(pg_get_serial_sequence(%s, %s))",
                [table, pk_column],
            )
            row = cursor.fetchone()
            if not row or row[0] is None:
                raise RuntimeError(f"No serial sequence for {table}.{pk_column}")
            ids.append(int(row[0]))

    return ids


def next_serial_id(table: str, pk_column: str, *, using: str = POSTGRES_DB) -> int:
    return next_serial_ids(table, pk_column, 1, using=using)[0]
