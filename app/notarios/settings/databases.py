"""
Multi-database configuration.

- ``default``: MariaDB/MySQL (legacy notarios schema).
- ``postgres``: optional PostgreSQL (new apps / services).

Enable PostgreSQL by setting POSTGRES_HOST (e.g. ``postgres`` in Docker).
Route apps with POSTGRES_APPS=signatum,compliance (see db_router.py).
"""

import os


def build_databases() -> dict:
    databases = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "HOST": os.environ.get("DATABASE_HOST", "db"),
            "NAME": os.environ.get("DATABASE_NAME", "notarios"),
            "USER": os.environ.get("DATABASE_USER", "root"),
            "PASSWORD": os.environ.get("DATABASE_PASSWORD", ""),
            "PORT": os.environ.get("DATABASE_PORT", "3306"),
            "OPTIONS": {
                "charset": "utf8mb4",
            },
        }
    }

    if os.environ.get("POSTGRES_HOST", "").strip():
        pg_name = (
            os.environ.get("POSTGRES_NAME", "").strip()
            or os.environ.get("POSTGRES_DB", "").strip()
            or "notarios_pg"
        )
        databases["postgres"] = {
            "ENGINE": "django.db.backends.postgresql",
            "HOST": os.environ.get("POSTGRES_HOST", "postgres"),
            "NAME": pg_name,
            "USER": os.environ.get("POSTGRES_USER", "postgres"),
            "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
            "PORT": os.environ.get("POSTGRES_PORT", "5432"),
            "OPTIONS": {
                "options": "-c search_path=almacen,public",
            },
        }

    return databases


def postgres_enabled() -> bool:
    return bool(os.environ.get("POSTGRES_HOST", "").strip())


def postgres_app_labels() -> frozenset:
    raw = os.environ.get("POSTGRES_APPS", "")
    labels = {
        label.strip()
        for label in raw.split(",")
        if label.strip()
    }
    labels.add("taxes")
    return frozenset(labels)
