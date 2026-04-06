from django.shortcuts import render
from rest_framework.viewsets import ModelViewSet
from rest_framework.decorators import action, api_view
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from . import models, serializers
from notaria.models import (
    TplTemplate,
    Detallevehicular,
    Patrimonial,
    Contratantes,
    Actocondicion,
    Cliente2,
    Nacionalidades,
    Kardex,
    Usuarios,
    Contratantesxacto,
    Ubigeo,
    IngresoCartas,
    CertDomiciliario,
    Libros,
)
from notaria.constants import MONEDAS, OPORTUNIDADES_PAGO, FORMAS_PAGO
from notaria import pagination
from django.http import HttpResponse, JsonResponse
import boto3
from botocore.client import Config
from django.conf import settings
import os
from docx import Document
import io
from .constants import ROLE_LABELS, TIPO_DOCUMENTO, CIVIL_STATUS
import re
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any
from botocore.config import Config
from datetime import datetime
from docxtpl import DocxTemplate
from docxcompose.properties import CustomProperties
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from docx.shared import RGBColor, Pt
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django.views.decorators.http import require_GET
from django.utils.decorators import method_decorator
import secrets
import hashlib
from functools import wraps

import re
from django.urls import reverse
from .utils import NumberToLetterConverter
from .services import (
    VehicleTransferDocumentService,
    NonContentiousDocumentService,
    TestamentoDocumentService,
    GarantiasMobiliariasDocumentService,
)
from .protocolares.EscrituraPublicaDocumentService import EscrituraDocumentService
from .protocolares.NoContenciososService import NoContenciososDocumentService
from .protocolares.GarantiasService import GarantiasDocumentService
from .protocolares.TestamentosService import TestamentosDocumentService
from .protocolares.TransferenciasVehicularesService import TransferenciasVehicularesDocumentService

# from .services import VehicleTransferDocumentService, NonContentiousDocumentService, TestamentoDocumentService, GarantiasMobiliariasDocumentService, EscrituraPublicaDocumentService
from .extraprotocolares.permiso_viajes import (
    PermisoViajeInteriorDocumentService,
    PermisoViajeExteriorDocumentService,
)
from .extraprotocolares.poderes import (
    PoderFueraDeRegistroDocumentService,
    PoderPensionDocumentService,
    PoderEssaludDocumentService,
)
from notaria.models import IngresoPoderes
from .extraprotocolares.cartas_notariales import CartasNotarialesDocumentService
from .extraprotocolares.cert_domiciliarios import CertDomiciliariosDocumentService
from .extraprotocolares.libros import LibrosDocumentService
from notaria.models import Libros

from ducumentation.protocolares.EscrituraPublicaDocumentService import EscrituraDocumentService


# Token-based authentication for save_doc view
def generate_secure_token():
    """Generate a secure token for API access"""
    # Generate a random 32-byte token
    token = secrets.token_urlsafe(32)
    # Hash it for storage (we'll store the hash, not the plain token)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    return token, token_hash


def validate_api_token(request):
    """Validate the API token from request headers"""
    print("DEBUG: ===== TOKEN VALIDATION START =====")

    # Get token from Authorization header
    auth_header = request.META.get("HTTP_AUTHORIZATION", "")
    print(f"DEBUG: Raw auth header: '{auth_header}'")

    if not auth_header.startswith("Token "):
        print(f"DEBUG: Header doesn't start with 'Token '")
        return False, "Missing or invalid Authorization header format"

    token = auth_header[6:]  # Remove 'Token ' prefix
    print(f"DEBUG: Extracted token: '{token}'")

    # Get valid tokens from environment variables
    env_tokens = os.environ.get("API_TOKENS", "")
    print(f"DEBUG: Environment API_TOKENS: '{env_tokens}'")
    print(f"DEBUG: Environment API_TOKENS type: {type(env_tokens)}")
    print(f"DEBUG: All environment variables: {dict(os.environ)}")

    if env_tokens:
        valid_tokens = [t.strip() for t in env_tokens.split(",") if t.strip()]
        print(f"DEBUG: Parsed valid_tokens: {valid_tokens}")
    else:
        print(f"DEBUG: No environment tokens, using fallback")
        # Fallback to hardcoded tokens (for development only)
        valid_tokens = [
            "your-secure-token-here-12345",
            "office-addin-token-67890",
        ]
        print(f"DEBUG: Fallback valid_tokens: {valid_tokens}")

    print(f"DEBUG: Final valid_tokens list: {valid_tokens}")
    print(f"DEBUG: Token in valid_tokens: {token in valid_tokens}")
    print(f"DEBUG: Token length: {len(token)}")
    print(f"DEBUG: Valid token lengths: {[len(t) for t in valid_tokens]}")

    if token in valid_tokens:
        print(f"DEBUG: TOKEN VALID - Authentication successful!")
        return True, "Token valid"
    else:
        print(f"DEBUG: TOKEN INVALID - Authentication failed!")
        return False, "Invalid token"


