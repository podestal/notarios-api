from django.shortcuts import render
from rest_framework.viewsets import ModelViewSet
from rest_framework.decorators import action
from rest_framework.response import Response
from . import models, serializers
from notaria.models import TplTemplate
from notaria import pagination
from django.http import HttpResponse
import boto3
from botocore.client import Config
from django.conf import settings
import os
from docx import Document
import io

class DocumentosGeneradosViewSet(ModelViewSet):
    """
    ViewSet for the Documentogenerados model.
    """
    queryset = models.Documentogenerados.objects.all()
    serializer_class = serializers.DocumentosGeneradosSerializer
    pagination_class = pagination.KardexPagination

    @action(detail=False, methods=['get'])
    def by_kardex(self, request):
        """
        Get Documentogenerados records by Kardex.
        """
        kardex = request.query_params.get('kardex')
        if not kardex:
            return Response(
                {"error": "kardex parameter is required."},
                status=400
            )
        
        documentos_generados = models.Documentogenerados.objects.filter(kardex=kardex)
        if not documentos_generados.exists():
            return Response([], status=200)

        serializer = serializers.DocumentosGeneradosSerializer(documentos_generados, many=True)
        return Response(serializer.data)
    

    @action(detail=False, methods=['get'], url_path='template-download')
    def download_template(self, request):
        """
        Return the .docx file from R2 given a template_id and fill Acquirer (Buyer) data.
        """
        template_id = request.query_params.get("template_id")
        if not template_id:
            return Response({"error": "Missing template_id parameter."}, status=400)

        try:
            template = TplTemplate.objects.get(pktemplate=template_id)
        except TplTemplate.DoesNotExist:
            return Response({"error": "Template not found."}, status=404)

        object_key = f"rodriguez-zea/PROTOCOLARES/ACTAS DE TRANSFERENCIA DE BIENES MUEBLES REGISTRABLES/{template.filename}"

        # Connect to R2 via boto3
        s3 = boto3.client(
            's3',
            endpoint_url=os.environ.get('CLOUDFLARE_R2_ENDPOINT'),
            aws_access_key_id=os.environ.get('CLOUDFLARE_R2_ACCESS_KEY'),
            aws_secret_access_key=os.environ.get('CLOUDFLARE_R2_SECRET_KEY'),
            config=Config(signature_version='s3v4'),
            region_name='auto',
        )

        try:
            # Retrieve the template file from R2
            s3_response = s3.get_object(
                Bucket=os.environ.get('CLOUDFLARE_R2_BUCKET'),
                Key=object_key,
            )
            file_stream = s3_response['Body'].read()

            # Load the template into python-docx
            doc = Document(io.BytesIO(file_stream))

            # Fill Acquirer (Buyer) data with funny Spanish names

            # [E.P_NOM_1], [E.P_NOM_2], etc.: Transferor names.
            # [E.P_NACIONALIDAD_1], [E.P_NACIONALIDAD_2], etc.: Transferor nationality.
            # [E.P_TIP_DOC_1], [E.P_TIP_DOC_2], etc.: Transferor document type.
            # [E.P_DOC_1], [E.P_DOC_2], etc.: Transferor document number.
            # [E.P_OCUPACION_1], [E.P_OCUPACION_2], etc.: Transferor occupation.
            # [E.P_ESTADO_CIVIL_1], [E.P_ESTADO_CIVIL_2], etc.: Transferor marital status.
            # [E.P_DOMICILIO_1], [E.P_DOMICILIO_2], etc.: Transferor address.
            # [E.P_CALIDAD_1], [E.P_CALIDAD_2], etc.: Transferor quality.
            # [E.P_IDE_1], [E.P_IDE_2], etc.: Transferor identification.
            # [E.P_FIRMA_1], [E.P_FIRMA_2], etc.: Transferor signature.
            # [E.P_AMBOS_1], [E.P_AMBOS_2], etc.: Transferor both.
            acquirer_data = {
                "[E.C_NOM_1]": "Juanito Pérez ",
                "[E.C_NOM_2]": "María López ",
                "[E.C_NACIONALIDAD_1]": "Mexicana",
                "[E.C_NACIONALIDAD_2]": "",
                "[E.C_TIP_DOC_1]": "DNI",
                "[E.C_TIP_DOC_2]": "",
                "[E.C_DOC_1]": "12345678",
                "[E.C_DOC_2]": "",
                "[E.C_OCUPACION_1]": "Panadero",
                "[E.C_OCUPACION_2]": "",
                "[E.C_ESTADO_CIVIL_1]": "Soltero",
                "[E.C_ESTADO_CIVIL_2]": "",
                "[E.C_DOMICILIO_1]": "Calle Falsa 123, Madrid",
                "[E.C_DOMICILIO_2]": "",
                "[E.C_CALIDAD_1]": "Comprador",
                "[E.C_CALIDAD_2]": "",
                "[E.C_IDE_1]": "",
                "[E.C_IDE_2]": "",
                "[E.C_FIRMA_1]": "Firma de Juanito",
                "[E.C_FIRMA_2]": "Firma de María",
                "[E.C_AMBOS_1]": "Ambos",
                "[E.C_AMBOS_2]": "Ambos",
            }

            # Replace placeholders in the document
            for paragraph in doc.paragraphs:
                for placeholder, value in acquirer_data.items():
                    if placeholder in paragraph.text:
                        paragraph.text = paragraph.text.replace(placeholder, value)

            # Save the modified document to a temporary file
            temp_file_path = f"/tmp/{template.filename}"
            doc.save(temp_file_path)

            # Return the modified document as a response
            with open(temp_file_path, "rb") as modified_file:
                response = HttpResponse(modified_file.read(), content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
                response['Content-Disposition'] = f'attachment; filename="{template.filename}"'
                return response

        except Exception as e:
            return Response({"error": f"Failed to process document: {str(e)}"}, status=500)
    
    # @action(detail=False, methods=['get'], url_path='template-download')
    # def download_template(self, request):
    #     """
    #     Return the .docx file from R2 given a template_id.
    #     """
    #     template_id = request.query_params.get("template_id")
    #     if not template_id:
    #         return Response({"error": "Missing template_id parameter."}, status=400)

    #     try:
    #         template = TplTemplate.objects.get(pktemplate=template_id)
    #     except TplTemplate.DoesNotExist:
    #         return Response({"error": "Template not found."}, status=404)

    #     object_key = f"rodriguez-zea/PROTOCOLARES/ACTAS DE TRANSFERENCIA DE BIENES MUEBLES REGISTRABLES/{template.filename}"

    #     # Connect to R2 via boto3
    #     s3 = boto3.client(
    #         's3',
    #         endpoint_url=os.environ.get('CLOUDFLARE_R2_ENDPOINT'),
    #         aws_access_key_id=os.environ.get('CLOUDFLARE_R2_ACCESS_KEY'),
    #         aws_secret_access_key=os.environ.get('CLOUDFLARE_R2_SECRET_KEY'),
    #         config=Config(signature_version='s3v4'),
    #         region_name='auto',
    #     )

    #     try:
    #         s3_response = s3.get_object(
    #             Bucket=os.environ.get('CLOUDFLARE_R2_BUCKET'),
    #             Key=object_key,
    #         )
    #         file_stream = s3_response['Body'].read()
    #         response = HttpResponse(file_stream, content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    #         response['Content-Disposition'] = f'attachment; filename="{template.filename}"'
    #         return response
    #     except Exception as e:
    #         return Response({"error": f"Failed to download document: {str(e)}"}, status=500)
