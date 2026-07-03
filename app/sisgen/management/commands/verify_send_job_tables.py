from django.core.management.base import BaseCommand
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder


class Command(BaseCommand):
    help = "Check SisgenSendJob migration state and MariaDB tables."

    def handle(self, *args, **options):
        tables = set(connection.introspection.table_names())
        job_table = "sisgen_sisgensendjob"
        doc_table = "sisgen_sisgensendjobdocument"

        applied = list(
            MigrationRecorder.Migration.objects.filter(app="sisgen")
            .order_by("name")
            .values_list("name", flat=True)
        )

        self.stdout.write("sisgen migrations applied:")
        for name in applied:
            self.stdout.write(f"  - {name}")

        for table in (job_table, doc_table):
            status = "OK" if table in tables else "MISSING"
            self.stdout.write(f"{table}: {status}")

        if job_table in tables and doc_table in tables:
            self.stdout.write(self.style.SUCCESS("Sisgen send-job tables are ready."))
            return

        self.stdout.write(
            self.style.ERROR(
                "Tables missing but migration may be marked applied. Fix with:\n"
                "  python manage.py migrate sisgen 0002 --fake\n"
                "  python manage.py migrate sisgen"
            )
        )