def require_api_token(view_func):
    """Decorator to require valid API token"""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        is_valid, message = validate_api_token(request)
        if not is_valid:
            return JsonResponse(
                {"status": "error", "message": f"Authentication failed: {message}"}, status=401
            )
        return view_func(request, *args, **kwargs)

    return wrapper


def require_admin_user(view_func):
    """Decorator to require admin user - works with JWT authentication"""

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        print(
            f"DEBUG: require_admin_user - User: {request.user}, Authenticated: {request.user.is_authenticated}, Staff: {getattr(request.user, 'is_staff', False)}"
        )
        print(f"DEBUG: require_admin_user - Headers: {dict(request.META)}")

        # Check if user is authenticated via JWT (like your other endpoints)
        if request.user.is_authenticated and request.user.is_staff:
            print(
                f"DEBUG: require_admin_user - JWT auth successful for user: {request.user.username}"
            )
            return view_func(request, *args, **kwargs)

        # If not JWT authenticated, check for admin token as fallback
        admin_token = request.META.get("HTTP_X_ADMIN_TOKEN", "")
        if admin_token:
            print(f"DEBUG: require_admin_user - Admin token provided: {admin_token[:10]}...")
            # Check if admin token is valid
            valid_admin_tokens = os.environ.get("ADMIN_TOKENS", "admin-secret-token-12345").split(
                ","
            )
            if admin_token in valid_admin_tokens:
                print(f"DEBUG: require_admin_user - Admin token valid")
                return view_func(request, *args, **kwargs)
            else:
                print(f"DEBUG: require_admin_user - Admin token invalid")

        # If neither JWT nor admin token is valid
        print(f"DEBUG: require_admin_user - No valid authentication found")
        return JsonResponse(
            {
                "status": "error",
                "message": "Admin access required. Use JWT authentication or provide X-Admin-Token header.",
                "debug_info": {
                    "user_authenticated": request.user.is_authenticated,
                    "user_is_staff": getattr(request.user, "is_staff", False),
                    "admin_token_provided": bool(admin_token),
                    "jwt_token_provided": bool(
                        request.META.get("HTTP_AUTHORIZATION", "").startswith("Bearer ")
                    ),
                    "session_id": (
                        request.session.session_key if hasattr(request, "session") else None
                    ),
                },
            },
            status=403,
        )

    return wrapper


