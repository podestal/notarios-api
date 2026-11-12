from rest_framework import status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from documentos.models import DocumentoBien
from documentos.serializers import (
    DocumentoBienSerializer,
    DocumentoVehicularApplySerializer,
    DocumentoVehicularUploadSerializer,
)
from documentos.services.apply_vehicular import (
    apply_documento_vehicular_to_detalle,
    list_pending_vehiculares,
)
from documentos.services.upload import (
    delete_documento_bien,
    list_documentos_vehiculares,
    submit_documento_vehicular,
)
from notaria.serializers import DetallevehicularSerializer


class DocumentoVehicularListCreateView(APIView):
    """
    GET  /documentos/vehiculares/ — all vehicular boletas (linked + pending).
    POST /documentos/vehiculares/ — upload + parse SUNARP Boleta Informativa PDF.
    """

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        qs = list_documentos_vehiculares()
        return Response(DocumentoBienSerializer(qs, many=True).data)

    def post(self, request):
        serializer = DocumentoVehicularUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        uploaded = serializer.validated_data["file"]
        try:
            doc = submit_documento_vehicular(
                uploaded_file=uploaded,
                original_filename=getattr(uploaded, "name", "") or "boleta.pdf",
                uploaded_by=request.user,
                content_type=getattr(uploaded, "content_type", "") or "application/pdf",
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        payload = DocumentoBienSerializer(doc).data
        code = (
            status.HTTP_201_CREATED
            if doc.status == DocumentoBien.STATUS_PARSED
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        return Response(payload, status=code)


class DocumentoVehicularPendingView(APIView):
    """GET /documentos/vehiculares/pendientes/ — parsed boletas not yet linked to detalle."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = list_pending_vehiculares()
        return Response(DocumentoBienSerializer(qs, many=True).data)


class DocumentoVehicularApplyView(APIView):
    """
    POST /documentos/vehiculares/aplicar/

    Body: {documento_id, kardex, idtipacto, replace_existing?}
    Creates/updates detallevehicular and links DocumentoBien.detveh.
    """

    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, FormParser, MultiPartParser]

    def post(self, request):
        serializer = DocumentoVehicularApplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            doc, detalle = apply_documento_vehicular_to_detalle(
                documento_id=data["documento_id"],
                kardex=data["kardex"],
                idtipacto=data["idtipacto"],
                replace_existing=data.get("replace_existing", True),
                overwrite_detalle=data.get("overwrite_detalle", True),
                detveh=data.get("detveh"),
            )
        except LookupError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "documento": DocumentoBienSerializer(doc).data,
                "detallevehicular": DetallevehicularSerializer(detalle).data,
            },
            status=status.HTTP_200_OK,
        )


class DocumentoBienDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk: int):
        doc = DocumentoBien.objects.filter(pk=pk).first()
        if not doc:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(DocumentoBienSerializer(doc).data)

    def delete(self, request, pk: int):
        doc = DocumentoBien.objects.filter(pk=pk).first()
        if not doc:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)
        delete_documento_bien(doc)
        return Response(status=status.HTTP_204_NO_CONTENT)
