import csv
from django.core.management.base import BaseCommand
from viajes import models

class Command(BaseCommand):
    help = "Import Participante records from a CSV file"

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            required=True,
            help='Path to the CSV file'
        )

    def handle(self, *args, **options):
        file_path = options['file']

        counter = 0
        created_count = 0

        try:
            with open(file_path, newline='', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile, skipinitialspace=True)

                self.stdout.write(self.style.SUCCESS(f"Detected CSV Headers: {reader.fieldnames}"))

                for row in reader:
                    counter += 1
                    try:
                        # Debug: print the row dict to see keys and values
                        self.stdout.write(str(row))

                        # Map CSV fields to model fields correctly
                        participante = models.Participante.objects.create(
                            id_viaje = int(row.get("id_viaje")) if row.get("id_viaje") else None,
                            documento = row.get("c_codcontrat") or None,
                            nombres = row.get("c_descontrat") or None,
                            condicion = row.get("c_condicontrat") or None,
                            edad = row.get("edad") or '',
                            incapacidad = row.get("tip_incapacidad") or '',
                        )
                        created_count += 1
                        self.stdout.write(self.style.SUCCESS(
                            f"Created Participante in Viaje {participante.id_viaje}: {participante.nombres}"
                        ))
                    except Exception as e:
                        self.stderr.write(self.style.ERROR(
                            f"Error processing row {counter}: {e}"
                        ))

        except FileNotFoundError:
            self.stderr.write(self.style.ERROR(f"File not found: {file_path}"))
            return

        self.stdout.write(self.style.SUCCESS(
            f"Import completed. Processed {counter} rows, created {created_count} Participante records."
        ))