@api_view(["GET"])
def generate_document_by_tipkar(request):
    """
    Generate document based on tipkar (tipo kardex) from the kardex record
    """
    print("GENERATE DOCUMENT BY TIPKAR VIEW CALLED")
    # Get parameters from GET request
    template_id = request.GET.get("template_id")
    kardex = request.GET.get("kardex")
    action = "generate"
    mode = request.GET.get("mode")

    if not all([template_id, kardex]):
        return Response(
            {"success": False, "message": "Missing required parameters: template_id, kardex"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        template_id = int(template_id)
    except ValueError:
        return Response(
            {"success": False, "message": "Invalid template_id format"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        # Get the kardex record to determine the tipkar
        kardex_obj = Kardex.objects.filter(kardex=kardex).first()

        if not kardex_obj:
            return Response(
                {"success": False, "message": f"Kardex {kardex} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        tipkar = kardex_obj.idtipkar

        # Route to appropriate service based on tipkar
        if tipkar == 3:  # TRANSFERENCIAS VEHICULARES
            print(f"DEBUG: Using VehicleTransferDocumentService for tipkar {tipkar}")
            service = VehicleTransferDocumentService()
            response = service.generate_vehicle_transfer_document(template_id, kardex, action, mode)
            return response
        elif tipkar == 2:  # ASUNTOS NO CONTENCIOSOS
            print(f"DEBUG: Using NonContentiousDocumentService for tipkar {tipkar}")
            # For non-contentious, we need idtipoacto from the request or from kardex
            idtipoacto = request.GET.get("idtipoacto")
            if not idtipoacto:
                # Try to get from kardex codactos
                if kardex_obj.codactos:
                    idtipoacto = kardex_obj.codactos[:3]  # Take first 3 characters
                else:
                    return Response(
                        {
                            "success": False,
                            "message": "idtipoacto is required for non-contentious documents",
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            service = NonContentiousDocumentService()
            response = service.generate_non_contentious_document(
                template_id, kardex, idtipoacto, action, mode
            )
            return response
        else:
            return Response(
                {
                    "success": False,
                    "message": f"Document generation not implemented for tipkar {tipkar}",
                },
                status=status.HTTP_501_NOT_IMPLEMENTED,
            )

    except Exception as e:
        print(f"Error generating document: {e}")
        return Response(
            {"success": False, "message": "Internal server error occurred"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
def update_document_by_tipkar(request):
    """
    Smart update endpoint that preserves manual edits based on tipkar.
    Supports all 5 document types: Escrituras, No Contenciosos, Transferencias, Garantías, Testamentos
    """
    print("SMART UPDATE DOCUMENT BY TIPKAR VIEW CALLED")
    
    # Get parameters
    template_id = request.POST.get("template_id")
    kardex = request.POST.get("kardex")

    if not all([template_id, kardex]):
        return Response(
            {"success": False, "message": "Faltan parámetros requeridos: template_id, kardex"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        template_id = int(template_id)
    except ValueError:
        return Response(
            {"success": False, "message": "Formato de template_id inválido"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        # Get the kardex record to determine the tipkar
        from notaria.models import Kardex

        kardex_obj = Kardex.objects.filter(kardex=kardex).first()

        if not kardex_obj:
            return Response(
                {"success": False, "message": f"Kardex {kardex} no encontrado"},
                status=status.HTTP_404_NOT_FOUND,
            )

        tipkar = kardex_obj.idtipkar
        
        # Log the update action
        from . import models
        models.DocumentosLogs.objects.create(
            kardex=kardex,
            user=request.user,
            action='U'  # U = Update
        )

        # Service map for all document types
        UPDATE_SERVICE_MAP = {
            1: {
                "name": "Escrituras Públicas",
                "class": EscrituraDocumentService,
                "method": "generate_escritura_publica_document"
            },
            2: {
                "name": "Asuntos No Contenciosos",
                "class": NoContenciososDocumentService,
                "method": "generate_no_contencioso_document"
            },
            3: {
                "name": "Transferencias Vehiculares",
                "class": TransferenciasVehicularesDocumentService,
                "method": "generate_transferencias_document"
            },
            4: {
                "name": "Garantías Mobiliarias",
                "class": GarantiasDocumentService,
                "method": "generate_garantias_document"
            },
            5: {
                "name": "Testamentos",
                "class": TestamentosDocumentService,
                "method": "generate_testamentos_document"
            },
        }

        # Get service configuration
        service_config = UPDATE_SERVICE_MAP.get(tipkar)
        
        if not service_config:
            return Response(
                {
                    "success": False,
                    "message": f"Actualización de documento no implementada para tipkar {tipkar}",
                },
                status=status.HTTP_501_NOT_IMPLEMENTED,
            )

        # Log which service we're using
        print(f"DEBUG: Updating {service_config['name']} document for tipkar {tipkar}")
        
        # Instantiate service and call update method
        try:
            service = service_config["class"]()
            update_method = getattr(service, service_config["method"])
            response = update_method(
                template_id=template_id,
                kardex=kardex,
                action="actualizar",
                mode="download"
            )
            return response
            
        except ValueError as e:
            # Handle validation errors (missing numescritura, document not found, etc.)
            return Response(
                {"success": False, "message": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

    except Exception as e:
        print(f"Error in smart update: {e}")
        return Response(
            {"success": False, "message": "Ocurrió un error interno en el servidor"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class DocumentosGeneradosViewSet(ModelViewSet):
    """
    ViewSet for the Documentogenerados model.
    """

    queryset = models.Documentogenerados.objects.all()
    serializer_class = serializers.DocumentosGeneradosSerializer
    pagination_class = pagination.KardexPagination
    # permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["get"])
    def by_kardex(self, request):
        """
        Get Documentogenerados records by Kardex.
        """
        kardex = request.query_params.get("kardex")
        if not kardex:
            return Response({"error": "kardex parameter is required."}, status=400)

        documentos_generados = models.Documentogenerados.objects.filter(kardex=kardex)
        if not documentos_generados.exists():
            return Response([], status=200)

        serializer = serializers.DocumentosGeneradosSerializer(documentos_generados, many=True)
        return Response(serializer.data)

    def _create_open_mode_response(self, request, kardex):
        """Helper method to create 'open' mode JSON response"""
        download_url = f"https://{request.get_host()}/docs/download/{kardex}/__PROY__{kardex}.docx"
        response = JsonResponse(
            {
                "status": "success",
                "mode": "open",
                "filename": f"__PROY__{kardex}.docx",
                "kardex": kardex,
                "url": download_url,
                "message": "Document ready to open in Word",
            }
        )
        response["Access-Control-Allow-Origin"] = "*"
        return response

    @action(detail=False, methods=["get"], url_path="open-template")
    def open_template(self, request):
        print(f"DEBUG: open_template")
        template_id = request.query_params.get("template_id")
        kardex = request.query_params.get("kardex")
        action = request.query_params.get("action", "generate")
        mode = request.query_params.get("mode", "download")

        user = request.user

        # Validation
        if not user:
            return HttpResponse({"error": "User not authenticated."}, status=401)
        if not template_id:
            return HttpResponse({"error": "Missing template_id parameter."}, status=400)
        if not kardex:
            return HttpResponse({"error": "Missing kardex parameter."}, status=400)

        # Get or create document tracking record (handle duplicates gracefully)
        todayTimeDate = datetime.now().isoformat() + "Z"
        print(f"DEBUG: kardex: {kardex}")
        
        # Check if any record exists for this kardex
        documentogenerados = models.Documentogenerados.objects.filter(kardex=kardex).first()
        
        if documentogenerados:
            print(f"DEBUG: Using existing documentogenerados: {documentogenerados}")
        else:
            # Create new record only if none exists
            documentogenerados = models.Documentogenerados.objects.create(
                    kardex=kardex,
                    usuario=user.idusuario,
                    fecha=todayTimeDate
                )
            print(f"DEBUG: Created new documentogenerados: {documentogenerados}")
        
        # Log the action in DocumentosLogs
        models.DocumentosLogs.objects.create(
            kardex=kardex,
            user=user,
            action='G'  # G = Generate
        )

        # Parse template_id
        try:
            template_id = int(template_id)
        except ValueError:
            return HttpResponse({"error": "Invalid template_id format."}, status=400)
        print(f"DEBUG: template_id: {template_id}")

        # Get kardex object to determine tipkar
        kardex_obj = Kardex.objects.filter(kardex=kardex).first()
        print(f"DEBUG: kardex_obj: {kardex_obj}")
        if not kardex_obj:
            return HttpResponse({"error": f"Kardex {kardex} not found"}, status=404)

        tipkar = kardex_obj.idtipkar

        # Service configuration mapping
        SERVICE_MAP = {
            1: {
                "name": "EscrituraPublicaDocumentService",
                "class": EscrituraDocumentService,
                "method": "generate_escritura_publica_document",
            },
            2: {
                "name": "NonContenciousDocumentService",
                "class": NoContenciososDocumentService,
                "method": "generate_no_contencioso_document",
            },
            3: {
                "name": "TransferenciasVehicularesDocumentService",
                "class": TransferenciasVehicularesDocumentService,
                "method": "generate_transferencias_document",
            },
            4: {
                "name": "GarantiasMobiliariasDocumentService",
                "class": GarantiasDocumentService,
                "method": "generate_garantias_document",
            },
            5: {
                "name": "TestamentosDocumentService",
                "class": TestamentosDocumentService,
                "method": "generate_testamentos_document",
            },
        }

        # Get service config
        service_config = SERVICE_MAP.get(tipkar)
        if not service_config:
            return HttpResponse(
                {"error": f"Document generation not implemented for tipkar {tipkar}"}, 
                status=501
            )

        # Create service instance
        print(f"DEBUG: Using {service_config['name']} for tipkar {tipkar}")
        service = service_config["class"]()

        # Handle 'open' mode
        if mode == "open":
            return self._create_open_mode_response(request, kardex)

        # Generate document
        generate_method = getattr(service, service_config["method"])
        return generate_method(template_id, kardex, action, mode)

    def _get_document_from_r2(self, kardex):
        """Helper method to retrieve document from R2 if it exists"""
        object_key = f"{os.environ.get('CLOUDFLARE_R2_MAIN_URL')}/documentos/__PROY__{kardex}.docx"
        print(f"DEBUG: Checking if document exists in R2: {object_key}")
        
        s3 = boto3.client(
            "s3",
            endpoint_url=os.environ.get("CLOUDFLARE_R2_ENDPOINT"),
            aws_access_key_id=os.environ.get("CLOUDFLARE_R2_ACCESS_KEY"),
            aws_secret_access_key=os.environ.get("CLOUDFLARE_R2_SECRET_KEY"),
            config=Config(signature_version="s3v4"),
            region_name="auto",
        )
        
        try:
            s3_response = s3.get_object(
                Bucket=os.environ.get("CLOUDFLARE_R2_BUCKET"), Key=object_key
            )
            print(f"DEBUG: Document found in R2")
            return s3_response["Body"].read()
        except Exception as e:
            print(f"DEBUG: Document not found in R2: {e}")
            return None

    def _create_download_response(self, doc_content, kardex):
        """Helper method to create download response"""
        response = HttpResponse(
            doc_content,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        response["Content-Disposition"] = f'inline; filename="__PROY__{kardex}.docx"'
        response["Content-Length"] = str(len(doc_content))
        response["Access-Control-Allow-Origin"] = "*"
        return response

    @action(detail=False, methods=["get"], url_path="open-document")
    def open_document(self, request):
        """
        Will look for the document in the r2 storage, and if it exists, it will return the document
        If it doesn't exist, it will generate the document from the template, save it in R2, and return the document
        """
        template_id = request.query_params.get("template_id")
        kardex = request.query_params.get("kardex", "ACT401-2025")
        action = request.query_params.get("action", "generate")
        mode = request.query_params.get("mode", "download")

        user = request.user

        # Validation
        if not user:
            return HttpResponse({"error": "User not authenticated."}, status=401)
        if not template_id:
            return HttpResponse({"error": "Missing template_id parameter."}, status=400)
        if not kardex:
            return HttpResponse({"error": "Missing kardex parameter."}, status=400)

        # Parse template_id
        try:
            template_id = int(template_id)
        except ValueError:
            return HttpResponse({"error": "Invalid template_id format."}, status=400)

        # Try to get existing document from R2
        doc_content = self._get_document_from_r2(kardex)
        
        if doc_content:
            # Document exists in R2, return it
            # Log the open action
            models.DocumentosLogs.objects.create(
                kardex=kardex,
                user=user,
                action='O'  # O = Open
            )

            if mode == "open":
                return self._create_open_mode_response(request, kardex)
            else:
                return self._create_download_response(doc_content, kardex)

        # Document doesn't exist, generate it
        print(f"DEBUG: Generating new document for kardex: {kardex}")

        # Get kardex object to determine tipkar
        kardex_obj = Kardex.objects.filter(kardex=kardex).first()
        if not kardex_obj:
            return HttpResponse({"error": f"Kardex {kardex} no encontrado"}, status=404)

        tipkar = kardex_obj.idtipkar

        # Use the same SERVICE_MAP as open_template
        SERVICE_MAP = {
            1: {
                "name": "EscrituraPublicaDocumentService",
                "class": EscrituraDocumentService,
                "method": "generate_escritura_publica_document",
            },
            2: {
                "name": "NonContenciousDocumentService",
                "class": NoContenciososDocumentService,
                "method": "generate_no_contencioso_document",
            },
            3: {
                "name": "TransferenciasVehicularesDocumentService",
                "class": TransferenciasVehicularesDocumentService,
                "method": "generate_transferencias_document",
            },
            4: {
                "name": "GarantiasMobiliariasDocumentService",
                "class": GarantiasDocumentService,
                "method": "generate_garantias_document",
            },
            5: {
                "name": "TestamentosDocumentService",
                "class": TestamentosDocumentService,
                "method": "generate_testamentos_document",
            },
        }

        # Get service config
        service_config = SERVICE_MAP.get(tipkar)
        if not service_config:
            return HttpResponse(
                {"error": f"La generación de documentos no está implementada para tipkar {tipkar}"}, 
                status=501
            )

        # Create service instance
        print(f"DEBUG: Using {service_config['name']} for tipkar {tipkar}")
        service = service_config["class"]()

        # Handle 'open' mode
        if mode == "open":
            return self._create_open_mode_response(request, kardex)

        # Generate document
        generate_method = getattr(service, service_config["method"])
        return generate_method(template_id, kardex, action, mode)


class DocumentosLogsViewSet(ModelViewSet):
    """
    ViewSet for the DocumentosLogs model.
    """

    queryset = models.DocumentosLogs.objects.all()
    serializer_class = serializers.DocumentosLogsSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["get"])
    def by_kardex(self, request):
        """
        Get DocumentosLogs by kardex
        """
        kardex = request.query_params.get("kardex")
        logs = models.DocumentosLogs.objects.filter(kardex=kardex)

        if not logs.exists():
            return Response([], status=200)

        serializer = serializers.DocumentosLogsSerializer(logs, many=True)
        return Response(serializer.data)


# Create S3 client once at module level for better performance
_s3_client = None


def get_s3_client():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client(
            "s3",
            endpoint_url=os.environ.get("CLOUDFLARE_R2_ENDPOINT"),
            aws_access_key_id=os.environ.get("CLOUDFLARE_R2_ACCESS_KEY"),
            aws_secret_access_key=os.environ.get("CLOUDFLARE_R2_SECRET_KEY"),
            config=Config(signature_version="s3v4"),
            region_name="auto",
        )
    return _s3_client


@api_view(["GET"])
# @permission_classes([IsAuthenticated])
def download_docx(request, kardex, kardex2):
    """
    Secure endpoint to stream a docx file from R2 to the user.
    Only authenticated users can access. Returns 404 if not found.
    """
    import boto3
    import os
    import time
    from botocore.client import Config
    from django.http import FileResponse, Http404, HttpResponse

    start_time = time.time()

    object_key = f"{os.environ.get('CLOUDFLARE_R2_MAIN_URL')}/documentos/__PROY__{kardex}.docx"

    try:
        s3 = get_s3_client()
        s3_response = s3.get_object(Bucket=os.environ.get("CLOUDFLARE_R2_BUCKET"), Key=object_key)
        file_stream = s3_response["Body"]
        response = FileResponse(
            file_stream,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        response["Content-Disposition"] = f'inline; filename="__PROY__{kardex}.docx"'
        # Add caching headers for better performance
        response["Cache-Control"] = "public, max-age=3600"  # Cache for 1 hour
        response["ETag"] = f'"{kardex}"'

        # Log performance metrics
        elapsed_time = time.time() - start_time
        print(f"DEBUG: download_docx took {elapsed_time:.2f} seconds for kardex: {kardex}")

        return response
    except s3.exceptions.NoSuchKey:
        raise Http404("Document not found")
    except Exception as e:
        return HttpResponse(f"Error: {str(e)}", status=500)


@api_view(["GET"])
def test_r2_connection(request):
    """
    Test R2 connection and configuration
    """
    try:
        # Check environment variables
        endpoint_url = os.environ.get("CLOUDFLARE_R2_ENDPOINT")
        access_key = os.environ.get("CLOUDFLARE_R2_ACCESS_KEY")
        secret_key = os.environ.get("CLOUDFLARE_R2_SECRET_KEY")
        bucket = os.environ.get("CLOUDFLARE_R2_BUCKET")

        config_status = {
            "endpoint_url": endpoint_url,
            "access_key_set": bool(access_key),
            "secret_key_set": bool(secret_key),
            "bucket": bucket,
        }

        # Test S3 client creation
        s3 = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(signature_version="s3v4"),
            region_name="auto",
        )

        # Test bucket access
        try:
            s3.head_bucket(Bucket=bucket)
            bucket_access = True
        except Exception as e:
            bucket_access = False
            bucket_error = str(e)

        return Response(
            {
                "success": True,
                "config_status": config_status,
                "s3_client_created": True,
                "bucket_access": bucket_access,
                "bucket_error": bucket_error if not bucket_access else None,
            }
        )

    except Exception as e:
        return Response(
            {
                "success": False,
                "error": str(e),
                "config_status": config_status if "config_status" in locals() else None,
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class ExtraprotocolaresViewSet(ModelViewSet):
    """
    ViewSet for handling all extraprotocolares document types including permiso viajes.
    This provides a modular approach for the 7+ different permiso viaje types.
    """

    serializer_class = serializers.DocumentosGeneradosSerializer  # Reuse existing serializer
    pagination_class = pagination.KardexPagination
    # permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """
        Return empty queryset since this ViewSet is only for document generation
        """
        return models.Documentogenerados.objects.none()

    @action(detail=False, methods=["get"], url_path="permiso-viaje-interior")
    def permiso_viaje_interior(self, request):
        """
        Generate Permiso Viaje Interior document
        """
        print("DEBUG: ExtraprotocolaresViewSet.permiso_viaje_interior called")

        # Get parameters
        id_viaje = request.query_params.get("id_viaje")
        action = request.query_params.get("action", "generate")  # Default to 'generate'
        mode = request.query_params.get("mode", "download")

        if not id_viaje:
            return Response(
                {"status": "error", "message": "id_viaje parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        service = PermisoViajeInteriorDocumentService()
        if action == "retrieve":
            return service.retrieve_document(id_viaje, mode)
        else:
            return service.generate_permiso_viaje_interior_document(id_viaje, mode)

    @action(detail=False, methods=["get"], url_path="permiso-viaje-exterior")
    def permiso_viaje_exterior(self, request):
        """
        Generate or retrieve a Permiso Viaje Exterior document.
        - action=generate: Creates a new document, saves it to R2, and returns it.
        - action=retrieve: Fetches an existing document from R2 and returns it.
        """
        id_viaje = request.query_params.get("id_viaje")
        action = request.query_params.get("action", "generate")
        mode = request.query_params.get("mode", "download")

        if not id_viaje:
            return Response(
                {"status": "error", "message": "id_viaje parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        service = PermisoViajeExteriorDocumentService()
        if action == "retrieve":
            return service.retrieve_document(id_viaje, mode)
        else:
            return service.generate_permiso_viaje_exterior_document(id_viaje, mode)

    @action(detail=False, methods=["get"], url_path="poder-fuera-registro")
    def poder_fuera_registro(self, request):
        """
        Generate or retrieve a Poder Fuera de Registro document.
        - action=generate: Creates a new document, saves it to R2, and returns it.
        - action=retrieve: Fetches an existing document from R2 and returns it.
        """
        id_poder = request.query_params.get("id_poder")
        action = request.query_params.get("action", "generate")
        mode = request.query_params.get("mode", "download")

        if not id_poder:
            return Response(
                {"status": "error", "message": "id_poder parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Build filename using legacy pattern: __PODER__{id_poder}-{anioKardex}.docx
        try:
            rec = IngresoPoderes.objects.get(id_poder=id_poder)
            num_kardex = rec.num_kardex
            if not num_kardex:
                return Response(
                    {"status": "error", "message": "num_kardex is empty for the provided id_poder"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            anio_kardex = (num_kardex or "")[:4]
            filename = f"__PODER__{id_poder}-{anio_kardex}.docx"
        except IngresoPoderes.DoesNotExist:
            return Response(
                {
                    "status": "error",
                    "message": f"IngresoPoderes with id_poder {id_poder} not found",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        service = PoderFueraDeRegistroDocumentService()
        if action == "retrieve":
            return service.retrieve_document(id_poder, filename, mode)
        else:
            return service.generate_poder_fuera_registro_document(id_poder, mode)

    @action(detail=False, methods=["get"], url_path="poder-essalud")
    def poder_essalud(self, request):
        """
        Generate or retrieve a Poder Essalud document.
        - action=generate: Creates a new document, saves it to R2, and returns it.
        - action=retrieve: Fetches an existing document from R2 and returns it.
        """
        id_poder = request.query_params.get("id_poder")
        action = request.query_params.get("action", "generate")  # generate, retrieve
        mode = request.query_params.get("mode", "download")  # download, open

        if not id_poder:
            return Response({"error": "id_poder is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            rec = IngresoPoderes.objects.get(id_poder=id_poder)
            num_kardex = rec.num_kardex
            if not num_kardex:
                return Response(
                    {"status": "error", "message": "num_kardex is empty for the provided id_poder"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            anio_kardex = (num_kardex or "")[:4]
            filename = f"__PODER__{id_poder}-{anio_kardex}.docx"
        except IngresoPoderes.DoesNotExist:
            return Response(
                {
                    "status": "error",
                    "message": f"IngresoPoderes with id_poder {id_poder} not found",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        service = PoderEssaludDocumentService()
        if action == "retrieve":
            return service.retrieve_document(id_poder, filename, mode)
        else:
            return service.generate_poder_essalud_document(id_poder, mode)

    @action(detail=False, methods=["get"], url_path="poder-onp")
    def poder_onp(self, request):
        """
        Generate or retrieve a Poder ONP document.
        - action=generate: Creates a new document, saves it to R2, and returns it.
        - action=retrieve: Fetches an existing document from R2 and returns it.
        """
        id_poder = request.query_params.get("id_poder")
        action = request.query_params.get("action", "generate")
        mode = request.query_params.get("mode", "download")

        if not id_poder:
            return Response({"error": "id_poder is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            rec = IngresoPoderes.objects.get(id_poder=id_poder)
            num_kardex = rec.num_kardex
            if not num_kardex:
                return Response(
                    {"status": "error", "message": "num_kardex is empty for the provided id_poder"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            anio_kardex = (num_kardex or "")[:4]
            filename = f"__PODER__{id_poder}-{anio_kardex}.docx"
        except IngresoPoderes.DoesNotExist:
            return Response(
                {
                    "status": "error",
                    "message": f"IngresoPoderes with id_poder {id_poder} not found",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        service = PoderPensionDocumentService()
        if action == "retrieve":
            return service.retrieve_document(id_poder, filename, mode)
        else:
            return service.generate_poder_pension_document(id_poder, mode)

    @action(detail=False, methods=["get"], url_path="carta-notarial")
    def carta_notarial(self, request):
        """
        Generate or retrieve a Carta Notarial document.
        - action=generate: Creates a new document, saves it to R2, and returns it.
        - action=retrieve: Fetches an existing document from R2 and returns it.
        """
        id_carta = request.query_params.get("id_carta")
        print(f"DEBUG: id_carta: {id_carta}")
        action = request.query_params.get("action", "generate")
        mode = request.query_params.get("mode", "download")

        if not id_carta:
            return Response({"error": "id_carta is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            rec = IngresoCartas.objects.get(id_carta=id_carta)
            print(f"DEBUG: rec: {rec}")
            num_carta = rec.num_carta
            if not num_carta:
                return Response(
                    {"status": "error", "message": "num_carta is empty for the provided id_carta"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except IngresoCartas.DoesNotExist:
            return Response(
                {"status": "error", "message": f"IngresoCartas with id_carta {id_carta} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        service = CartasNotarialesDocumentService()
        if action == "retrieve":
            return service.retrieve_carta_document(num_carta, mode)
        else:
            return service.generate_carta_document(num_carta, mode)

    @action(detail=False, methods=["get"], url_path="cert-domiciliario")
    def cert_domiciliario(self, request):
        """
        Generate or retrieve a Cert Domiciliario document.
        - action=generate: Creates a new document, saves it to R2, and returns it.
        - action=retrieve: Fetches an existing document from R2 and returns it.
        """
        id_domiciliario = request.query_params.get("id_domiciliario")
        action = request.query_params.get("action", "generate")
        mode = request.query_params.get("mode", "download")

        if not id_domiciliario:
            return Response(
                {"error": "num_certificado is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            rec = CertDomiciliario.objects.get(id_domiciliario=id_domiciliario)
            num_certificado = rec.num_certificado
            if not rec:
                return Response(
                    {"error": "CertDomiciliario with id_domiciliario {id_domiciliario} not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )
        except CertDomiciliario.DoesNotExist:
            return Response(
                {"error": f"CertDomiciliario with id_domiciliario {id_domiciliario} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        service = CertDomiciliariosDocumentService()
        if action == "retrieve":
            return service.retrieve_cdom_document(num_certificado, mode)
        else:
            return service.generate_cdom_document(num_certificado, mode)

    @action(detail=False, methods=["get"], url_path="libro")
    def libro(self, request):
        """
        Generate or retrieve a Libro document.
        - action=generate: Creates a new document, saves it to R2, and returns it.
        - action=retrieve: Fetches an existing document from R2 and returns it.
        Query params:
        - num_libro: required
        - orientation: optional ('H' or 'V'), defaults to 'V' (vertical)
        - action: optional ('generate' | 'retrieve'), defaults to 'generate'
        - mode: optional ('download' | 'open'), defaults to 'download'
        """
        id_libro = request.query_params.get("id_libro")
        orientation = request.query_params.get("orientation", "V")
        action = request.query_params.get("action", "generate")
        mode = request.query_params.get("mode", "download")

        if not id_libro:
            return Response(
                {"status": "error", "message": "num_libro is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            rec = Libros.objects.get(id=id_libro)
            num_libro = rec.numlibro
            anio_libro = rec.ano
        except Libros.DoesNotExist:
            return Response(
                {"status": "error", "message": f"Libros with id {id_libro} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not anio_libro:
            return Response(
                {
                    "status": "error",
                    "message": f"ano is empty for the provided num_libro {num_libro}",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        service = LibrosDocumentService()
        if action == "retrieve":
            return service.retrieve_libro_document(num_libro, str(anio_libro), mode)
        else:
            return service.generate_libro_document(num_libro, str(anio_libro), orientation, mode)


@require_api_token
@require_http_methods(["POST"])
def save_doc(request):
    """
    Save changes made in Word document back to R2 bucket
    Receives a file upload and saves it to the R2 storage
    """
    try:
        # Check if file was uploaded
        if "file" not in request.FILES:
            return JsonResponse({"status": "error", "message": "No file uploaded"}, status=400)

        uploaded_file = request.FILES["file"]

        # Validate file type
        if not uploaded_file.name.endswith(".docx"):
            return JsonResponse(
                {"status": "error", "message": "Only .docx files are allowed"}, status=400
            )

        # Sanitize filename:
        # - remove trailing " (n)" or "(n)" before extension
        # - trim spaces around the basename
        # - preserve original extension
        filename = uploaded_file.name
        try:
            import os as _os
            import re as _re
            base, ext = _os.path.splitext(filename)
            # Remove optional whitespace + (digits) at the end of the base name
            base = _re.sub(r"\s*\(\d+\)\s*$", "", base)
            base = base.strip()
            sanitized_filename = f"{base}{ext}"
        except Exception:
            # Fallback to original if anything odd happens
            sanitized_filename = filename

        object_key = f"{os.environ.get('CLOUDFLARE_R2_MAIN_URL')}/documentos/{sanitized_filename}"

        print(f"DEBUG: Saving document to R2: {object_key}")
        print(f"DEBUG: Filename (original): {filename}")
        print(f"DEBUG: Filename (sanitized): {sanitized_filename}")
        print(f"DEBUG: File size: {uploaded_file.size} bytes")

        # Create S3 client
        s3 = boto3.client(
            "s3",
            endpoint_url=os.environ.get("CLOUDFLARE_R2_ENDPOINT"),
            aws_access_key_id=os.environ.get("CLOUDFLARE_R2_ACCESS_KEY"),
            aws_secret_access_key=os.environ.get("CLOUDFLARE_R2_SECRET_KEY"),
            config=Config(signature_version="s3v4"),
            region_name="auto",
        )

        # Upload file to R2
        try:
            s3.upload_fileobj(uploaded_file, os.environ.get("CLOUDFLARE_R2_BUCKET"), object_key)

            print(f"DEBUG: Successfully saved document to R2: {object_key}")

            return JsonResponse(
                {
                    "status": "success",
                    "message": "Document saved successfully",
                    "filename": sanitized_filename,
                    "r2_path": object_key,
                    "file_size": uploaded_file.size,
                }
            )

        except Exception as e:
            print(f"DEBUG: Error uploading to R2: {e}")
            return JsonResponse(
                {"status": "error", "message": f"Failed to save document to R2: {str(e)}"},
                status=500,
            )

    except Exception as e:
        print(f"DEBUG: Error in save_doc view: {e}")
        return JsonResponse(
            {"status": "error", "message": f"Internal server error: {str(e)}"}, status=500
        )


@api_view(["GET"])
@permission_classes([IsAuthenticated, IsAdminUser])
def generate_token(request):
    """
    Generate a new secure token for API access
    This endpoint is for admin use only
    """
    try:
        token, token_hash = generate_secure_token()
        return Response(
            {
                "status": "success",
                "message": "Token generated successfully",
                "token": token,
                "token_hash": token_hash,
                "note": "Store this token securely. It will not be shown again.",
            }
        )
    except Exception as e:
        return Response(
            {"status": "error", "message": f"Failed to generate token: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
