from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction


CORE_TABLES = [
    "documentos_logs",
    "documentogenerados",
    "detallemediopago",
    "detallebienes",
    "detallevehicular",
    "predios",
    "renta",
    "patrimonial",
    "detalle_actos_kardex",
    "contratantesxacto",
    "contratantes",
    "kardex",
]

EXTRA_TABLES = [
    "viaje_contratantes",
    "permi_viaje",
    "poderes_contratantes",
    "poderes_fuerareg",
    "poderes_pension",
    "ingreso_poderes",
]


class Command(BaseCommand):
    help = (
        "Preview or delete core protocol data tied to kardex. "
        "Dry-run by default; use --execute to apply."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--execute",
            action="store_true",
            help="Actually delete rows. Without this flag, the command only previews counts.",
        )
        parser.add_argument(
            "--include-extras",
            action="store_true",
            help="Also delete related poderes/permisos tables tied to kardex workflows.",
        )
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Skip interactive confirmation prompt when using --execute.",
        )

    def handle(self, *args, **options):
        execute = options["execute"]
        include_extras = options["include_extras"]
        skip_confirm = options["yes"]

        tables = list(CORE_TABLES)
        if include_extras:
            tables = EXTRA_TABLES + tables

        self.stdout.write(self.style.WARNING("Core protocol data reset helper"))
        self.stdout.write("Mode: {}".format("EXECUTE" if execute else "DRY-RUN"))
        self.stdout.write(
            "Tables in scope: {}".format(", ".join(tables))
        )
        self.stdout.write("")

        counts = self._fetch_counts(tables)
        self._print_counts(counts)

        if not execute:
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING(
                    "Dry-run only. Re-run with --execute to delete these rows."
                )
            )
            return

        if not skip_confirm:
            confirm = input(
                "Type DELETE CORE DATA to continue: "
            ).strip()
            if confirm != "DELETE CORE DATA":
                raise CommandError("Confirmation text did not match. Aborting.")

        self.stdout.write("")
        self.stdout.write(self.style.WARNING("Deleting rows inside one transaction..."))

        with transaction.atomic():
            deleted = self._delete_tables(tables)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Reset completed successfully."))
        for table_name, deleted_rows in deleted:
            self.stdout.write(f"  {table_name}: {deleted_rows} rows deleted")

    def _fetch_counts(self, tables):
        counts = []
        with connection.cursor() as cursor:
            for table_name in tables:
                cursor.execute(f"SELECT COUNT(*) FROM `{table_name}`")
                counts.append((table_name, cursor.fetchone()[0]))
        return counts

    def _print_counts(self, counts):
        total = 0
        for table_name, count in counts:
            total += count
            self.stdout.write(f"  {table_name}: {count} rows")
        self.stdout.write("")
        self.stdout.write(f"Total rows in scope: {total}")

    def _delete_tables(self, tables):
        deleted = []
        with connection.cursor() as cursor:
            for table_name in tables:
                cursor.execute(f"DELETE FROM `{table_name}`")
                deleted.append((table_name, cursor.rowcount))
        return deleted
