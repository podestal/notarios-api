"""
Parse SISGEN SOAP responses from setDocumentosNotariales y materializar filas para dashboard.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import defusedxml.ElementTree as ET

logger = logging.getLogger(__name__)

SISGEN_IT_CONTACT_NOTE = (
    "Si el problema persiste, contacte al área de sistemas (IT) e indique el kardex, "
    "la fecha/hora del envío y el mensaje de error mostrado."
)


def soap_response_is_ok(parsed: Dict[str, Any]) -> bool:
    """True when SISGEN SOAP <return><status> is OK."""
    if not parsed:
        return False
    summary = parsed.get("summary") or {}
    if summary.get("soap_level_ok") is True:
        return True
    rs = (parsed.get("return_status") or "").strip().upper()
    return rs == "OK"


def format_soap_return_message(raw: str, *, max_len: int = 600) -> str:
    """First line of SISGEN return message (drops duplicated SAX stack lines)."""
    text = (raw or "").strip()
    if not text:
        return "SISGEN no devolvió detalle del error."
    line = text.splitlines()[0].strip()
    if len(line) > max_len:
        return line[: max_len - 3] + "..."
    return line


SOAP_FAILURE_STATUSES = frozenset(
    {
        "INTERNAL_SERVER_ERROR",
        "ERROR_SOAP",
        "ERROR_RESPUESTA",
        "ERROR_ENVIO",
        "ERROR_PROCESAMIENTO",
        "SIN_ECHO",
    }
)


def is_soap_level_submission_failure(
    *,
    document_status: str = "",
    soap_return_status: str = "",
    parsed_payload: Optional[Dict[str, Any]] = None,
) -> bool:
    """True when the last send failed before/at SOAP (no DocumentoNotarial GUARDADO)."""
    if isinstance(parsed_payload, dict) and parsed_payload.get("soap_failure"):
        return True
    ds = (document_status or "").strip().upper()
    if ds in SOAP_FAILURE_STATUSES or ds.startswith("HTTP_"):
        return True
    rs = (soap_return_status or "").strip().upper()
    if rs in SOAP_FAILURE_STATUSES or rs.startswith("HTTP_"):
        return True
    return False


def extract_submission_errors(
    parsed_payload: Optional[Dict[str, Any]],
    *,
    soap_return_message: str = "",
    document_status: str = "",
    soap_return_status: str = "",
) -> List[str]:
    """
    Errors for ``sisgen_last_submission.errors`` — document-level SISGEN echo or SOAP reject.
    """
    payload = parsed_payload if isinstance(parsed_payload, dict) else {}
    merged: List[str] = []
    seen: set[str] = set()

    def add(msg: Any) -> None:
        text = str(msg or "").strip()
        if not text or text in seen:
            return
        seen.add(text)
        merged.append(text)

    doc = payload.get("document") or {}
    for err in doc.get("errors") or []:
        add(err)

    summary = payload.get("summary") or {}
    for doc_row in summary.get("documents") or []:
        for err in doc_row.get("errors") or []:
            add(err)

    if merged:
        return merged

    user_facing = payload.get("user_facing") or {}
    add(user_facing.get("mensaje_usuario"))
    add(user_facing.get("mensaje_tecnico"))

    if is_soap_level_submission_failure(
        document_status=document_status,
        soap_return_status=soap_return_status,
        parsed_payload=payload,
    ):
        add(format_soap_return_message(soap_return_message))

    note = payload.get("nota_contacto_it") or user_facing.get("nota_contacto_it")
    if note and merged:
        add(note)
    elif note and is_soap_level_submission_failure(
        document_status=document_status,
        soap_return_status=soap_return_status,
        parsed_payload=payload,
    ):
        add(note)

    return merged


def build_soap_failure_entries(
    *,
    parsed: Dict[str, Any],
    batch_documents: List[Dict[str, Any]],
    batch_index: int,
    http_status: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    User-facing rows when SOAP-level send fails (INTERNAL_SERVER_ERROR, parse errors, etc.).
    One entry per kardex in the batch.
    """
    return_status = (parsed.get("return_status") or "").strip()
    status_label = return_status or "ERROR_SOAP"
    if parsed.get("parse_error") and not return_status:
        status_label = "ERROR_RESPUESTA"
    short_msg = format_soap_return_message(parsed.get("return_message") or "")
    if parsed.get("parse_error") == "empty_response":
        short_msg = "SISGEN devolvió una respuesta vacía."
    elif parsed.get("parse_error") == "missing_return_element":
        short_msg = "La respuesta de SISGEN no tiene el formato esperado."

    entries: List[Dict[str, Any]] = []
    for bd in batch_documents:
        kardex = str(bd.get("kardex") or "").strip()
        if not kardex:
            continue
        user_line = (
            f"{kardex}: SISGEN rechazó el envío ({status_label}). {short_msg}"
        )
        entries.append(
            {
                "kardex": kardex,
                "idkardex": str(bd.get("idkardex") or ""),
                "batch": batch_index,
                "estado": status_label,
                "http_status": http_status,
                "soap_return_status": return_status,
                "mensaje_tecnico": (parsed.get("return_message") or short_msg).strip(),
                "mensaje_usuario": user_line,
                "nota_contacto_it": SISGEN_IT_CONTACT_NOTE,
                "parse_error": parsed.get("parse_error"),
            }
        )
    return entries


