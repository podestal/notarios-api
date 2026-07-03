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
from .services.send_job_store import create_send_job
from .services.send_response_enrichment import (
    attach_last_submission_status,
    last_submission_from_soap_obj,
)
from .utils.exceptions import ValidationException
from .services.sisgen_soap_response import (
    SISGEN_IT_CONTACT_NOTE,
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
)
from .models import SisgenSendJob, SisgenSoapResponse, SisgenValidationCache
from notaria.models import Kardex
from django.urls import reverse
from rest_framework.decorators import api_view
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def _serialize_send_job(job: SisgenSendJob, *, request=None) -> Dict[str, Any]:
    status_url = None
    if request is not None:
        status_url = request.build_absolute_uri(
            reverse("sisgen_service:send_job_detail", kwargs={"job_id": job.pk})
        )
    return {
        "job_id": job.pk,
        "status": job.status,
        "celery_task_id": job.celery_task_id or None,
        "progress_processed": job.progress_processed,
        "progress_total": job.progress_total,
        "progress": job.progress_label,
        "payload": job.payload,
        "result": job.result,
        "error": job.error or None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "status_url": status_url,
        "documents": [
            {
                "kardex": doc.kardex,
                "idkardex": doc.idkardex,
                "status": doc.status,
                "batch_index": doc.batch_index,
                "attempt": doc.attempt or None,
                "message": doc.message or None,
                "submission_response_id": doc.submission_response_id,
            }
            for doc in job.documents.all()
        ],
    }


def _build_document_search_response(rows: list, page_status: dict) -> dict:
    enriched = attach_last_submission_status(rows)
    return {
        "error": 0,
        "data": [slim_search_document_row(row) for row in enriched],
        "pagination": slim_search_pagination(page_status),
    }


def _build_book_search_response(rows: list, page_status: dict) -> dict:
    return {
        "error": 0,
        "data": attach_last_submission_status(rows),
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
    Enqueue async SISGEN send. Returns 202 + job_id for polling.

    POST body:
    - documents: [{ kardex, idkardex }, ...]
    - Optional filter fields (fechaDesde, fechaHasta, ...) — validated before enqueue.
    """

    permission_classes = [IsAuthenticated, IsSuperuser]

    def post(self, request):
        try:
            raw_documents = request.data.get("documents", [])
            filter_payload = extract_search_filters(request.data)

            if not raw_documents:
                return Response(
                    {"error": 1, "message": "documents array is required"},
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
                    {"error": 1, "message": "No valid documents to send"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            job = create_send_job(
                user=request.user,
                documents=documents,
                filters=filter_payload,
            )

            from sisgen.tasks import run_send_job

            async_result = run_send_job.delay(job.pk)
            if async_result.id:
                job.celery_task_id = async_result.id
                job.save(update_fields=["celery_task_id", "updated_at"])

            payload = _serialize_send_job(job, request=request)
            payload["error"] = 0
            payload["message"] = "SISGEN send job queued"
            return Response(payload, status=status.HTTP_202_ACCEPTED)

        except Exception as e:
            logger.exception("Unexpected error enqueueing SISGEN send: %s", e)
            return Response(
                {"error": 1, "message": f"Internal server error: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@method_decorator(csrf_exempt, name='dispatch')
class SisgenSendJobDetailView(APIView):
    """GET /sisgen/send-jobs/<job_id>/ — poll async send job status and result."""

    permission_classes = [IsAuthenticated, IsSuperuser]

    def get(self, request, job_id: int):
        try:
            job = SisgenSendJob.objects.prefetch_related("documents").get(pk=job_id)
        except SisgenSendJob.DoesNotExist:
            return Response(
                {"error": 1, "message": "Send job not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if job.user_id != request.user.id and not request.user.is_superuser:
            return Response(
                {"error": 1, "message": "Forbidden"},
                status=status.HTTP_403_FORBIDDEN,
            )

        payload = _serialize_send_job(job, request=request)
        payload["error"] = 0
        return Response(payload)


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
                last_sub = last_submission_from_soap_obj(latest)
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
