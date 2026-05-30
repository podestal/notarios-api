"""
Export Python UIF artifacts for side-by-side comparison with legacy PHP.

Example:
  python manage.py uif_parity_export --initialDate 01/04/2026 --finalDate 30/04/2026 \\
      --output app/uif/tests/fixtures/php_parity/2026-04 --write-manifest
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from uif.services.parity import build_python_parity_bundle, write_python_export


class Command(BaseCommand):
    help = "Export Python plane/errors/summary for PHP parity comparison."

    def add_arguments(self, parser):
        parser.add_argument("--initialDate", required=True, help="DD/MM/YYYY or YYYY-MM-DD")
        parser.add_argument("--finalDate", required=True, help="DD/MM/YYYY or YYYY-MM-DD")
        parser.add_argument(
            "--reportPolicy",
            default="all",
            help="all (PHP _arrObjRo) or clean",
        )
        parser.add_argument(
            "--output",
            required=True,
            help="Directory for plane.python.txt, errors.python.json, summary.python.json",
        )
        parser.add_argument(
            "--write-manifest",
            action="store_true",
            help="Also write manifest.json if missing",
        )

    def handle(self, *args, **options):
        initial = options["initialDate"]
        final = options["finalDate"]
        policy = options["reportPolicy"]
        out_dir = Path(options["output"])

        try:
            bundle = build_python_parity_bundle(initial, final, report_policy=policy)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        out_dir.mkdir(parents=True, exist_ok=True)
        write_python_export(out_dir, bundle)

        manifest_path = out_dir / "manifest.json"
        if options["write_manifest"] and not manifest_path.is_file():
            manifest_path.write_text(
                json.dumps(
                    {
                        "initialDate": initial,
                        "finalDate": final,
                        "reportPolicy": policy,
                        "description": "Add plane.php.txt from legacy RoClass generateFileRo",
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Exported {len(bundle['plane_lines'])} plane lines, "
                f"{len(bundle['errors'])} errors, "
                f"{bundle['report_record_count']} report acts → {out_dir}"
            )
        )