def user_facing_payload_for_saved_row(
    parsed: Dict[str, Any],
    *,
    kardex: str,
    batch_index: int,
    http_status: Optional[int] = None,
) -> Dict[str, Any]:
    """Extra JSON stored in SisgenSoapResponse.parsed_payload on SOAP failures."""
    entries = build_soap_failure_entries(
        parsed=parsed,
        batch_documents=[{"kardex": kardex}],
        batch_index=batch_index,
        http_status=http_status,
    )
    row = entries[0] if entries else {}
    return {
        "soap_failure": not soap_response_is_ok(parsed),
        "user_facing": row,
        "nota_contacto_it": SISGEN_IT_CONTACT_NOTE,
    }


def _local(tag: str) -> str:
    if tag.startswith("{") and "}" in tag:
        return tag.partition("}")[2]
    return tag


def _text(elem: Optional[ET.Element]) -> str:
    if elem is None or elem.text is None:
        return ""
    return elem.text.strip()


def _find_return(root: ET.Element) -> Optional[ET.Element]:
    """Localiza <return> bajo setDocumentosNotarialesResponse."""
    for el in root.iter():
        if _local(el.tag) == "setDocumentosNotarialesResponse":
            for ch in el:
                if _local(ch.tag) == "return":
                    return ch
            return None
    return None


def _collect_errors_deep(elem: ET.Element) -> List[str]:
    """
    Todos los <ERROR> con texto bajo un fragmento (p.ej. todo DocumentoNotarial).
    SISGEN mete ERRORS vacíos y errores reales repartidos en Maestros/Operaciones/etc.
    """
    seen: set[str] = set()
    out: List[str] = []
    for el in elem.iter():
        if _local(el.tag) != "ERROR":
            continue
        t = _text(el)
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def _maybe_truncate_raw(raw_xml: str) -> tuple[str, Dict[str, Any]]:
    """
    Reduce tamaño en BD; XML SOAP suele repetir todo el envío.
    SISGEN_SOAP_RESPONSE_MAX_RAW_BYTES=0 guarda completo (default previo).
    """
    meta: Dict[str, Any] = {}
    try:
        max_b = int(os.getenv("SISGEN_SOAP_RESPONSE_MAX_RAW_BYTES", str(256 * 1024)))
    except ValueError:
        max_b = 256 * 1024
    if max_b <= 0 or len(raw_xml.encode("utf-8")) <= max_b:
        return raw_xml, meta
    note = f"\n<!-- truncated: SISGEN_SOAP_RESPONSE_MAX_RAW_BYTES={max_b} -->"
    enc = raw_xml.encode("utf-8")[:max_b].decode("utf-8", errors="ignore")
    meta["raw_xml_truncated"] = True
    meta["raw_xml_original_bytes"] = len(raw_xml.encode("utf-8"))
    meta["raw_xml_stored_bytes"] = len(enc.encode("utf-8"))
    return enc + note, meta


