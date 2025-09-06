"""
This module contains the views for the sisgen service.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
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

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name='dispatch')
class DocumentSearchView(APIView):
    def post(self, request):
        """Search for notarial documents with pagination"""
        try:
            # Get filters and page from request
            filters = request.data
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
    - idkardex: ID of the kardex to send (required if all=0)
    - kardex: Kardex number to send (required if all=0)
    - all: 0 for single document, 1 for all documents in temp tables
    """
    def post(self, request):
        try:
            # Get parameters
            idkardex = request.data.get('idkardex')
            kardex = request.data.get('kardex')
            all_docs = request.data.get('all', 0)
            
            print('DEBUG: SendToSISGEN request data:', request.data)
            print('DEBUG: idkardex:', idkardex, 'kardex:', kardex, 'all:', all_docs)
            
            # Validate parameters
            if not all_docs and (not idkardex or not kardex):
                return Response({
                    'error': 1,
                    'message': 'idkardex and kardex are required when all=0'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Process data
            data_processor = DataProcessorService()
            result = data_processor.process_document(kardex, idkardex)
            
            # Generate XML
            xml_generator = SISGENXmlGenerator()
            xml_content = xml_generator.generate_document_xml(result['documents'])
            if not xml_content:
                print('DEBUG: Failed to generate XML - no content')
                return Response({
                    'error': 1,
                    'message': 'Failed to generate XML - missing required data'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Send to SISGEN
            soap_client = SoapClientService()
            response = soap_client.send_documents(xml_content)
            
            # Write response to file
            with open('response.xml', 'w') as f:
                f.write(response.text)
            
            # Process SISGEN response
            data_processor.update_document_statuses(response.text)
            
            # Get final status
            final_status = data_processor.get_final_status()
            
            return Response({
                'error': 0,
                'messageDescription': '',
                'data': final_status.get('data', []),
                'kardex': kardex,
                'idKardex': idkardex,
                'errores': result.get('errores', []),
                'observaciones': result.get('observaciones', []),
                'personas': result.get('personas', []),
                'guardados': final_status.get('guardados', 0),
                'fallidos': final_status.get('fallidos', 0),
                'observados': final_status.get('observados', 0)
            })
            
        except Exception as e:
            print('DEBUG: Unexpected error in SISGEN send:', str(e))
            return Response({
                'error': 1,
                'message': f'Internal server error: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
