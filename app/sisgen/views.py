"""
This module contains the views for the sisgen service.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from .permissions import IsSuperuser
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from .services.document_search_service import DocumentSearchService
from .services.sisgen_errors_service import collect_kardex_sisgen_errors
from .services.send_preview_service import (
    build_send_preview,
    extract_search_filters,
    verify_documents_against_filters,
)
from .utils.exceptions import ValidationException
from .services.xml_generator_service import SISGENXmlGenerator
from .services.soap_client_service import SoapClientService
from .services.data_processor_service import DataProcessorService
from .services.send_batch_summary import (
    BATCH_STATUS_COMPLETED,
    BATCH_STATUS_DRY_RUN,
    BATCH_STATUS_ERROR_PROCESSING,
    BATCH_STATUS_ERROR_SEND,
    BATCH_STATUS_SKIPPED_NO_XML,
    BATCH_STATUS_SOAP_REJECTED,
    aggregate_batch_summary,
    build_batch_summary_entry,
)
from .services.sisgen_soap_response import (
    SISGEN_IT_CONTACT_NOTE,
    build_soap_failure_entries,
    extract_submission_errors,
    format_soap_return_message,
    parse_set_documentos_response,
    save_response_logs_for_batch,
    soap_response_is_ok,
)
from .utils.exceptions import DocumentSearchException
from .services.book_search_service import BookSearchService
from .services.search_response import (
    slim_search_document_row,
    slim_search_pagination,
)
from .services.sync_status import (
    build_sisgen_sync_status,
    merge_last_submission_for_row,
    status_ui_from_document_status,
)
from .models import SisgenSoapResponse, SisgenValidationCache
from notaria.models import Kardex
from rest_framework.decorators import api_view
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

# When True, SendToSISGEN builds XML and returns the SOAP payload only — no HTTP call to SISGEN.
SISGEN_DRY_RUN = False


def _last_submission_from_soap_obj(obj: SisgenSoapResponse) -> Dict[str, Any]:
    """Shape consumed by search UI as ``sisgen_last_submission``."""
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


def _attach_last_submission_status(rows: list) -> list:
    kardexes = [str(r.get("kardex") or "").strip() for r in rows if str(r.get("kardex") or "").strip()]
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
            latest_by_kardex[obj.kardex] = _last_submission_from_soap_obj(obj)

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


def _build_document_search_response(rows: list, page_status: dict) -> dict:
    enriched = _attach_last_submission_status(rows)
    return {
        "error": 0,
        "data": [slim_search_document_row(row) for row in enriched],
        "pagination": slim_search_pagination(page_status),
    }


def _build_book_search_response(rows: list, page_status: dict) -> dict:
    return {
        "error": 0,
        "data": _attach_last_submission_status(rows),
        "pagination": slim_search_pagination(page_status),
    }


@method_decorator(csrf_exempt, name='dispatch')
class DocumentSearchView(APIView):
    # permission_classes = [IsAuthenticated, IsSuperuser]

    def post(self, request):
        """Search for notarial documents with pagination"""
        try:
            # Get filters and page from request
            filters = request.data
            print('DEBUG: filters:', filters)
            page = int(filters.pop('page', 1))
            search_id = filters.pop('search_id', None)
            original_filters = filters.copy()  # Keep a copy of original filters

            # Route to BookSearchService if tipoInstrumento is 5
            if filters.get('tipoInstrumento') == 5:
                # If search_id is provided, try to get existing search data from session
                if search_id:
                    session_data = request.session.get('book_search_data')
                    if session_data and session_data.get('search_id') == search_id:
                        # Valid session exists
                        service = BookSearchService.from_session_data(session_data)
                        data, error_details, page_status = service.get_page(search_id, page)
                    else:
                        # Session expired - restart search with stored filters
                        stored_filters = request.session.get('last_book_filters', {})
                        filters_to_use = stored_filters or original_filters
                        
                        service = BookSearchService()
                        search_info = service.initialize_search(filters_to_use)
                        # Honor requested page (curl/API sin cookie no tiene sesión → antes forzaba page=1)
                        data, error_details, page_status = service.get_page(
                            search_info["search_id"],
                            page=page,
                        )

                        # Update page_status to indicate session restart
                        page_status["session_restarted"] = True
                        page_status["message"] = (
                            "Search session was restarted with previous filters; "
                            "use pagination.search_id from this response for following pages."
                        )
                else:
                    # New search
                    service = BookSearchService()
                    search_info = service.initialize_search(filters)
                    data, error_details, page_status = service.get_page(
                        search_info['search_id'], 
                        page=1
                    )
                
                # Store both search data and filters
                request.session['book_search_data'] = service.get_session_data()
                request.session['last_book_filters'] = original_filters
                
                # Update session expiry
                request.session.set_expiry(86400)  # 24 hours
                
                return Response(_build_book_search_response(data, page_status))

            print('DEBUG: filters:', filters)
            
            # If search_id is provided, try to get existing search data from session
            if search_id:
                session_data = request.session.get('search_data')
                if session_data and session_data.get('search_id') == search_id:
                    # Valid session exists
                    service = DocumentSearchService.from_session_data(session_data)
                    data, error_details, page_status = service.get_page(search_id, page)
                else:
                    # Session expired - restart search with stored filters
                    stored_filters = request.session.get('last_search_filters', {})
                    filters_to_use = stored_filters or original_filters
                    
                    service = DocumentSearchService()
                    search_info = service.initialize_search(filters_to_use)
                    # Same session note as libros: sin Cookie de sesión se recrea el search pero debe respetarse page.
                    data, error_details, page_status = service.get_page(
                        search_info["search_id"],
                        page=page,
                    )

                    page_status["session_restarted"] = True
                    page_status["message"] = (
                        "Search session was restarted with previous filters; "
                        "use pagination.search_id from this response for following pages."
                    )
            else:
                # New search
                service = DocumentSearchService()
                search_info = service.initialize_search(filters)
                data, error_details, page_status = service.get_page(
                    search_info['search_id'], 
                    page=1
                )
            
            # Store both search data and filters
            request.session['search_data'] = service.get_session_data()
            request.session['last_search_filters'] = original_filters
            
            # Update session expiry
            request.session.set_expiry(86400)  # 24 hours
            
            return Response(_build_document_search_response(data, page_status))
            
        except DocumentSearchException as e:
            # Handle specific exceptions gracefully
            return Response({
                'error': 1,
                'message': str(e),
                'suggestion': 'Please try your search again',
                'recoverable': True
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            # Log unexpected errors
            logger.error(f"Unexpected error in document search: {str(e)}")
            return Response({
                'error': 1,
                'message': 'An unexpected error occurred',
                'suggestion': 'Please try again in a few moments',
                'recoverable': True
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@method_decorator(csrf_exempt, name='dispatch')
class SendToSISGENPreviewView(APIView):
    """
    List all kardexes that match search filters (not paginated) before batch send.

    POST body: same filters as /sisgen/search/ (fechaDesde, fechaHasta, tipoInstrumento, estado, codigoActo).
    """

    permission_classes = [IsAuthenticated, IsSuperuser]

    def post(self, request):
        filters = extract_search_filters(request.data)
        if not filters.get("fechaDesde") or not filters.get("fechaHasta"):
            return Response(
                {
                    "error": 1,
                    "message": "fechaDesde and fechaHasta are required",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            return Response(build_send_preview(filters))
        except ValidationException as exc:
            return Response(
                {"error": 1, "message": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except DocumentSearchException as exc:
            return Response(
                {"error": 1, "message": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )


@method_decorator(csrf_exempt, name='dispatch')
class SendToSISGENView(APIView):
    """
    Send documents to SISGEN (SOAP), up to 10 kardexes per request batch.

    POST body:
    - documents: [{ kardex, idkardex }, ...] (from preview or manual selection)
    - Optional: fechaDesde, fechaHasta, tipoInstrumento, estado, codigoActo — if sent,
      each document must still match those filters.
    """

    permission_classes = [IsAuthenticated, IsSuperuser]

    @staticmethod
    def _write_debug_xml(content: str, filename: str) -> None:
        """
        Persist SISGEN debug XML files in app/sisgen_xml_debug.
        We keep timestamped filenames to avoid overwriting previous sends.
        """
        debug_dir = Path(__file__).resolve().parent / "sisgen_xml_debug"
        debug_dir.mkdir(parents=True, exist_ok=True)
        (debug_dir / filename).write_text(content or "", encoding="utf-8")

    @staticmethod
    def _build_user_friendly_errors(batch_rows):
        """
        Convert SISGEN technical rows into user-friendly messages by kardex.
        """
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

    def post(self, request):
        try:
            raw_documents = request.data.get("documents", [])
            filter_payload = extract_search_filters(request.data)

            print("DEBUG: SendToSISGEN request data:", request.data)

            data_processor = DataProcessorService()
            xml_generator = SISGENXmlGenerator()
            soap_client = SoapClientService()

            if not raw_documents:
                return Response(
                    {
                        "error": 1,
                        "message": "documents array is required",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            documents = raw_documents
            if filter_payload:
                try:
                    documents, invalid = verify_documents_against_filters(
                        filter_payload, raw_documents
                    )
                except ValidationException as exc:
                    return Response(
                        {"error": 1, "message": str(exc)},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                except DocumentSearchException as exc:
                    return Response(
                        {"error": 1, "message": str(exc)},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if invalid:
                    return Response(
                        {
                            "error": 1,
                            "message": "Some kardexes do not match the provided filters",
                            "invalid_kardex": invalid,
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            if not documents:
                return Response(
                    {
                        "error": 1,
                        "message": "No valid documents to send",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Process documents
            batch_size = 10
            expected_batches = (len(documents) + batch_size - 1) // batch_size
            batches_out: list = []
            combined_result = {
                'error': 0,
                'messageDescription': '',
                'data': [],
                'errores': [],
                'errores_sisgen_usuario': [],
                'soap_errors': [],
                'observaciones': [],
                'personas': [],
                'guardados': 0,
                'fallidos': 0,
                'observados': 0,
                'processed_kardex': [],
                'dry_run': SISGEN_DRY_RUN,
                'sisgen_requests': [],
                'submission_response_ids': [],
                'batches': batches_out,
                'nota_contacto_it': SISGEN_IT_CONTACT_NOTE,
            }

            # Process in batches (even for single document)
            for i in range(0, len(documents), batch_size):
                batch = documents[i:i + batch_size]
                batch_num = (i // batch_size) + 1
                ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                soap_attempted = False
                try:
                    # Process batch
                    result = data_processor.process_documents_batch(batch)
                    
                    # Generate XML (None si todos omitidos → no enviar; SISGEN respondería OK sin GUARDADO)
                    xml_content, xml_issues = xml_generator.generate_document_xml(
                        result['documents']
                    )
                    if xml_issues:
                        combined_result['errores'].extend(xml_issues)
                    if not xml_content:
                        print(
                            f'DEBUG: Failed to generate XML for batch {batch_num}: '
                            f'{xml_issues}'
                        )
                        batches_out.append(
                            build_batch_summary_entry(
                                batch_index=batch_num,
                                batch=batch,
                                status=BATCH_STATUS_SKIPPED_NO_XML,
                                attempted=False,
                                message=(
                                    "No se generó XML para este lote; "
                                    "ningún documento se envió a SISGEN."
                                ),
                                xml_issues=xml_issues,
                            )
                        )
                        continue

                    # Always persist outgoing XML for troubleshooting
                    self._write_debug_xml(xml_content, f"request_batch_{batch_num}_{ts}.xml")

                    if SISGEN_DRY_RUN:
                        soap_req = soap_client.build_request(xml_content)
                        combined_result['messageDescription'] = (
                            'Dry run: no se envió a SISGEN. Revise sisgen_requests.'
                        )
                        combined_result['sisgen_requests'].append(
                            {
                                'batch': batch_num,
                                'kardex_list': [doc['kardex'] for doc in batch],
                                'url': soap_req['url'],
                                'headers': soap_req['headers'],
                                'soap_body': soap_req['soap_body'],
                                'documentos_notariales_xml': xml_content,
                            }
                        )
                        combined_result['processed_kardex'].extend(
                            [doc['kardex'] for doc in batch]
                        )
                        combined_result['errores'].extend(result.get('errores', []))
                        combined_result['observaciones'].extend(
                            result.get('observaciones', [])
                        )
                        combined_result['personas'].extend(result.get('personas', []))
                        batches_out.append(
                            build_batch_summary_entry(
                                batch_index=batch_num,
                                batch=batch,
                                status=BATCH_STATUS_DRY_RUN,
                                attempted=False,
                                message="Dry run: SOAP no enviado a SISGEN.",
                            )
                        )
                        continue

                    response = soap_client.send_documents(xml_content)
                    soap_attempted = True

                    self._write_debug_xml(response.text, f"response_batch_{batch_num}_{ts}.xml")

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

                    saved_ids: list = []
                    try:
                        saved_ids = save_response_logs_for_batch(
                            batch_documents=batch,
                            batch_index=batch_num,
                            http_status=response.status_code,
                            raw_xml=response.text or "",
                            parsed=parsed_soap,
                            user=request.user,
                        )
                        combined_result['submission_response_ids'].extend(saved_ids)
                    except Exception as exc:
                        logger.exception(
                            "Persistencia SisgenSoapResponse fallida batch=%s: %s",
                            batch_num,
                            exc,
                        )

                    combined_result['processed_kardex'].extend(
                        [doc['kardex'] for doc in batch]
                    )
                    combined_result['errores'].extend(result.get('errores', []))
                    combined_result['observaciones'].extend(result.get('observaciones', []))
                    combined_result['personas'].extend(result.get('personas', []))

                    if not soap_response_is_ok(parsed_soap):
                        soap_failures = build_soap_failure_entries(
                            parsed=parsed_soap,
                            batch_documents=batch,
                            batch_index=batch_num,
                            http_status=response.status_code,
                        )
                        combined_result['error'] = 1
                        combined_result['soap_errors'].extend(soap_failures)
                        combined_result['errores_sisgen_usuario'].extend(soap_failures)
                        short = format_soap_return_message(
                            parsed_soap.get("return_message") or ""
                        )
                        combined_result['messageDescription'] = (
                            f"SISGEN rechazó el envío (lote {batch_num}): {short} "
                            f"{SISGEN_IT_CONTACT_NOTE}"
                        )
                        batches_out.append(
                            build_batch_summary_entry(
                                batch_index=batch_num,
                                batch=batch,
                                status=BATCH_STATUS_SOAP_REJECTED,
                                attempted=True,
                                message=short,
                                http_status=response.status_code,
                                soap_return_status=(
                                    parsed_soap.get("return_status") or ""
                                ),
                                submission_response_ids=saved_ids,
                            )
                        )
                        continue

                    try:
                        data_processor.update_document_statuses(response.text)
                    except Exception as exc:
                        logger.exception(
                            "Error actualizando estados SISGEN batch=%s: %s",
                            batch_num,
                            exc,
                        )
                        batch_failures = build_soap_failure_entries(
                            parsed={
                                "return_status": "ERROR_PROCESAMIENTO",
                                "return_message": str(exc),
                            },
                            batch_documents=batch,
                            batch_index=batch_num,
                            http_status=response.status_code,
                        )
                        combined_result['error'] = 1
                        combined_result['soap_errors'].extend(batch_failures)
                        combined_result['errores_sisgen_usuario'].extend(batch_failures)
                        batches_out.append(
                            build_batch_summary_entry(
                                batch_index=batch_num,
                                batch=batch,
                                status=BATCH_STATUS_ERROR_PROCESSING,
                                attempted=True,
                                message=str(exc),
                                http_status=response.status_code,
                                soap_return_status="ERROR_PROCESAMIENTO",
                                submission_response_ids=saved_ids,
                            )
                        )
                        continue

                    batch_status = data_processor.get_final_status()
                    batch_guardados = int(batch_status.get('guardados', 0) or 0)
                    batch_fallidos = int(batch_status.get('fallidos', 0) or 0)
                    batch_observados = int(batch_status.get('observados', 0) or 0)

                    combined_result['data'].extend(batch_status.get('data', []))
                    combined_result['guardados'] += batch_guardados
                    combined_result['fallidos'] += batch_fallidos
                    combined_result['observados'] += batch_observados

                    combined_result['errores_sisgen_usuario'].extend(
                        self._build_user_friendly_errors(batch_status.get('data', []))
                    )
                    batches_out.append(
                        build_batch_summary_entry(
                            batch_index=batch_num,
                            batch=batch,
                            status=BATCH_STATUS_COMPLETED,
                            attempted=True,
                            message="Lote enviado y procesado.",
                            http_status=response.status_code,
                            soap_return_status=(
                                parsed_soap.get("return_status") or "OK"
                            ),
                            guardados=batch_guardados,
                            fallidos=batch_fallidos,
                            observados=batch_observados,
                            submission_response_ids=saved_ids,
                        )
                    )
                    
                except Exception as e:
                    print(f'DEBUG: Error processing batch {batch_num}:', str(e))
                    batch_failures = build_soap_failure_entries(
                        parsed={
                            "return_status": "ERROR_ENVIO",
                            "return_message": str(e),
                        },
                        batch_documents=batch,
                        batch_index=batch_num,
                    )
                    combined_result['error'] = 1
                    combined_result['soap_errors'].extend(batch_failures)
                    combined_result['errores_sisgen_usuario'].extend(batch_failures)
                    if not combined_result['messageDescription']:
                        combined_result['messageDescription'] = (
                            f"Error al enviar lote {batch_num}: {e}. {SISGEN_IT_CONTACT_NOTE}"
                        )
                    batches_out.append(
                        build_batch_summary_entry(
                            batch_index=batch_num,
                            batch=batch,
                            status=BATCH_STATUS_ERROR_SEND,
                            attempted=soap_attempted,
                            message=str(e),
                            soap_return_status="ERROR_ENVIO",
                        )
                    )
                    continue

            combined_result["batch_summary"] = aggregate_batch_summary(
                batches_out,
                total_documents=len(documents),
                expected_batches=expected_batches,
            )

            # For single document, include specific kardex info in response
            if len(documents) == 1:
                combined_result['kardex'] = documents[0]['kardex']
                combined_result['idKardex'] = documents[0]['idkardex']

            if combined_result['error'] and not combined_result['messageDescription']:
                combined_result['messageDescription'] = (
                    f"El envío a SISGEN falló. {SISGEN_IT_CONTACT_NOTE}"
                )

            if combined_result.get("processed_kardex"):
                submission_rows = [
                    {"kardex": k} for k in combined_result["processed_kardex"]
                ]
                enriched = _attach_last_submission_status(submission_rows)
                by_kardex = {
                    row["kardex"]: row.get("sisgen_last_submission") or {"exists": False}
                    for row in enriched
                    if row.get("kardex")
                }
                combined_result["sisgen_last_submission_by_kardex"] = by_kardex
                if len(documents) == 1:
                    k0 = documents[0]["kardex"]
                    combined_result["sisgen_last_submission"] = by_kardex.get(
                        k0, {"exists": False}
                    )

            return Response(combined_result)
            
        except Exception as e:
            print('DEBUG: Unexpected error in SISGEN send:', str(e))
            return Response({
                'error': 1,
                'message': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def _serialize_sisgen_soap_response(
    obj: SisgenSoapResponse, *, include_raw: bool
) -> dict:
    payload = obj.parsed_payload or {}
    user_facing = payload.get("user_facing") or {}
    row = {
        "id": obj.id,
        "created_at": obj.created_at.isoformat(),
        "kardex": obj.kardex,
        "idkardex": obj.idkardex,
        "batch_index": obj.batch_index,
        "http_status": obj.http_status,
        "soap_return_status": obj.soap_return_status,
        "soap_return_message": obj.soap_return_message,
        "document_status": obj.document_status,
        "parsed_payload": payload,
        "soap_failure": payload.get("soap_failure", False),
        "mensaje_usuario": user_facing.get("mensaje_usuario"),
        "mensaje_tecnico": user_facing.get("mensaje_tecnico") or obj.soap_return_message,
        "nota_contacto_it": payload.get("nota_contacto_it")
        or user_facing.get("nota_contacto_it")
        or SISGEN_IT_CONTACT_NOTE,
    }
    if include_raw:
        row["raw_response_xml"] = obj.raw_response_xml or ""
    else:
        row["raw_response_xml_bytes"] = len((obj.raw_response_xml or "").encode("utf-8"))
    return row


@method_decorator(csrf_exempt, name='dispatch')
class SisgenSoapResponseListView(APIView):
    """
    Histórico de respuestas SISGEN guardadas tras POST real (no dry-run).

    **Varias filas por mismo kardex:** cada envío exitoso puede crear una o más filas
    (reenvíos, eco por documento, etc.).

    **Paginación**
    - Sin ``limit``: se devuelven todas las filas que coincidan desde ``offset``, hasta
      ``max_auto_fetch`` (50_000) por petición; si hay más, ``has_more`` es True y se usa
      el siguiente ``offset``.
    - Con ``limit``: tamaño de página explícito (1 … 100_000).

    GET ``/sisgen/submission-responses/?kardex=…``
    GET ``/sisgen/submission-responses/kardex/<kardex>/``

    Query: ``offset``, ``limit`` (opcional), ``include_raw=1``.
    """

    # permission_classes = [IsAuthenticated, IsSuperuser]

    _MAX_AUTO_FETCH = 50000
    _MAX_LIMIT_PARAM = 100000

    def get(self, request, kardex=None):
        k_filter = (
            (kardex if kardex is not None else "")
            or (request.query_params.get("kardex") or "")
        ).strip()
        try:
            offset = int(request.query_params.get("offset", 0))
        except ValueError:
            offset = 0
        offset = max(0, offset)

        limit_raw = request.query_params.get("limit")
        limit_explicit = limit_raw is not None and str(limit_raw).strip() != ""

        include_raw = request.query_params.get("include_raw", "").strip().lower() in (
            "1",
            "true",
            "yes",
        )

        qs = SisgenSoapResponse.objects.all().order_by("-created_at")
        if k_filter:
            qs = qs.filter(kardex=k_filter)

        total_count = qs.count()

        if limit_explicit:
            try:
                page_size = int(limit_raw)
            except ValueError:
                page_size = self._MAX_AUTO_FETCH
            page_size = max(1, min(page_size, self._MAX_LIMIT_PARAM))
        else:
            remaining = max(0, total_count - offset)
            page_size = min(self._MAX_AUTO_FETCH, remaining)

        rows = list(qs[offset : offset + page_size])
        has_more = offset + len(rows) < total_count

        payload = {
            "error": 0,
            "total_count": total_count,
            "offset": offset,
            "returned_count": len(rows),
            "has_more": has_more,
            "max_auto_fetch_per_request": self._MAX_AUTO_FETCH,
            "include_raw": include_raw,
            "data": [
                _serialize_sisgen_soap_response(r, include_raw=include_raw) for r in rows
            ],
        }
        if k_filter:
            payload["kardex"] = k_filter
            krow = Kardex.objects.filter(kardex=k_filter).values("estado_sisgen").first()
            estado_code = krow["estado_sisgen"] if krow else 0
            latest = SisgenSoapResponse.objects.filter(kardex=k_filter).order_by(
                "-created_at"
            ).first()
            if latest:
                last_sub = _last_submission_from_soap_obj(latest)
            else:
                last_sub = {"exists": False}
            sync = build_sisgen_sync_status(estado_code, last_sub)
            payload["sisgen_status"] = sync
            payload["sisgen_last_submission"] = merge_last_submission_for_row(
                last_sub, sync
            )
        return Response(payload)


@method_decorator(csrf_exempt, name='dispatch')
class SisgenErrorsByKardexView(APIView):
    """
    Pre-send SISGEN validation messages for one kardex.

    GET /sisgen/errors/kardex/<kardex>/
    """

    # permission_classes = [IsAuthenticated]

    def get(self, request, kardex: str):
        kardex_code = (kardex or "").strip()
        if not kardex_code:
            return Response(
                {"error": 1, "message": "kardex is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = collect_kardex_sisgen_errors(kardex_code)
        if result is None:
            return Response(
                {"error": 1, "message": f"Kardex not found: {kardex_code}"},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(result)


@method_decorator(csrf_exempt, name='dispatch')
class SisgenValidationRecalculateView(APIView):
    """
    Recalculate and upsert search-validation errors for one kardex.
    """

    # permission_classes = [IsAuthenticated, IsSuperuser]

    @staticmethod
    def _recalculate_and_upsert(kardex: str, idkardex_filter: str, user):
        service = DocumentSearchService()
        docs = service._execute_batch_query([kardex])

        if idkardex_filter:
            docs = [d for d in docs if str(d.get("idkardex", "")) == idkardex_filter]

        if not docs:
            return None

        service.kardex_errors = {}
        service.kardex_observations = {}
        service.person_errors = {}
        service.pdt_errors = {}

        try:
            service._validate_document_data(docs)
            service._validate_person_data(docs)
            service._validate_pdt_data(docs)
        except Exception as exc:
            logger.warning("Validation warning for kardex %s: %s", kardex, exc)

        processed = service._process_documents(docs, filters={})
        processed_doc = processed[0]

        payload = {
            "kardex": processed_doc.get("kardex", kardex),
            "idkardex": str(processed_doc.get("idkardex", "")),
            "errores": processed_doc.get("errores", []),
            "observaciones": processed_doc.get("observaciones", []),
            "personas": processed_doc.get("personas", []),
            "uif_validation": processed_doc.get("uif_validation", {}),
            "pdt_validation": processed_doc.get("pdt_validation", {}),
        }

        cache, _ = SisgenValidationCache.objects.update_or_create(
            kardex=payload["kardex"],
            defaults={
                "idkardex": payload["idkardex"],
                "payload": payload,
                "updated_by": user if user.is_authenticated else None,
            },
        )
        return cache

    def post(self, request):
        kardex = str(request.data.get("kardex", "")).strip()
        idkardex_filter = str(request.data.get("idkardex", "")).strip()

        if not kardex:
            return Response(
                {"error": 1, "message": "kardex is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cache = self._recalculate_and_upsert(kardex, idkardex_filter, request.user)
        if cache is None:
            return Response(
                {"error": 1, "message": "Document not found for provided kardex/idkardex"},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {
                "error": 0,
                "message": "Validation recalculated",
                "kardex": cache.kardex,
                "idkardex": cache.idkardex,
                "updated_at": cache.updated_at,
                "payload": cache.payload,
            }
        )
