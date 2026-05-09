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
from .services.xml_generator_service import SISGENXmlGenerator
from .services.soap_client_service import SoapClientService
from .services.data_processor_service import DataProcessorService
from .utils.exceptions import DocumentSearchException
from .services.book_search_service import BookSearchService
from .models import SisgenValidationCache
from rest_framework.decorators import api_view
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# When True, SendToSISGEN builds XML and returns the SOAP payload only — no HTTP call to SISGEN.
SISGEN_DRY_RUN = True


@method_decorator(csrf_exempt, name='dispatch')
class DocumentSearchView(APIView):
    permission_classes = [IsAuthenticated, IsSuperuser]

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
                        data, error_details, page_status = service.get_page(
                            search_info['search_id'], 
                            page=1
                        )
                        
                        # Update page_status to indicate session restart
                        page_status['session_restarted'] = True
                        page_status['message'] = 'Search session was restarted with previous filters'
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
                
                return Response({
                    'error': 0,
                    'data': data,
                    'pagination': page_status,
                    'errores': error_details.get('book_errors', []),
                    'observaciones': error_details.get('observations', [])
                })

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
                    data, error_details, page_status = service.get_page(
                        search_info['search_id'], 
                        page=1
                    )
                    
                    # Update page_status to indicate session restart
                    page_status['session_restarted'] = True
                    page_status['message'] = 'Search session was restarted with previous filters'
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
            
            return Response({
                'error': 0,
                'data': data,
                'pagination': page_status,
                'errores': error_details.get('kardex_errors', []),
                'observaciones': error_details.get('observations', []),
                'personas': error_details.get('person_errors', [])
            })
            
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
class SendToSISGENView(APIView):
    """
    Send documents to SISGEN service.

    POST Parameters:
    - documents: List of documents to process, each containing:
        {'kardex': str, 'idkardex': str}
        For single document, send array with one item
        For batch processing, send array with multiple items (processed in batches of 10)
    - all: 0 for documents array, 1 for all documents in temp tables
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
            # Get parameters
            documents = request.data.get('documents', [])
            all_docs = request.data.get('all', 0)
            
            print('DEBUG: SendToSISGEN request data:', request.data)
            
            # Initialize services
            data_processor = DataProcessorService()
            xml_generator = SISGENXmlGenerator()
            soap_client = SoapClientService()

            # Validate parameters
            if not all_docs and not documents:
                return Response({
                    'error': 1,
                    'message': 'documents array is required when all=0'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Process documents
            batch_size = 10
            combined_result = {
                'error': 0,
                'messageDescription': '',
                'data': [],
                'errores': [],
                'errores_sisgen_usuario': [],
                'observaciones': [],
                'personas': [],
                'guardados': 0,
                'fallidos': 0,
                'observados': 0,
                'processed_kardex': [],
                'dry_run': SISGEN_DRY_RUN,
                'sisgen_requests': [],
            }

            # Process in batches (even for single document)
            for i in range(0, len(documents), batch_size):
                batch = documents[i:i + batch_size]
                batch_num = (i // batch_size) + 1
                ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                try:
                    # Process batch
                    result = data_processor.process_documents_batch(batch)
                    
                    # Generate XML
                    xml_content = xml_generator.generate_document_xml(result['documents'])
                    if not xml_content:
                        print(f'DEBUG: Failed to generate XML for batch {batch_num}')
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
                        continue

                    response = soap_client.send_documents(xml_content)

                    self._write_debug_xml(response.text, f"response_batch_{batch_num}_{ts}.xml")

                    data_processor.update_document_statuses(response.text)

                    batch_status = data_processor.get_final_status()

                    combined_result['data'].extend(batch_status.get('data', []))
                    combined_result['guardados'] += batch_status.get('guardados', 0)
                    combined_result['fallidos'] += batch_status.get('fallidos', 0)
                    combined_result['observados'] += batch_status.get('observados', 0)
                    combined_result['processed_kardex'].extend([doc['kardex'] for doc in batch])

                    combined_result['errores'].extend(result.get('errores', []))
                    combined_result['errores_sisgen_usuario'].extend(
                        self._build_user_friendly_errors(batch_status.get('data', []))
                    )
                    combined_result['observaciones'].extend(result.get('observaciones', []))
                    combined_result['personas'].extend(result.get('personas', []))
                    
                except Exception as e:
                    print(f'DEBUG: Error processing batch {batch_num}:', str(e))
                    # Continue with next batch instead of failing completely
                    continue

            # For single document, include specific kardex info in response
            if len(documents) == 1:
                combined_result['kardex'] = documents[0]['kardex']
                combined_result['idKardex'] = documents[0]['idkardex']

            return Response(combined_result)
            
        except Exception as e:
            print('DEBUG: Unexpected error in SISGEN send:', str(e))
            return Response({
                'error': 1,
                'message': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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
