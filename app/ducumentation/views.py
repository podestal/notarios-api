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
import uuid

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
    
    @action(detail=False, methods=['get'], url_path='open-template')
    def open_template(self, request):
        """
        Stream a filled Word document (.docx) directly from R2 so Word can open it.
        """
        template_id = request.query_params.get("template_id")
        if not template_id:
            return Response({"error": "Missing template_id parameter."}, status=400)

        try:
            template_id = int(template_id)  # this ensures we only accept clean integers
        except ValueError:
            return Response({"error": "Invalid template_id format."}, status=400)

        try:
            template = TplTemplate.objects.get(pktemplate=template_id)
        except TplTemplate.DoesNotExist:
            return Response({"error": "Template not found."}, status=404)

        object_key = f"rodriguez-zea/PROTOCOLARES/ACTAS DE TRANSFERENCIA DE BIENES MUEBLES REGISTRABLES/{template.filename}"

        # Connect to R2
        s3 = boto3.client(
            's3',
            endpoint_url=os.environ.get('CLOUDFLARE_R2_ENDPOINT'),
            aws_access_key_id=os.environ.get('CLOUDFLARE_R2_ACCESS_KEY'),
            aws_secret_access_key=os.environ.get('CLOUDFLARE_R2_SECRET_KEY'),
            config=Config(signature_version='s3v4'),
            region_name='auto',
        )

        try:
            # Retrieve and modify the file
            s3_response = s3.get_object(Bucket=os.environ.get('CLOUDFLARE_R2_BUCKET'), Key=object_key)
            file_stream = s3_response['Body'].read()

            doc = Document(io.BytesIO(file_stream))

            acquirer_data = {
                "[E.C_NOM_1]": "Juanito Pérez ",
                # ... your other placeholder replacements ...
            }

            for paragraph in doc.paragraphs:
                for placeholder, value in acquirer_data.items():
                    if placeholder in paragraph.text:
                        paragraph.text = paragraph.text.replace(placeholder, value)

            buffer = io.BytesIO()
            doc.save(buffer)
            buffer.seek(0)

            # Respond directly with the document
            # response = HttpResponse(buffer.read(), content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
            # response['Content-Disposition'] = f'inline; filename="{template.filename}"'  # NOT attachment
            # return response

            response = HttpResponse(
                buffer.read(),
                content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            )
            response['Content-Disposition'] = f'inline; filename="{template.filename}"'
            response['Content-Length'] = str(buffer.getbuffer().nbytes)
            response['Access-Control-Allow-Origin'] = '*'
            return response

        except Exception as e:
            return Response({"error": f"Failed to open document: {str(e)}"}, status=500)

    
    # @action(detail=False, methods=['get'], url_path='template-download')
    # def download_template(self, request):
    #     """
    #     Return a pre-signed URL for the filled .docx template from R2 given a template_id.
    #     """
    #     template_id = request.query_params.get("template_id")
    #     if not template_id:
    #         return Response({"error": "Missing template_id parameter."}, status=400)

    #     try:
    #         template = TplTemplate.objects.get(pktemplate=template_id)
    #     except TplTemplate.DoesNotExist:
    #         return Response({"error": "Template not found."}, status=404)

    #     object_key = f"rodriguez-zea/PROTOCOLARES/ACTAS DE TRANSFERENCIA DE BIENES MUEBLES REGISTRABLES/{template.filename}"

    #     # Connect to R2
    #     s3 = boto3.client(
    #         's3',
    #         endpoint_url=os.environ.get('CLOUDFLARE_R2_ENDPOINT'),
    #         aws_access_key_id=os.environ.get('CLOUDFLARE_R2_ACCESS_KEY'),
    #         aws_secret_access_key=os.environ.get('CLOUDFLARE_R2_SECRET_KEY'),
    #         config=Config(signature_version='s3v4'),
    #         region_name='auto',
    #     )

    #     try:
    #         # Retrieve the template file from R2
    #         s3_response = s3.get_object(
    #             Bucket=os.environ.get('CLOUDFLARE_R2_BUCKET'),
    #             Key=object_key,
    #         )
    #         file_stream = s3_response['Body'].read()

    #         # Load and modify the document
    #         doc = Document(io.BytesIO(file_stream))

    #         acquirer_data = {
    #             "[E.C_NOM_1]": "Juanito Pérez ",
    #             "[E.C_NOM_2]": "María López ",
    #             "[E.C_NACIONALIDAD_1]": "Mexicana",
    #             "[E.C_NACIONALIDAD_2]": "",
    #             "[E.C_TIP_DOC_1]": "DNI",
    #             "[E.C_TIP_DOC_2]": "",
    #             "[E.C_DOC_1]": "12345678",
    #             "[E.C_DOC_2]": "",
    #             "[E.C_OCUPACION_1]": "Panadero",
    #             "[E.C_OCUPACION_2]": "",
    #             "[E.C_ESTADO_CIVIL_1]": "Soltero",
    #             "[E.C_ESTADO_CIVIL_2]": "",
    #             "[E.C_DOMICILIO_1]": "Calle Falsa 123, Madrid",
    #             "[E.C_DOMICILIO_2]": "",
    #             "[E.C_CALIDAD_1]": "Comprador",
    #             "[E.C_CALIDAD_2]": "",
    #             "[E.C_IDE_1]": "",
    #             "[E.C_IDE_2]": "",
    #             "[E.C_FIRMA_1]": "Firma de Juanito",
    #             "[E.C_FIRMA_2]": "Firma de María",
    #             "[E.C_AMBOS_1]": "Ambos",
    #             "[E.C_AMBOS_2]": "Ambos",
    #         }

    #         for paragraph in doc.paragraphs:
    #             for placeholder, value in acquirer_data.items():
    #                 if placeholder in paragraph.text:
    #                     paragraph.text = paragraph.text.replace(placeholder, value)

    #         # Save to in-memory buffer
    #         buffer = io.BytesIO()
    #         doc.save(buffer)
    #         buffer.seek(0)

    #         # Upload to R2 under a new key
    #         new_key = f"rodriguez-zea/generated/{uuid.uuid4()}_{template.filename}"

    #         s3.put_object(
    #             Bucket=os.environ.get('CLOUDFLARE_R2_BUCKET'),
    #             Key=new_key,
    #             Body=buffer,
    #             ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    #         )

    #         # Generate pre-signed URL
    #         presigned_url = s3.generate_presigned_url(
    #             ClientMethod='get_object',
    #             Params={
    #                 'Bucket': os.environ.get('CLOUDFLARE_R2_BUCKET'),
    #                 'Key': new_key,
    #             },
    #             ExpiresIn=600  # 10 minutes
    #         )

    #         return Response({"url": presigned_url})

    #     except Exception as e:
    #         return Response({"error": f"Failed to process document: {str(e)}"}, status=500)

    

    # @action(detail=False, methods=['get'], url_path='template-download')
    # def download_template(self, request):
    #     """
    #     Return the .docx file from R2 given a template_id and fill Acquirer (Buyer) data.
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
    #         # Retrieve the template file from R2
    #         s3_response = s3.get_object(
    #             Bucket=os.environ.get('CLOUDFLARE_R2_BUCKET'),
    #             Key=object_key,
    #         )
    #         file_stream = s3_response['Body'].read()

    #         # Load the template into python-docx
    #         doc = Document(io.BytesIO(file_stream))

    #         # Fill Acquirer (Buyer) data with funny Spanish names
    #         acquirer_data = {
    #             "[E.C_NOM_1]": "Juanito Pérez ",
    #             "[E.C_NOM_2]": "María López ",
    #             "[E.C_NACIONALIDAD_1]": "Mexicana",
    #             "[E.C_NACIONALIDAD_2]": "",
    #             "[E.C_TIP_DOC_1]": "DNI",
    #             "[E.C_TIP_DOC_2]": "",
    #             "[E.C_DOC_1]": "12345678",
    #             "[E.C_DOC_2]": "",
    #             "[E.C_OCUPACION_1]": "Panadero",
    #             "[E.C_OCUPACION_2]": "",
    #             "[E.C_ESTADO_CIVIL_1]": "Soltero",
    #             "[E.C_ESTADO_CIVIL_2]": "",
    #             "[E.C_DOMICILIO_1]": "Calle Falsa 123, Madrid",
    #             "[E.C_DOMICILIO_2]": "",
    #             "[E.C_CALIDAD_1]": "Comprador",
    #             "[E.C_CALIDAD_2]": "",
    #             "[E.C_IDE_1]": "",
    #             "[E.C_IDE_2]": "",
    #             "[E.C_FIRMA_1]": "Firma de Juanito",
    #             "[E.C_FIRMA_2]": "Firma de María",
    #             "[E.C_AMBOS_1]": "Ambos",
    #             "[E.C_AMBOS_2]": "Ambos",
    #         }

    #         # Replace placeholders in the document
    #         for paragraph in doc.paragraphs:
    #             for placeholder, value in acquirer_data.items():
    #                 if placeholder in paragraph.text:
    #                     paragraph.text = paragraph.text.replace(placeholder, value)

    #         # Save the modified document to a temporary file
    #         temp_file_path = f"/tmp/{template.filename}"
    #         doc.save(temp_file_path)

    #         # Return the modified document as a response
    #         with open(temp_file_path, "rb") as modified_file:
    #             response = HttpResponse(modified_file.read(), content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    #             response['Content-Disposition'] = f'attachment; filename="{template.filename}"'
    #             return response

    #     except Exception as e:
    #         return Response({"error": f"Failed to process document: {str(e)}"}, status=500)
    
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
