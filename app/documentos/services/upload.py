"""Persist uploaded PDFs under documentos_notaria and parse them."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, BinaryIO, Dict, Optional

from django.db import transaction

from documentos.models import DocumentoBien
from documentos.services.boleta_vehicular_parser import (
    parse_boleta_vehicular_text,
    partida_from_parsed,
    placa_from_parsed,
)
from documentos.services.pdf_text import extract_pdf_text
from documentos.storage import absolute_path, ensure_tipo_dir, tipo_subdir


def _safe_filename(original: str) -> str:
    base = Path(original or "boleta.pdf").name
    stem = Path(base).stem[:80] or "boleta"
    suffix = Path(base).suffix.lower() or ".pdf"
    if suffix != ".pdf":
        suffix = ".pdf"
    token = uuid.uuid4().hex[:12]
    return f"{stem}_{token}{suffix}"


@transaction.atomic
def submit_documento_vehicular(
    *,
    uploaded_file: BinaryIO,
    original_filename: str,
    uploaded_by=None,
    content_type: str = "application/pdf",
) -> DocumentoBien:
    """
    Save PDF to DOCUMENTOS_NOTARIA_ROOT/vehiculares, parse SUNARP boleta, store JSON.
    """
    data = uploaded_file.read()
    if not data:
        raise ValueError("Empty file")
    if not (original_filename or "").lower().endswith(".pdf") and not str(
        content_type or ""
    ).lower().endswith("pdf"):
        # Still allow if bytes look like PDF.
        if not data[:5].startswith(b"%PDF"):
            raise ValueError("Only PDF uploads are supported")

    tipo = DocumentoBien.TIPO_VEHICULAR
    stored_name = _safe_filename(original_filename)
    relative = f"{tipo_subdir(tipo)}/{stored_name}"
    target_dir = ensure_tipo_dir(tipo)
    target_path = target_dir / stored_name
    target_path.write_bytes(data)

    doc = DocumentoBien.objects.create(
        tipo=tipo,
        original_filename=Path(original_filename or stored_name).name,
        stored_filename=stored_name,
        relative_path=relative,
        content_type=content_type or "application/pdf",
        file_size=len(data),
        status=DocumentoBien.STATUS_PENDING,
        uploaded_by=uploaded_by if getattr(uploaded_by, "is_authenticated", False) else None,
    )

    try:
        raw_text = extract_pdf_text(data)
        parsed = parse_boleta_vehicular_text(raw_text)
        doc.raw_text = raw_text
        doc.parsed = parsed
        doc.placa = placa_from_parsed(parsed)
        doc.partida = partida_from_parsed(parsed)
        doc.oficina = str((parsed.get("meta") or {}).get("oficina") or "")
        doc.status = DocumentoBien.STATUS_PARSED
        doc.parse_error = ""
        doc.save(
            update_fields=[
                "raw_text",
                "parsed",
                "placa",
                "partida",
                "oficina",
                "status",
                "parse_error",
                "updated_at",
            ]
        )
    except Exception as exc:
        doc.status = DocumentoBien.STATUS_ERROR
        doc.parse_error = str(exc)
        doc.save(update_fields=["status", "parse_error", "updated_at"])
        # Keep the file on disk for retry; surface error via status.
    return doc


def documento_absolute_path(doc: DocumentoBien) -> Path:
    return absolute_path(doc.relative_path)


def list_documentos_vehiculares():
    return DocumentoBien.objects.filter(tipo=DocumentoBien.TIPO_VEHICULAR).order_by(
        "-created_at"
    )


@transaction.atomic
def delete_documento_bien(doc: DocumentoBien) -> None:
    """Delete DB row and remove the stored PDF if present."""
    rel = doc.relative_path
    doc.delete()
    if not rel:
        return
    try:
        path = absolute_path(rel)
    except ValueError:
        return
    if path.is_file():
        path.unlink()


def documento_to_dict(doc: DocumentoBien) -> Dict[str, Any]:
    return {
        "id": doc.id,
        "tipo": doc.tipo,
        "status": doc.status,
        "original_filename": doc.original_filename,
        "stored_filename": doc.stored_filename,
        "relative_path": doc.relative_path,
        "file_size": doc.file_size,
        "placa": doc.placa,
        "partida": doc.partida,
        "oficina": doc.oficina,
        "parsed": doc.parsed,
        "parse_error": doc.parse_error,
        "detveh": doc.detveh,
        "kardex": doc.kardex,
        "idtipacto": doc.idtipacto,
        "linked": doc.detveh is not None,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
    }
