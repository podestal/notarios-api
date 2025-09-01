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
from .utils.constants import SISGEN_URLS
from .utils.exceptions import DocumentSearchException, SISGENServiceException


@method_decorator(csrf_exempt, name='dispatch')
class DocumentSearchView(APIView):
    def post(self, request):
        """Search for notarial documents"""
        try:
            # Get filters from request
            filters = request.data
            print('DEBUG: Filters', filters)
            
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
            print('DEBUG: Processing data for kardex:', kardex)
            result = data_processor.process_document(kardex, idkardex)
            print('DEBUG: Process result:', result)
            
            # Generate XML
            xml_generator = SISGENXmlGenerator()
            xml_content = xml_generator.generate_document_xml(result['documents'])
            if not xml_content:
                print('DEBUG: Failed to generate XML - no content')
                return Response({
                    'error': 1,
                    'message': 'Failed to generate XML - missing required data'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            print('DEBUG: Generated XML content')
            
            # Send to SISGEN
            soap_client = SoapClientService()
            response = soap_client.send_documents(xml_content)
            print('DEBUG: SISGEN response:', response)
            
            # Write response to file
            with open('response.xml', 'w') as f:
                f.write(response.text)
            
            # Handle SOAP client errors
            if not response.get('success'):
                return Response({
                    'error': 1,
                    'messageDescription': response.get('error', 'Error interno del XML.'),
                    'data': [],
                    'kardex': kardex,
                    'idKardex': idkardex,
                    'errores': result.get('errores', []),
                    'observaciones': result.get('observaciones', []),
                    'personas': result.get('personas', [])
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # Get final status counts and messages
            final_status = response
            
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