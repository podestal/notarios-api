"""
Enrich SISGEN send/search rows with last submission + sync status.
"""

from __future__ import annotations

from typing import Any, Dict, List

from notaria.models import Kardex
from sisgen.models import SisgenSoapResponse
from sisgen.services.sisgen_soap_response import (
    SISGEN_IT_CONTACT_NOTE,
    extract_submission_errors,
)
from sisgen.services.sync_status import (
    build_sisgen_sync_status,
    merge_last_submission_for_row,
    status_ui_from_document_status,
)


def last_submission_from_soap_obj(obj: SisgenSoapResponse) -> Dict[str, Any]:
    payload = obj.parsed_payload or {}
    errors = extract_submission_errors(
        payload,
        soap_return_message=obj.soap_return_message or "",
        document_status=obj.document_status or "",
        soap_return_status=obj.soap_return_status or "",
    )
    remote_ui = status_ui_from_document_status(obj.document_status or "")
    if errors and remote_ui == "pendiente":
        remote_ui = "fallido"
    last = {
        "exists": True,
        "created_at": obj.created_at.isoformat(),
        "batch_index": obj.batch_index,
        "http_status": obj.http_status,
        "soap_return_status": obj.soap_return_status,
        "soap_return_message": obj.soap_return_message,
        "document_status": obj.document_status,
        "remote_status_ui": remote_ui,
        "status_ui": remote_ui,
        "errors": errors,
        "has_errors": bool(errors),
    }
    note = payload.get("nota_contacto_it") or (payload.get("user_facing") or {}).get(
        "nota_contacto_it"
    )
    if note:
        last["nota_contacto_it"] = note
    elif errors:
        last["nota_contacto_it"] = SISGEN_IT_CONTACT_NOTE
    return last


def attach_last_submission_status(rows: list) -> list:
    kardexes = [
        str(r.get("kardex") or "").strip()
        for r in rows
        if str(r.get("kardex") or "").strip()
    ]
    if not kardexes:
        return rows

    seen = set()
    ordered_unique = []
    for k in kardexes:
        if k not in seen:
            seen.add(k)
            ordered_unique.append(k)

    estado_by_kardex = {
        row["kardex"]: row["estado_sisgen"]
        for row in Kardex.objects.filter(kardex__in=ordered_unique).values(
            "kardex", "estado_sisgen"
        )
    }

    latest_by_kardex = {}
    qs = SisgenSoapResponse.objects.filter(kardex__in=ordered_unique).order_by(
        "kardex", "-created_at"
    )
    for obj in qs:
        if obj.kardex not in latest_by_kardex:
            latest_by_kardex[obj.kardex] = last_submission_from_soap_obj(obj)

    for row in rows:
        k = str(row.get("kardex") or "").strip()
        estado_raw = row.get("estado_sisgen_code")
        if estado_raw is None and k in estado_by_kardex:
            estado_raw = estado_by_kardex[k]
        last = latest_by_kardex.get(k, {"exists": False})
        sync = build_sisgen_sync_status(estado_raw, last)
        row["sisgen_status"] = sync
        row["sisgen_last_submission"] = merge_last_submission_for_row(last, sync)
        row["estado_sisgen_code"] = sync["estado_sisgen_code"]
        if sync["needs_resubmit"]:
            row["estado_sisgen"] = sync["estado_sisgen_label"]
    return rows


def enrich_send_result(combined_result: Dict[str, Any], documents: List[Dict[str, Any]]) -> None:
    if not combined_result.get("processed_kardex"):
        return

    submission_rows = [{"kardex": k} for k in combined_result["processed_kardex"]]
    enriched = attach_last_submission_status(submission_rows)
    by_kardex = {
        row["kardex"]: row.get("sisgen_last_submission") or {"exists": False}
        for row in enriched
        if row.get("kardex")
    }
    combined_result["sisgen_last_submission_by_kardex"] = by_kardex
    if len(documents) == 1:
        k0 = documents[0]["kardex"]
        combined_result["sisgen_last_submission"] = by_kardex.get(k0, {"exists": False})
