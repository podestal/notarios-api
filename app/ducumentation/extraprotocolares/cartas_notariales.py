import os
import io
import traceback
from typing import Dict, Any, Optional

from django.db import connection
from django.http import HttpResponse, JsonResponse
from docxtpl import DocxTemplate

from ..shared.base_r2_documents import get_s3_client, BaseR2DocumentService
from ..utils import NumberToLetterConverter


class CartasNotarialesDocumentService(BaseR2DocumentService):
    """
    Service for generating and retrieving Certificación de Entrega de Carta Notarial documents.

    - Template expected in R2: 'CERTIFICACION ENTREGA DE CARTA NOTARIAL.docx'
    - Output filename: '__CARTA__{num_carta}.docx'
    - Stores under: rodriguez-zea/documentos/
    """

    def __init__(self) -> None:
        self.letras = NumberToLetterConverter()
        self.template_filename = "CERTIFICACION ENTREGA DE CARTA NOTARIAL.docx"

    def retrieve_carta_document(self, num_carta: str, mode: str = "download") -> HttpResponse:
        try:
            if not num_carta:
                return self.json_error(400, "num_carta is required to retrieve document")

            formatted_num_carta = self._format_num_carta(num_carta)
            filename = f"__CARTA__{formatted_num_carta}.docx"

            if mode == "open":
                return self._create_response(None, filename, num_carta, mode)

            s3 = get_s3_client()
            object_key = self._object_key_for_document(filename)
            response = s3.get_object(Bucket=os.environ.get('CLOUDFLARE_R2_BUCKET'), Key=object_key)
            buffer = io.BytesIO(response['Body'].read())
            return self._create_response(buffer, filename, num_carta, mode)
        except Exception as e:
            # Map not-found to 404 JSON
            if hasattr(e, 'response') and isinstance(getattr(e, 'response'), dict):
                code = e.response.get('Error', {}).get('Code')
                if code == 'NoSuchKey':
                    return self.json_error(404, "Document not found in R2. Generate it first.", {
                        'num_carta': num_carta,
                        'filename': f"__CARTA__{num_carta}.docx",
                    })
            traceback.print_exc()
            return self.json_error(500, f"Error retrieving document: {e}")

    def generate_carta_document(self, num_carta: str, mode: str = "download") -> HttpResponse:
        try:
            if not num_carta:
                return self.json_error(400, "num_carta is required to generate document")

            formatted_num_carta = self._format_num_carta(num_carta)
            filename = f"__CARTA__{formatted_num_carta}.docx"
            if self._document_exists_in_r2(filename):
                return self.json_error(409, "Document already exists. Use action=retrieve to fetch it.", {
                    'num_carta': formatted_num_carta,
                    'filename': filename,
                })

            template_bytes = self._get_template_from_r2()
            if template_bytes is None:
                return self.json_error(404, f"Template '{self.template_filename}' not found in 'rodriguez-zea/plantillas/'.")

            carta_data = self._get_carta_data(num_carta)
            if not carta_data:
                return self.json_error(404, f"ingreso_cartas record with num_carta {num_carta} not found")

            context: Dict[str, Any] = {}
            context.update(carta_data)
            context.update(self._get_notary_data())

            # Aliases to match template variable names (docxtpl is case-sensitive)
            context['contenido_carta'] = context.get('CONTENIDO_CARTA', '')
            context['fec_ingreso'] = context.get('FECHA_INGRESO_LETRAS', '')
            context['num_carta'] = context.get('NUM_CARTA_FMT', '')
            # Legacy placeholders from PHP template
            context['USUARIO'] = context.get('USUARIO', '') or ''
            context['USUARIO_DNI'] = context.get('USUARIO_DNI', '') or ''
            context['COMPROBANTE'] = context.get('COMPROBANTE', '') or 'sin'

            doc = DocxTemplate(io.BytesIO(template_bytes))
            doc.render(context)

            buffer = io.BytesIO()
            doc.save(buffer)
            self._save_document_to_r2(buffer, filename)
            return self._create_response(buffer, filename, num_carta, mode)
        except Exception as e:
            traceback.print_exc()
            return self.json_error(500, f"Error generating document: {e}")

    def _get_template_from_r2(self) -> Optional[bytes]:
        s3 = get_s3_client()
        object_key = self._object_key_for_template(self.template_filename)
        try:
            response = s3.get_object(Bucket=os.environ.get('CLOUDFLARE_R2_BUCKET'), Key=object_key)
            return response['Body'].read()
        except Exception:
            return None

    def _save_document_to_r2(self, buffer: io.BytesIO, filename: str) -> None:
        s3 = get_s3_client()
        object_key = self._object_key_for_document(filename)
        buffer.seek(0)
        s3.put_object(
            Bucket=os.environ.get('CLOUDFLARE_R2_BUCKET'),
            Key=object_key,
            Body=buffer.read(),
        )
        buffer.seek(0)

    def _create_response(self, buffer: Optional[io.BytesIO], filename: str, num_carta: str, mode: str = "download") -> HttpResponse:
        if mode == "open":
            s3 = get_s3_client()
            object_key = self._object_key_for_document(filename)
            try:
                url = s3.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': os.environ.get('CLOUDFLARE_R2_BUCKET'), 'Key': object_key},
                    ExpiresIn=3600,
                )
                response = JsonResponse({
                    'status': 'success', 'mode': 'open', 'url': url,
                    'filename': filename, 'num_carta': num_carta,
                    'message': 'Document is ready to be opened.'
                })
                response['Access-Control-Allow-Origin'] = '*'
                return response
            except Exception as e:
                return HttpResponse(f"Error generating pre-signed URL: {e}", status=500)
        if buffer is None:
            return HttpResponse("Error: Document buffer is missing for download mode.", status=500)
        buffer.seek(0)
        response = HttpResponse(buffer.read(), content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        response['Content-Length'] = str(buffer.getbuffer().nbytes)
        response['Access-Control-Allow-Origin'] = '*'
        return response

    def _get_notary_data(self) -> Dict[str, str]:
        with connection.cursor() as cursor:
            cursor.execute("SELECT CONCAT(nombre, ' ', apellido) AS notario FROM confinotario")
            row = cursor.fetchone()
            if row:
                return {'NOTARIO': str(row[0]).upper() if row[0] else ''}
        return {'NOTARIO': ''}

    def _get_user_data(self, usuario_imprime: Optional[str]) -> Dict[str, str]:
        if not usuario_imprime:
            return {'USUARIO': '?', 'USUARIO_DNI': '?'}
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT loginusuario, dni FROM usuarios
                WHERE CONCAT(apepat,' ',prinom) = %s
                """,
                [usuario_imprime],
            )
            row = cursor.fetchone()
            if row:
                return {'USUARIO': row[0] or '?', 'USUARIO_DNI': row[1] or '?'}
            return {'USUARIO': '?', 'USUARIO_DNI': '?'}

    def _format_num_carta(self, raw: Optional[str]) -> str:
        if not raw or len(raw) < 6:
            return raw or ''
        # Format as NNNNNN-YYYY like PHP CONCAT(RIGHT(6), '-', LEFT(4))
        return f"{raw[-6:]}-{raw[:4]}"

    def _get_carta_data(self, num_carta: str) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT 
                    num_carta,
                    conte_carta,
                    STR_TO_DATE(fec_entrega, '%%d/%%m/%%Y') AS fecha_diligencia,
                    hora_entrega,
                    STR_TO_DATE(fec_ingreso, '%%d/%%m/%%Y') AS fecha_ingreso
                FROM ingreso_cartas
                WHERE num_carta = %s
                """,
                [num_carta],
            )
            row = cursor.fetchone()
            if not row:
                return {}
            raw_num_carta = row[0]
            contenido = row[1] or ''
            fecha_diligencia = row[2]
            hora_entrega = row[3] or ''
            fecha_ingreso = row[4]

            # Prepare replacements in contenido (00/00/0000 -> dd/mm/YYYY, 00:00 -> hora_entrega)
            fecha_diligencia_ddmmyyyy = fecha_diligencia.strftime('%d/%m/%Y') if fecha_diligencia else ''
            contenido_replaced = contenido.replace('00/00/0000', fecha_diligencia_ddmmyyyy).replace('00:00', hora_entrega)

            data.update({
                'NUM_CARTA': raw_num_carta or '',
                'NUM_CARTA_FMT': self._format_num_carta(raw_num_carta),
                'CONTENIDO_CARTA': contenido_replaced,
                'FECHA_DILIGENCIA': fecha_diligencia_ddmmyyyy,
                'FECHA_DILIGENCIA_LETRAS': self.letras.date_to_letters(fecha_diligencia).upper() if fecha_diligencia else '',
                'HORA_DILIGENCIA': hora_entrega,
                'FECHA_INGRESO_LETRAS': self.letras.date_to_letters(fecha_ingreso).lower() if fecha_ingreso else '',
            })
        return data 