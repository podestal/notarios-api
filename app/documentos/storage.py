"""Local filesystem paths for documentos_notaria/{vehiculares,inmuebles}."""

from __future__ import annotations

import os
from pathlib import Path

from django.conf import settings

from documentos.models import DocumentoBien


def documentos_root() -> Path:
    raw = (
        getattr(settings, "DOCUMENTOS_NOTARIA_ROOT", None)
        or os.environ.get("DOCUMENTOS_NOTARIA_ROOT")
        or ""
    ).strip()
    if not raw:
        raise ValueError(
            "DOCUMENTOS_NOTARIA_ROOT is not configured. "
            "Set it in .env (e.g. /mnt/documentos_notaria)."
        )
    return Path(raw)


def tipo_subdir(tipo: str) -> str:
    if tipo == DocumentoBien.TIPO_VEHICULAR:
        return "vehiculares"
    if tipo == DocumentoBien.TIPO_INMUEBLE:
        return "inmuebles"
    raise ValueError(f"Unsupported documento tipo: {tipo}")


def ensure_tipo_dir(tipo: str) -> Path:
    path = documentos_root() / tipo_subdir(tipo)
    path.mkdir(parents=True, exist_ok=True)
    return path


def absolute_path(relative_path: str) -> Path:
    root = documentos_root().resolve()
    full = (root / relative_path).resolve()
    if root not in full.parents and full != root:
        raise ValueError("Resolved path escapes DOCUMENTOS_NOTARIA_ROOT")
    return full
