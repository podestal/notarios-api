"""
SISGEN document send pipeline (batch / single / full job run).
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from sisgen.services.data_processor_service import DataProcessorService
from sisgen.services.send_batch_summary import (
    BATCH_STATUS_COMPLETED,
    BATCH_STATUS_DRY_RUN,
    BATCH_STATUS_ERROR_PROCESSING,
    BATCH_STATUS_ERROR_SEND,
    BATCH_STATUS_SKIPPED_NO_XML,
    BATCH_STATUS_SOAP_REJECTED,
    aggregate_batch_summary,
    build_batch_summary_entry,
)
from sisgen.services.send_response_enrichment import enrich_send_result
from sisgen.services.sisgen_soap_response import (
    SISGEN_IT_CONTACT_NOTE,
    build_soap_failure_entries,
    format_soap_return_message,
    parse_set_documentos_response,
    save_response_logs_for_batch,
    soap_response_is_ok,
)
from sisgen.services.soap_client_service import SoapClientService
from sisgen.services.xml_generator_service import SISGENXmlGenerator

logger = logging.getLogger(__name__)

SISGEN_DRY_RUN = False
DEFAULT_BATCH_SIZE = 10


def write_debug_xml(content: str, filename: str) -> None:
    debug_dir = Path(__file__).resolve().parent.parent / "sisgen_xml_debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    (debug_dir / filename).write_text(content or "", encoding="utf-8")


def build_user_friendly_errors(batch_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    friendly = []
    for row in batch_rows or []:
        status_txt = (row.get("status") or "").upper()
        if status_txt not in {"FALLIDO", "CON OBSERVACIONES"}:
            continue
        kardex = row.get("kardex") or ""
        contrato = row.get("contrato") or ""
        detalle = row.get("mensaje") or "SISGEN devolvio error sin detalle."
        readable_status = "FALLIDO" if status_txt == "FALLIDO" else "OBSERVADO"
        friendly.append(
            {
                "kardex": kardex,
                "estado": readable_status,
                "contrato": contrato,
                "mensaje_usuario": f"{kardex}: {detalle}",
                "mensaje_tecnico": detalle,
            }
        )
    return friendly


def new_combined_result(*, dry_run: bool = SISGEN_DRY_RUN) -> Dict[str, Any]:
    return {
        "error": 0,
        "messageDescription": "",
        "data": [],
        "errores": [],
        "errores_sisgen_usuario": [],
        "soap_errors": [],
        "observaciones": [],
        "personas": [],
        "guardados": 0,
        "fallidos": 0,
        "observados": 0,
        "processed_kardex": [],
        "dry_run": dry_run,
        "sisgen_requests": [],
        "submission_response_ids": [],
        "batches": [],
        "nota_contacto_it": SISGEN_IT_CONTACT_NOTE,
    }


def merge_batch_result(combined: Dict[str, Any], batch_result: Dict[str, Any]) -> None:
    merge = batch_result.get("merge") or {}
    if merge.get("error"):
        combined["error"] = 1
    if merge.get("messageDescription"):
        combined["messageDescription"] = merge["messageDescription"]

    for key in (
        "data",
        "errores",
        "errores_sisgen_usuario",
        "soap_errors",
        "observaciones",
        "personas",
        "processed_kardex",
        "sisgen_requests",
        "submission_response_ids",
    ):
        combined[key].extend(merge.get(key) or [])

    for counter in ("guardados", "fallidos", "observados"):
        combined[counter] += int(merge.get(counter) or 0)

    entry = batch_result.get("batch_summary")
    if entry:
        combined["batches"].append(entry)


def send_batch(
    *,
    batch: List[Dict[str, Any]],
    batch_index: int,
    user,
    data_processor: Optional[DataProcessorService] = None,
    xml_generator: Optional[SISGENXmlGenerator] = None,
    soap_client: Optional[SoapClientService] = None,
    dry_run: bool = SISGEN_DRY_RUN,
    write_debug: Callable[[str, str], None] = write_debug_xml,
) -> Dict[str, Any]:
    """
    Send one SOAP batch (1–10 documents). Returns batch_summary + merge payload.
    """
    data_processor = data_processor or DataProcessorService()
    xml_generator = xml_generator or SISGENXmlGenerator()
    soap_client = soap_client or SoapClientService()

    merge: Dict[str, Any] = {
        "error": 0,
        "messageDescription": "",
        "data": [],
        "errores": [],
        "errores_sisgen_usuario": [],
        "soap_errors": [],
        "observaciones": [],
        "personas": [],
        "guardados": 0,
        "fallidos": 0,
        "observados": 0,
        "processed_kardex": [],
        "sisgen_requests": [],
        "submission_response_ids": [],
    }
    batch_summary: Dict[str, Any] = {}
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    soap_attempted = False

    try:
        result = data_processor.process_documents_batch(batch)
        xml_content, xml_issues = xml_generator.generate_document_xml(
            result["documents"]
        )
        if xml_issues:
            merge["errores"].extend(xml_issues)

        if not xml_content:
            batch_summary = build_batch_summary_entry(
                batch_index=batch_index,
                batch=batch,
                status=BATCH_STATUS_SKIPPED_NO_XML,
                attempted=False,
                message=(
                    "No se generó XML para este lote; "
                    "ningún documento se envió a SISGEN."
                ),
                xml_issues=xml_issues,
            )
            return {"batch_summary": batch_summary, "merge": merge}

        write_debug(xml_content, f"request_batch_{batch_index}_{ts}.xml")

        if dry_run:
            soap_req = soap_client.build_request(xml_content)
            merge["messageDescription"] = (
                "Dry run: no se envió a SISGEN. Revise sisgen_requests."
            )
            merge["sisgen_requests"].append(
                {
                    "batch": batch_index,
                    "kardex_list": [doc["kardex"] for doc in batch],
                    "url": soap_req["url"],
                    "headers": soap_req["headers"],
                    "soap_body": soap_req["soap_body"],
                    "documentos_notariales_xml": xml_content,
                }
            )
            merge["processed_kardex"].extend([doc["kardex"] for doc in batch])
            merge["errores"].extend(result.get("errores", []))
            merge["observaciones"].extend(result.get("observaciones", []))
            merge["personas"].extend(result.get("personas", []))
            batch_summary = build_batch_summary_entry(
                batch_index=batch_index,
                batch=batch,
                status=BATCH_STATUS_DRY_RUN,
                attempted=False,
                message="Dry run: SOAP no enviado a SISGEN.",
            )
            return {"batch_summary": batch_summary, "merge": merge}

        response = soap_client.send_documents(xml_content)
        soap_attempted = True
        write_debug(response.text, f"response_batch_{batch_index}_{ts}.xml")

        parsed_soap = parse_set_documentos_response(response.text or "")
        if response.status_code >= 400 and soap_response_is_ok(parsed_soap):
            parsed_soap = {
                **parsed_soap,
                "return_status": f"HTTP_{response.status_code}",
                "return_message": (
                    parsed_soap.get("return_message")
                    or getattr(response, "reason", None)
                    or f"HTTP {response.status_code}"
                ),
                "parse_error": parsed_soap.get("parse_error") or "http_error",
                "summary": {
                    **(parsed_soap.get("summary") or {}),
                    "return_status": f"HTTP_{response.status_code}",
                    "soap_level_ok": False,
                },
            }

        saved_ids: List[int] = []
        try:
            saved_ids = save_response_logs_for_batch(
                batch_documents=batch,
                batch_index=batch_index,
                http_status=response.status_code,
                raw_xml=response.text or "",
                parsed=parsed_soap,
                user=user,
            )
            merge["submission_response_ids"].extend(saved_ids)
        except Exception as exc:
            logger.exception(
                "Persistencia SisgenSoapResponse fallida batch=%s: %s",
                batch_index,
                exc,
            )

        merge["processed_kardex"].extend([doc["kardex"] for doc in batch])
        merge["errores"].extend(result.get("errores", []))
        merge["observaciones"].extend(result.get("observaciones", []))
        merge["personas"].extend(result.get("personas", []))

        if not soap_response_is_ok(parsed_soap):
            soap_failures = build_soap_failure_entries(
                parsed=parsed_soap,
                batch_documents=batch,
                batch_index=batch_index,
                http_status=response.status_code,
            )
            merge["error"] = 1
            merge["soap_errors"].extend(soap_failures)
            merge["errores_sisgen_usuario"].extend(soap_failures)
            short = format_soap_return_message(parsed_soap.get("return_message") or "")
            merge["messageDescription"] = (
                f"SISGEN rechazó el envío (lote {batch_index}): {short} "
                f"{SISGEN_IT_CONTACT_NOTE}"
            )
            batch_summary = build_batch_summary_entry(
                batch_index=batch_index,
                batch=batch,
                status=BATCH_STATUS_SOAP_REJECTED,
                attempted=True,
                message=short,
                http_status=response.status_code,
                soap_return_status=parsed_soap.get("return_status") or "",
                submission_response_ids=saved_ids,
            )
            return {"batch_summary": batch_summary, "merge": merge}

        try:
            data_processor.update_document_statuses(response.text)
        except Exception as exc:
            logger.exception(
                "Error actualizando estados SISGEN batch=%s: %s",
                batch_index,
                exc,
            )
            batch_failures = build_soap_failure_entries(
                parsed={
                    "return_status": "ERROR_PROCESAMIENTO",
                    "return_message": str(exc),
                },
                batch_documents=batch,
                batch_index=batch_index,
                http_status=response.status_code,
            )
            merge["error"] = 1
            merge["soap_errors"].extend(batch_failures)
            merge["errores_sisgen_usuario"].extend(batch_failures)
            batch_summary = build_batch_summary_entry(
                batch_index=batch_index,
                batch=batch,
                status=BATCH_STATUS_ERROR_PROCESSING,
                attempted=True,
                message=str(exc),
                http_status=response.status_code,
                soap_return_status="ERROR_PROCESAMIENTO",
                submission_response_ids=saved_ids,
            )
            return {"batch_summary": batch_summary, "merge": merge}

        batch_status = data_processor.get_final_status()
        batch_guardados = int(batch_status.get("guardados", 0) or 0)
        batch_fallidos = int(batch_status.get("fallidos", 0) or 0)
        batch_observados = int(batch_status.get("observados", 0) or 0)

        merge["data"].extend(batch_status.get("data", []))
        merge["guardados"] = batch_guardados
        merge["fallidos"] = batch_fallidos
        merge["observados"] = batch_observados
        merge["errores_sisgen_usuario"].extend(
            build_user_friendly_errors(batch_status.get("data", []))
        )
        batch_summary = build_batch_summary_entry(
            batch_index=batch_index,
            batch=batch,
            status=BATCH_STATUS_COMPLETED,
            attempted=True,
            message="Lote enviado y procesado.",
            http_status=response.status_code,
            soap_return_status=parsed_soap.get("return_status") or "OK",
            guardados=batch_guardados,
            fallidos=batch_fallidos,
            observados=batch_observados,
            submission_response_ids=saved_ids,
        )
        return {"batch_summary": batch_summary, "merge": merge}

    except Exception as exc:
        logger.exception("Error sending SISGEN batch %s: %s", batch_index, exc)
        batch_failures = build_soap_failure_entries(
            parsed={
                "return_status": "ERROR_ENVIO",
                "return_message": str(exc),
            },
            batch_documents=batch,
            batch_index=batch_index,
        )
        merge["error"] = 1
        merge["soap_errors"].extend(batch_failures)
        merge["errores_sisgen_usuario"].extend(batch_failures)
        if not merge.get("messageDescription"):
            merge["messageDescription"] = (
                f"Error al enviar lote {batch_index}: {exc}. {SISGEN_IT_CONTACT_NOTE}"
            )
        batch_summary = build_batch_summary_entry(
            batch_index=batch_index,
            batch=batch,
            status=BATCH_STATUS_ERROR_SEND,
            attempted=soap_attempted,
            message=str(exc),
            soap_return_status="ERROR_ENVIO",
        )
        return {"batch_summary": batch_summary, "merge": merge}


def send_single(
    document: Dict[str, Any],
    *,
    batch_index: int,
    user,
    **kwargs: Any,
) -> Dict[str, Any]:
    return send_batch(batch=[document], batch_index=batch_index, user=user, **kwargs)


def send_documents(
    documents: List[Dict[str, Any]],
    *,
    user,
    dry_run: bool = SISGEN_DRY_RUN,
    batch_size: int = DEFAULT_BATCH_SIZE,
    on_batch_start: Optional[Callable[[List[Dict[str, Any]], int], None]] = None,
    on_batch_complete: Optional[Callable[[int, int], None]] = None,
    on_batch_result: Optional[
        Callable[[List[Dict[str, Any]], int, Dict[str, Any]], None]
    ] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    Send all documents in batches of ``batch_size``. Returns combined_result dict.
    Optional hooks used by the job orchestrator for DB progress / per-doc rows.
    """
    combined = new_combined_result(dry_run=dry_run)
    total = len(documents)
    expected_batches = (total + batch_size - 1) // batch_size if total else 0
    processed = 0

    for i in range(0, total, batch_size):
        batch = documents[i : i + batch_size]
        batch_num = (i // batch_size) + 1
        if on_batch_start:
            on_batch_start(batch, batch_num)

        batch_result = send_batch(
            batch=batch,
            batch_index=batch_num,
            user=user,
            dry_run=dry_run,
            **kwargs,
        )
        merge_batch_result(combined, batch_result)
        if on_batch_result:
            on_batch_result(batch, batch_num, batch_result)

        processed += len(batch)
        if on_batch_complete:
            on_batch_complete(processed, total)

    return finalize_combined_result(
        combined,
        documents,
        total=total,
        expected_batches=expected_batches,
    )


def finalize_combined_result(
    combined: Dict[str, Any],
    documents: List[Dict[str, Any]],
    *,
    total: int,
    expected_batches: int,
) -> Dict[str, Any]:
    combined["batch_summary"] = aggregate_batch_summary(
        combined["batches"],
        total_documents=total,
        expected_batches=expected_batches,
    )

    if len(documents) == 1:
        combined["kardex"] = documents[0]["kardex"]
        combined["idKardex"] = documents[0]["idkardex"]

    if combined["error"] and not combined["messageDescription"]:
        combined["messageDescription"] = (
            f"El envío a SISGEN falló. {SISGEN_IT_CONTACT_NOTE}"
        )

    enrich_send_result(combined, documents)
    return combined
