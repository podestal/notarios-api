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
from rest_framework.decorators import api_view
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


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
                'observaciones': [],
                'personas': [],
                'guardados': 0,
                'fallidos': 0,
                'observados': 0,
                'processed_kardex': []
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

                    # Send to SISGEN
                    response = soap_client.send_documents(xml_content)
                    
                    # Always persist SISGEN response XML for troubleshooting
                    self._write_debug_xml(response.text, f"response_batch_{batch_num}_{ts}.xml")
                    
                    # Process SISGEN response
                    data_processor.update_document_statuses(response.text)
                    
                    # Get status for this batch
                    batch_status = data_processor.get_final_status()
                    
                    # Combine results
                    combined_result['data'].extend(batch_status.get('data', []))
                    combined_result['guardados'] += batch_status.get('guardados', 0)
                    combined_result['fallidos'] += batch_status.get('fallidos', 0)
                    combined_result['observados'] += batch_status.get('observados', 0)
                    combined_result['processed_kardex'].extend([doc['kardex'] for doc in batch])
                    
                    # Add any errors/observations from the batch
                    combined_result['errores'].extend(result.get('errores', []))
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