def parse_set_documentos_response(xml_text: str) -> Dict[str, Any]:
    """
    Devuelve dict estable para JSONField / dashboard.

    Claves principales:
      ``summary`` — vista compacta (status SOAP, mensaje, lista corta por doc, totales).
      ``documents`` — detalle por documento (incluye ``errors`` de todo el subárbol).
      ``return_status``, ``return_message``, ``generador_datos``, ``parse_error``.
    """
    empty: Dict[str, Any] = {
        "return_status": None,
        "return_message": "",
        "documents": [],
        "generador_datos": None,
    }
    if not (xml_text or "").strip():
        return {**empty, "parse_error": "empty_response"}

    try:
        root = ET.fromstring(xml_text.strip())
    except ET.ParseError as exc:
        logger.warning("SOAP response XML parse error: %s", exc)
        return {**empty, "parse_error": str(exc), "return_message": str(exc)}

    ret = _find_return(root)
    if ret is None:
        return {**empty, "parse_error": "missing_return_element"}

    return_status = None
    return_message = ""
    for ch in ret:
        lt = _local(ch.tag)
        if lt == "status":
            return_status = _text(ch) or None
        elif lt == "message":
            return_message = _text(ch)

    documents: List[Dict[str, Any]] = []
    for dn in root.iter():
        if _local(dn.tag) != "DocumentoNotarial":
            continue
        st_el = None
        doc_el = None
        for ch in dn:
            t = _local(ch.tag)
            if t == "Status":
                st_el = ch
            elif t == "Documento":
                doc_el = ch

        if st_el is None or doc_el is None:
            continue

        doc_status = _text(st_el)
        nk = tp = num_doc = fecha = ""
        num_folios = fecha_concl = ""
        fecha_ingreso = ""
        for fe in doc_el:
            ft = _local(fe.tag)
            if ft == "NumKardex":
                nk = _text(fe)
            elif ft == "TipoInstrumento":
                tp = _text(fe)
            elif ft == "NumDocumento":
                num_doc = _text(fe)
            elif ft == "FechaInstrumento":
                fecha = _text(fe)
            elif ft == "NumFolios":
                num_folios = _text(fe)
            elif ft == "FechaConclusion":
                fecha_concl = _text(fe)
            elif ft == "FechaIngreso":
                fecha_ingreso = _text(fe)

        errors_merged = _collect_errors_deep(dn)

        documents.append(
            {
                "num_kardex": nk,
                "doc_status": doc_status,
                "tipo_instrumento": tp,
                "num_documento": num_doc,
                "fecha_instrumento": fecha,
                "fecha_ingreso": fecha_ingreso,
                "num_folios": num_folios,
                "fecha_conclusion": fecha_concl,
                "errors": errors_merged,
                "has_errors": bool(errors_merged),
            }
        )

    generador = None
    for el in root.iter():
        if _local(el.tag) != "GeneradorDatos":
            continue
        gd: Dict[str, str] = {}
        for ch in el:
            gd[_local(ch.tag)] = _text(ch)
        generador = gd or None
        break

    rs_upper = (return_status or "").strip().upper()
    summary: Dict[str, Any] = {
        "return_status": return_status,
        "return_message": return_message,
        "soap_level_ok": rs_upper == "OK",
        "generador_datos": generador,
        "documents": [
            {
                "num_kardex": d.get("num_kardex"),
                "status": d.get("doc_status"),
                "num_documento": d.get("num_documento"),
                "tipo_instrumento": d.get("tipo_instrumento"),
                "fecha_instrumento": d.get("fecha_instrumento"),
                "errors": d.get("errors") or [],
                "has_errors": d.get("has_errors", False),
            }
            for d in documents
        ],
        "totals": {
            "documentos": len(documents),
            "errores": sum(len(d.get("errors") or []) for d in documents),
        },
    }

    return {
        "return_status": return_status,
        "return_message": return_message,
        "documents": documents,
        "generador_datos": generador,
        "summary": summary,
    }


def save_response_logs_for_batch(
    *,
    batch_documents: List[Dict[str, Any]],
    batch_index: int,
    http_status: Optional[int],
    raw_xml: str,
    parsed: Dict[str, Any],
    user=None,
) -> List[int]:
    """
    Crea una fila SisgenSoapResponse por documento devuelto en el SOAP, o por cada
    kardex del batch si SISGEN no devolvió DocumentoNotarial (solo ACK o error SOAP).

    Returns IDs of rows created.
    """
    # Import local to evitar circular apps.loading
    from ..models import SisgenSoapResponse

    kmap = {
        str(d.get("kardex") or "").strip(): str(d.get("idkardex") or "").strip()
        for d in batch_documents
    }

    stored_raw, raw_meta = _maybe_truncate_raw(raw_xml or "")

    common = {
        "batch_index": batch_index,
        "http_status": http_status,
        "soap_return_status": (parsed.get("return_status") or "")[:64],
        "soap_return_message": parsed.get("return_message") or "",
        "raw_response_xml": stored_raw,
        "created_by": user if user is not None and getattr(user, "is_authenticated", False) else None,
    }

    docs = parsed.get("documents") or []
    created_ids: List[int] = []
    soap_failed = not soap_response_is_ok(parsed)

    if docs:
        for d in docs:
            nk = (d.get("num_kardex") or "").strip() or "?"
            pl: Dict[str, Any] = {
                "summary": parsed.get("summary"),
                "document": d,
                "parse_error": parsed.get("parse_error"),
            }
            if raw_meta:
                pl["raw_storage"] = raw_meta
            if soap_failed:
                pl.update(
                    user_facing_payload_for_saved_row(
                        parsed,
                        kardex=nk,
                        batch_index=batch_index,
                        http_status=http_status,
                    )
                )

            obj = SisgenSoapResponse.objects.create(
                kardex=nk[:32],
                idkardex=(kmap.get(nk, "") or "")[:32],
                document_status=(d.get("doc_status") or "")[:64],
                parsed_payload=pl,
                **common,
            )
            created_ids.append(obj.id)
        return created_ids

    rs = (parsed.get("return_status") or "").strip().upper()
    synth = "OK_ACK" if rs == "OK" else (rs[:64] if rs else "SIN_ECHO")

    for bd in batch_documents:
        k = str(bd.get("kardex") or "").strip()
        if not k:
            continue
        pl_ack: Dict[str, Any] = {
            "summary": parsed.get("summary"),
            "documents_echo": [],
            "parse_error": parsed.get("parse_error"),
        }
        if raw_meta:
            pl_ack["raw_storage"] = raw_meta
        if soap_failed:
            pl_ack.update(
                user_facing_payload_for_saved_row(
                    parsed,
                    kardex=k,
                    batch_index=batch_index,
                    http_status=http_status,
                )
            )

        obj = SisgenSoapResponse.objects.create(
            kardex=k[:32],
            idkardex=str(bd.get("idkardex") or "")[:32],
            document_status=synth,
            parsed_payload=pl_ack,
            **common,
        )
        created_ids.append(obj.id)
    return created_ids
