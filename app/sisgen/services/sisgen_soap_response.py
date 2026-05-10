"""
Parse SISGEN SOAP responses from setDocumentosNotariales y materializar filas para dashboard.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import defusedxml.ElementTree as ET

logger = logging.getLogger(__name__)


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
) -> int:
    """
    Crea una fila SisgenSoapResponse por documento devuelto en el SOAP, o por cada
    kardex del batch si SISGEN no devolvió DocumentoNotarial (solo ACK).

    Returns número de filas creadas.
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
    created = 0

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

            SisgenSoapResponse.objects.create(
                kardex=nk[:32],
                idkardex=(kmap.get(nk, "") or "")[:32],
                document_status=(d.get("doc_status") or "")[:64],
                parsed_payload=pl,
                **common,
            )
            created += 1
        return created

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

        SisgenSoapResponse.objects.create(
            kardex=k[:32],
            idkardex=str(bd.get("idkardex") or "")[:32],
            document_status=synth,
            parsed_payload=pl_ack,
            **common,
        )
        created += 1
    return created
