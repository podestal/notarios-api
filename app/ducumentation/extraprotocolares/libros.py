import os
import io
import traceback
from typing import Dict, Any, Optional

from django.db import connection
from django.http import HttpResponse, JsonResponse
from docxtpl import DocxTemplate

from ..shared.base_r2_documents import get_s3_client, BaseR2DocumentService
from ..utils import NumberToLetterConverter


class LibrosDocumentService(BaseR2DocumentService):
    """
    Service for Certificación de Apertura de Libros.

    - Templates expected in R2:
      - 'CERTIFICACION APERTURA DE LIBRO HORIZONTAL.docx'
      - 'CERTIFICACION APERTURA DE LIBRO VERTICAL.docx'
    - Output filename: '__LIBRO__{num_libro}-{anio_libro}.docx'
    """

    H_TEMPLATE = "CERTIFICACION APERTURA DE LIBRO HORIZONTAL.docx"
    V_TEMPLATE = "CERTIFICACION APERTURA DE LIBRO VERTICAL.docx"

    def __init__(self) -> None:
        self.letras = NumberToLetterConverter()
        # Default; can be overridden per-call based on orientation
        self.template_filename = self.V_TEMPLATE

    def retrieve_libro_document(self, num_libro: str, anio_libro: str, mode: str = "download") -> HttpResponse:
        try:
            if not num_libro or not anio_libro:
                return HttpResponse("Error: num_libro and anio_libro are required", status=400)

            filename = f"__LIBRO__{num_libro}-{anio_libro}.docx"

            if mode == "open":
                return self._create_response(None, filename, f"{num_libro}-{anio_libro}", mode)

            s3 = get_s3_client()
            object_key = self._object_key_for_document(filename)
            response = s3.get_object(Bucket=os.environ.get('CLOUDFLARE_R2_BUCKET'), Key=object_key)
            buffer = io.BytesIO(response['Body'].read())
            return self._create_response(buffer, filename, f"{num_libro}-{anio_libro}", mode)
        except Exception as e:
            if hasattr(e, 'response') and isinstance(getattr(e, 'response'), dict):
                if e.response.get('Error', {}).get('Code') == 'NoSuchKey':
                    return HttpResponse(f"Error: Document '{filename}' not found in R2.", status=404)
            traceback.print_exc()
            return HttpResponse(f"Error retrieving document: {e}", status=500)

    def generate_libro_document(self, num_libro: str, anio_libro: str, orientation: str = "V", mode: str = "download") -> HttpResponse:
        try:
            if not num_libro or not anio_libro:
                return self.json_error(400, "num_libro and anio_libro are required")

            filename = f"__LIBRO__{num_libro}-{anio_libro}.docx"
            if self._document_exists_in_r2(filename):
                return self.json_error(409, "Document already exists. Use action=retrieve to fetch it.", {
                    'num_libro': num_libro,
                    'anio_libro': anio_libro,
                    'filename': filename,
                })

            # Select template by orientation
            orientation_upper = (orientation or "V").upper()
            self.template_filename = self.H_TEMPLATE if orientation_upper.startswith("H") else self.V_TEMPLATE

            template_bytes = self._get_template_from_r2()
            if template_bytes is None:
                return self.json_error(404, f"Template '{self.template_filename}' not found in 'rodriguez-zea/plantillas/'.")

            libro_data = self._get_libro_data(num_libro, anio_libro)
            if not libro_data:
                return self.json_error(404, f"libros record {num_libro}-{anio_libro} not found")

            context: Dict[str, Any] = {}
            context.update(self._get_notary_data())
            context.update(libro_data)

            doc = DocxTemplate(io.BytesIO(template_bytes))
            doc.render(context)

            buffer = io.BytesIO()
            doc.save(buffer)
            self._save_document_to_r2(buffer, filename)
            return self._create_response(buffer, filename, f"{num_libro}-{anio_libro}", mode)
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

    def _create_response(self, buffer: Optional[io.BytesIO], filename: str, key_id: str, mode: str = "download") -> HttpResponse:
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
                    'filename': filename, 'libro': key_id,
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
            cursor.execute("SELECT CONCAT(nombre, ' ', apellido) AS notario, direccion, distrito FROM confinotario")
            row = cursor.fetchone()
            if row:
                return {
                    'NOTARIO': str(row[0]).upper() if row[0] else '',
                    'DIRECCION_NOTARIO': str(row[1]).upper() if row[1] else '',
                    'DISTRITO_NOTARIO': str(row[2]).upper() if row[2] else '',
                }
        return {'NOTARIO': '', 'DIRECCION_NOTARIO': '', 'DISTRITO_NOTARIO': ''}

    def _get_libro_data(self, num_libro: str, anio_libro: str) -> Dict[str, Any]:
        d: Dict[str, Any] = {}
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT 
                    l.numlibro,
                    UPPER(l.descritiplib) AS des_libro,
                    UPPER(l.empresa) AS nom_empresa,
                    l.ruc AS num_ruc,
                    l.folio AS num_hojas2,
                    tf.destipfol AS tip_folio,
                    l.numlibro AS num_crono,
                    CONCAT(l.apepat,' ',l.apemat,', ',l.prinom,' ', l.segnom) AS nombre_persona,
                    (CASE WHEN l.tipper='N' THEN l.ruc ELSE l.ruc END) AS documento,
                    (CASE WHEN l.tipper='N' THEN 'D.N.I.' ELSE 'R.U.C.' END) AS tipo_documento,
                    nl.idnlibro AS nro_libro,
                    nl.desnlibro AS des_nro_libro,
                    UPPER(l.solicitante) AS nombre_solici,
                    l.dni AS dni_solici_raw,
                    UPPER(l.comentario) AS comentario,
                    UPPER(l.comentario2) AS comentario2,
                    l.tipper,
                    l.fecing AS fecha_ingreso_libro,
                    tl.deslegal AS tipolegalizacion,
                    u.nomdis AS distrito,
                    u.nomprov AS provincia,
                    u.nomdpto AS departamento,
                    l.domfiscal,
                    l.ano AS anio_crono,
                    l.detalle,
                    l.numdoc_plantilla
                FROM libros l
                INNER JOIN tipofolio tf ON tf.idtipfol = l.idtipfol
                INNER JOIN nlibro nl ON nl.idnlibro = l.idnlibro
                INNER JOIN tipolegal tl ON tl.idlegal = l.idlegal
                LEFT JOIN cliente c ON c.idcliente = l.codclie
                LEFT JOIN ubigeo u ON u.coddis = c.idubigeo
                WHERE l.numlibro = %s AND l.ano = %s
                LIMIT 1
                """,
                [num_libro, anio_libro],
            )
            row = cursor.fetchone()
            if not row:
                return {}
            cols = [col[0] for col in cursor.description]
            d = dict(zip(cols, row))

        # Derived values
        d['des_nro_libro'] = 'APERTURA' if (d.get('des_nro_libro') or '').upper() == 'PRIMERO' else (d.get('des_nro_libro') or '')

        nombre_persona = (d.get('nombre_persona') or '').upper()
        nom_empresa = (d.get('nom_empresa') or '').upper()
        d['eval_persona'] = nom_empresa if nom_empresa else nombre_persona

        documento = d.get('documento') or ''
        if documento:
            d['num_doc'] = documento
            d['domicilio_fiscal'] = f"CON DOMICILIO EN {d.get('domfiscal','')}".strip()
            d['ubigeo'] = f"DEL DISTRITO DE {d.get('distrito','')} PROVINCIA DE {d.get('provincia','')} Y DEPARTAMENTO DE {d.get('departamento','')}"
        else:
            d['num_doc'] = ''
            d['domicilio_fiscal'] = ''
            d['ubigeo'] = ''

        dni_solici = d.get('dni_solici_raw') or ''
        d['dni_solici'] = f"IDENTIFICADO CON DNI N°{dni_solici}" if dni_solici else ''

        # Date strings
        fecha_ing = d.get('fecha_ingreso_libro')
        if fecha_ing:
            try:
                d['fec_letras_completa'] = self.letras.date_to_letters(fecha_ing).upper()
                d['fec_completa'] = (fecha_ing.strftime('%d/%m/%Y') if hasattr(fecha_ing, 'strftime') else str(fecha_ing))
            except Exception:
                d['fec_letras_completa'] = ''
                d['fec_completa'] = ''
        else:
            d['fec_letras_completa'] = ''
            d['fec_completa'] = ''

        # Aliases and computed text for template
        # ano_crono alias expected by template (without i)
        d['ano_crono'] = d.get('anio_crono')

        # Libro text blocks depending on type
        des_libro_upper = (d.get('des_libro') or '').upper()
        detalle = d.get('detalle') or ''
        nombre_solici = (d.get('nombre_solici') or '').upper()
        d['titulo_libro'] = 'Apertura de Cuaderno de Obra' if des_libro_upper == 'CUADERNO DE OBRA' else 'Apertura de Libro'
        d['tipo_libro'] = 'CUADERNO' if des_libro_upper == 'CUADERNO DE OBRA' else 'LIBRO'
        d['solicitud_libro'] = '' if des_libro_upper == 'CUADERNO DE OBRA' else 'a solicitud de '
        d['solicitud_obra'] = 'SOLICITADO POR' if des_libro_upper == 'CUADERNO DE OBRA' else ''
        d['obra'] = f'OBRA: "{detalle}"' if des_libro_upper == 'CUADERNO DE OBRA' and detalle else ''
        d['solicitante_libro'] = '' if des_libro_upper == 'CUADERNO DE OBRA' else (f"{nombre_solici}, {d.get('dni_solici','')}" if nombre_solici else '')
        d['solicitante_obra'] = (f"{nombre_solici}, {d.get('dni_solici','')}" if des_libro_upper == 'CUADERNO DE OBRA' and nombre_solici else '')
        d['calidad_obra'] = 'EN SU CALIDAD DE RESIDENTE' if des_libro_upper == 'CUADERNO DE OBRA' else ''

        # Tipo persona block
        tipper = (d.get('tipper') or '').upper()
        if tipper == 'J':
            # persona jurídica
            d['tipo_persona'] = 'CON RUC NUMERO'
        else:
            d['tipo_persona'] = 'CON DNI NUMERO'

        # Defaults for footer variables if template includes them
        d['usuario'] = d.get('usuario', '') or ''
        d['usuario_dni'] = d.get('usuario_dni', '') or ''

        # Composed blocks to avoid dangling commas in templates
        d['ubigeo_block'] = ' '.join([part for part in [d.get('domicilio_fiscal', ''), d.get('ubigeo', '')] if part]).strip()
        if des_libro_upper == 'CUADERNO DE OBRA':
            d['solicitud_libro_line'] = ''
        else:
            # For libro variant: "A SOLICITUD DE {nombre}, {dni}"
            prefix = (d.get('solicitud_libro') or '').strip()
            who = (f"{nombre_solici}, {d.get('dni_solici','')}" if nombre_solici else '').strip()
            d['solicitud_libro_line'] = f"{prefix} {who}".strip()

        return {k: (v.upper() if isinstance(v, str) else v) for k, v in d.items()} 