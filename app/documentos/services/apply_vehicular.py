"""Apply a parsed vehicular DocumentoBien into notaria.Detallevehicular."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from django.db import transaction
from django.utils import timezone

from documentos.models import DocumentoBien


def _clip(value: Any, max_len: int) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text[:max_len]


def _vehiculo_payload(doc: DocumentoBien) -> Dict[str, Any]:
    parsed = doc.parsed or {}
    veh = parsed.get("vehiculo") if isinstance(parsed, dict) else None
    return veh if isinstance(veh, dict) else {}


def parsed_to_detalle_fields(
    doc: DocumentoBien,
    *,
    kardex: str,
    idtipacto: str,
) -> Dict[str, Any]:
    veh = _vehiculo_payload(doc)
    placa = _clip(veh.get("placa") or doc.placa, 50)
    if not placa:
        raise ValueError("Parsed document has no placa")

    # Prefer tipo_uso when categoria is blank (common on SUNARP boletas).
    clase = _clip(veh.get("categoria") or veh.get("tipo_uso"), 50)
    # Detallevehicular.idplaca is a short plate-type code used in the UI as "P".
    return {
        "kardex": _clip(kardex, 30),
        "idtipacto": _clip(idtipacto, 20),
        "idplaca": "P",
        "numplaca": placa,
        "clase": clase,
        "marca": _clip(veh.get("marca"), 100),
        "anofab": _clip(veh.get("anio_fabricacion"), 30),
        "modelo": _clip(veh.get("modelo"), 100),
        "combustible": _clip(veh.get("combustible"), 100),
        "carroceria": _clip(veh.get("carroceria"), 100),
        "fecinsc": _clip(veh.get("fecha_inscripcion"), 30),
        "color": _clip(veh.get("color_1"), 100),
        "motor": _clip(veh.get("numero_motor"), 100),
        "numcil": _clip(veh.get("numero_cilindros"), 3),
        "numserie": _clip(veh.get("numero_serie"), 30),
        "numrueda": _clip(veh.get("numero_ruedas"), 3),
        "pregistral": _clip(veh.get("partida") or doc.partida, 100),
        # Oficina name is not the sede code; leave empty unless we map it later.
        "idsedereg": "",
    }


def list_pending_vehiculares():
    return DocumentoBien.objects.filter(
        tipo=DocumentoBien.TIPO_VEHICULAR,
        status=DocumentoBien.STATUS_PARSED,
        detveh__isnull=True,
    ).order_by("-created_at")


def _unlink_queryset(qs) -> int:
    """
    Clear detalle/kardex link on DocumentoBien rows and restore ``parsed`` status
    so the boleta shows up again under pendientes.
    """
    return int(
        qs.filter(tipo=DocumentoBien.TIPO_VEHICULAR).update(
            detveh=None,
            kardex="",
            idtipacto="",
            applied_at=None,
            status=DocumentoBien.STATUS_PARSED,
        )
    )


def unlink_documentos_for_detveh(detveh: Optional[int]) -> int:
    """Unlink any DocumentoBien pointing at this detallevehicular pk."""
    if not detveh:
        return 0
    try:
        detveh_id = int(detveh)
    except (TypeError, ValueError):
        return 0
    return _unlink_queryset(DocumentoBien.objects.filter(detveh=detveh_id))


def unlink_documentos_for_detvehs(detvehs) -> int:
    ids = []
    for raw in detvehs or []:
        try:
            ids.append(int(raw))
        except (TypeError, ValueError):
            continue
    if not ids:
        return 0
    return _unlink_queryset(DocumentoBien.objects.filter(detveh__in=ids))


def unlink_documentos_for_kardex_acto(*, kardex: str, idtipacto: str) -> int:
    key = str(kardex or "").strip()
    acto = str(idtipacto or "").strip()
    if not key:
        return 0
    qs = DocumentoBien.objects.filter(tipo=DocumentoBien.TIPO_VEHICULAR, kardex=key)
    if acto:
        qs = qs.filter(idtipacto=acto)
    return _unlink_queryset(qs)


def apply_documento_vehicular_to_detalle(
    *,
    documento_id: int,
    kardex: str,
    idtipacto: str,
    replace_existing: bool = True,
    overwrite_detalle: bool = True,
    detveh: Optional[int] = None,
) -> Tuple[DocumentoBien, Any]:
    """
    Create/update ``detallevehicular`` from a parsed boleta and link ``DocumentoBien.detveh``.

    When ``overwrite_detalle`` is False, an existing detalle (by ``detveh`` or
    kardex+acto) is only linked — form values already saved are preserved.
    """
    from notaria import models

    key = str(kardex or "").strip()
    acto = str(idtipacto or "").strip()
    if not key:
        raise ValueError("kardex is required")
    if not acto:
        raise ValueError("idtipacto is required")

    with transaction.atomic():
        doc = (
            DocumentoBien.objects.select_for_update()
            .filter(pk=documento_id, tipo=DocumentoBien.TIPO_VEHICULAR)
            .first()
        )
        if not doc:
            raise LookupError("Documento vehicular not found")
        if doc.status == DocumentoBien.STATUS_ERROR:
            raise ValueError("Documento has parse errors and cannot be applied")
        if doc.status not in {
            DocumentoBien.STATUS_PARSED,
            DocumentoBien.STATUS_APPLIED,
        }:
            raise ValueError(
                f"Documento status must be parsed/applied, got {doc.status}"
            )

        fields = parsed_to_detalle_fields(doc, kardex=key, idtipacto=acto)
        detalle = None
        if detveh:
            detalle = models.Detallevehicular.objects.filter(detveh=detveh).first()
        if detalle is None and replace_existing:
            detalle = (
                models.Detallevehicular.objects.filter(kardex=key, idtipacto=acto)
                .order_by("detveh")
                .first()
            )

        if detalle:
            if overwrite_detalle:
                for name, value in fields.items():
                    setattr(detalle, name, value)
                detalle.save()
        else:
            detalle = models.Detallevehicular.objects.create(**fields)

        doc.detveh = int(detalle.detveh)
        doc.kardex = key
        doc.idtipacto = acto
        doc.status = DocumentoBien.STATUS_APPLIED
        doc.applied_at = timezone.now()
        doc.save(
            update_fields=[
                "detveh",
                "kardex",
                "idtipacto",
                "status",
                "applied_at",
                "updated_at",
            ]
        )

        models.Kardex.objects.filter(kardex=key).exclude(estado_sisgen=0).update(
            estado_sisgen=0
        )
        return doc, detalle
