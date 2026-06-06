"""
Route Django apps to MariaDB (default) or PostgreSQL (postgres).

Set POSTGRES_APPS=signatum,myapp so migrations and ORM for those apps use postgres.
Apps not listed keep using default (MariaDB).

Cross-database relations are not supported (Django limitation).
"""

from notarios.settings.databases import postgres_app_labels, postgres_enabled


class PostgresRouter:
    postgres_db = "postgres"
    default_db = "default"

    def _app_on_postgres(self, app_label: str) -> bool:
        return postgres_enabled() and app_label in postgres_app_labels()

    def db_for_read(self, model, **hints):
        if self._app_on_postgres(model._meta.app_label):
            return self.postgres_db
        return self.default_db

    def db_for_write(self, model, **hints):
        if self._app_on_postgres(model._meta.app_label):
            return self.postgres_db
        return self.default_db

    def allow_relation(self, obj1, obj2, **hints):
        db1 = self._app_on_postgres(obj1._meta.app_label)
        db2 = self._app_on_postgres(obj2._meta.app_label)
        if db1 == db2:
            return True
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        on_postgres = self._app_on_postgres(app_label)
        if on_postgres:
            return db == self.postgres_db
        return db == self.default_db
