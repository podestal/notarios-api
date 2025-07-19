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
from .services.soap_client_service import SISGENSoapClient
from .services.data_processor_service import DataProcessorService
from .utils.constants import SISGEN_URLS
from .utils.exceptions import DocumentSearchException, SISGENServiceException

@method_decorator(csrf_exempt, name='dispatch')
class DocumentSearchView(APIView):
    def post(self, request):
        """Search for notarial documents"""
        try:
            # Get filters from request
            filters = request.data
            
            # Search documents
            service = DocumentSearchService()
            data, total, errors = service.search_documents(filters)
            
            if errors:
                return Response({
                    'error': 1,
                    'message': 'Search failed',
                    'errors': errors
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            return Response({
                'error': 0,
                'data': data,
                'total': total,
                'errores': [],
                'observaciones': [],
                'personas': []
            })
            
        except DocumentSearchException as e:
            return Response({
                'error': 1,
                'message': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                'error': 1,
                'message': 'Internal server error'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class SendToSISGENView(APIView):
    def post(self, request):
        """Send documents to SISGEN service"""
        try:
            # Get document IDs from request
            document_ids = request.data.get('document_ids', [])
            
            if not document_ids:
                return Response({
                    'error': 1,
                    'message': 'No documents specified'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Search for documents
            search_service = DocumentSearchService()
            documents, _, _ = search_service.search_documents({
                'document_ids': document_ids
            })
            
            if not documents:
                return Response({
                    'error': 1,
                    'message': 'No documents found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Process temp tables
            processor = DataProcessorService()
            processor.process_temp_tables([doc['kardex'] for doc in documents])
            
            # Generate XML
            xml_generator = SISGENXmlGenerator()
            xml_content = xml_generator.generate_document_xml(documents)
            
            # Send to SISGEN
            soap_client = SISGENSoapClient(SISGEN_URLS['DOCUMENTS'])
            result = soap_client.send_documents(xml_content)
            
            return Response({
                'error': 0 if result['success'] else 1,
                'status': result['status'],
                'message': result.get('message', ''),
                'xml_content': xml_content if request.data.get('include_xml') else None
            })
            
        except SISGENServiceException as e:
            return Response({
                'error': 1,
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            return Response({
                'error': 1,
                'message': 'Internal server error'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)