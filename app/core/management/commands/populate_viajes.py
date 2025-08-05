import csv
from django.core.management.base import BaseCommand
from viajes import models
from datetime import datetime

class Command(BaseCommand):
    help = "Import Viaje records from a CSV file"

    def add_arguments(self, parser):
        parser.add_argument('--file', type=str, required=True, help='Path to the CSV file')

    def handle(self, *args, **options):
        file_path = options['file']

        counter = 0
        created_count = 0

        try:
            with open(file_path, newline='', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    counter += 1
                    try:
                        # Parse date fields
                        fec_ingreso = self.parse_date(row.get("fec_ingreso"))
                        fecha_desde = self.parse_date(row.get("fecha_desde"))
                        fecha_hasta = self.parse_date(row.get("fecha_hasta"))

                        viaje = models.Viaje.objects.create(
                            id_viaje = int(row.get("id_viaje")) if row.get("id_viaje") else None,
                            num_kardex = row.get("num_kardex") or None,
                            asunto = row.get("asunto") or None,
                            fecha_ingreso = fec_ingreso,
                            referencia = row.get("referencia") or None,
                            num_formu = row.get("num_formu") or None,
                            lugar_formu = row.get("lugar_formu") or None,
                            observacion = row.get("observacion") or None,
                            sede_regis = row.get("sede_regis") or None,
                            via = row.get("via") or None,
                            fecha_desde = fecha_desde,
                            fecha_hasta = fecha_hasta,
                        )
                        created_count += 1
                        self.stdout.write(self.style.SUCCESS(f"Created Viaje {viaje.id_viaje}"))

                    except Exception as e:
                        self.stderr.write(self.style.ERROR(f"Error processing row {counter}: {e}"))

        except FileNotFoundError:
            self.stderr.write(self.style.ERROR(f"File not found: {file_path}"))
            return

        self.stdout.write(self.style.SUCCESS(f"Import completed. Processed {counter} rows, created {created_count} Viaje records."))

    def parse_date(self, date_str):
        """
        Converts dates like '2/9/21' into datetime.date
        Returns None if empty or invalid.
        """
        if not date_str or date_str.strip() == '\\N':
            return None
        try:
            # Support formats like M/D/YY
            return datetime.strptime(date_str.strip(), '%m/%d/%y').date()
        except ValueError:
            # Try ISO format (YYYY-MM-DD)
            try:
                return datetime.strptime(date_str.strip(), '%Y-%m-%d').date()
            except ValueError:
                self.stderr.write(self.style.WARNING(f"Invalid date format: {date_str}. Skipping date."))
                return None
