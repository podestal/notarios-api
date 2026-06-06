"""
Django command to wait for configured databases to be available.
"""
import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connections
from django.db.utils import OperationalError


class Command(BaseCommand):
    """Wait until every entry in DATABASES accepts a connection."""

    def handle(self, *args, **options):
        aliases = list(settings.DATABASES.keys())
        self.stdout.write(f"Waiting for database(s): {', '.join(aliases)}")

        pending = set(aliases)
        while pending:
            ready = []
            for alias in pending:
                try:
                    connections[alias].ensure_connection()
                    ready.append(alias)
                except OperationalError:
                    self.stdout.write(
                        f"Database '{alias}' unavailable, waiting 1 second..."
                    )
            for alias in ready:
                pending.discard(alias)
                self.stdout.write(self.style.SUCCESS(f"Database '{alias}' available!"))
            if pending:
                time.sleep(1)
