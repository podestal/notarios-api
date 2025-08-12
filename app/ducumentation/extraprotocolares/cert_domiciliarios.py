import os
import io
import traceback
from typing import Dict, Any, Optional

from django.db import connection
from django.http import HttpResponse, JsonResponse
from docxtpl import DocxTemplate

from ..shared.base_r2_documents import get_s3_client, BaseR2DocumentService
from ..utils import NumberToLetterConverter


class CertDomiciliariosDocumentService(BaseR2DocumentService):
    """
    Service to generate and retrieve Certificación/Constatación Domiciliaria documents.

    - Template expected in R2: 'CERTIFICADO DOMICILIARIO BASE.docx'
    - Output filename: '__CDOM__{RIGHT6(num_certificado)}-{LEFT4(num_certificado)}.docx'
    - Stored under: rodriguez-zea/documentos/
    """

    def __init__(self) -> None:
        self.letras = NumberToLetterConverter()
        self.template_filename = "CERTIFICADO DOMICILIARIO BASE.docx"

    def retrieve_cdom_document(self, num_certificado: str, mode: str = "download") -> HttpResponse:
        try:
            if not num_certificado:
                return HttpResponse("Error: num_certificado is required to retrieve document", status=400)

            formatted = self._format_num_certificado(num_certificado)
            filename = f"__CDOM__{formatted}.docx"

            if mode == "open":
                return self._create_response(None, filename, formatted, mode)

            s3 = get_s3_client()
            object_key = self._object_key_for_document(filename)
            response = s3.get_object(Bucket=os.environ.get('CLOUDFLARE_R2_BUCKET'), Key=object_key)
            buffer = io.BytesIO(response['Body'].read())
            return self._create_response(buffer, filename, formatted, mode)
        except Exception as e:
            if hasattr(e, 'response') and isinstance(getattr(e, 'response'), dict):
                if e.response.get('Error', {}).get('Code') == 'NoSuchKey':
                    return HttpResponse(f"Error: Document '{filename}' not found in R2.", status=404)
            traceback.print_exc()
            return HttpResponse(f"Error retrieving document: {e}", status=500)

    def generate_cdom_document(self, num_certificado: str, mode: str = "download") -> HttpResponse:
        try:
            if not num_certificado:
                return JsonResponse({'status': 'error', 'message': 'num_certificado is required'}, status=400)

            formatted = self._format_num_certificado(num_certificado)
            filename = f"__CDOM__{formatted}.docx"

            if self._document_exists_in_r2(filename):
                return self.json_error(409, "Document already exists. Use action=retrieve to fetch it.", {
                    'num_certificado': num_certificado,
                    'filename': filename,
                })

            template_bytes = self._get_template_from_r2()
            if template_bytes is None:
                return self.json_error(404, f"Template '{self.template_filename}' not found in 'rodriguez-zea/plantillas/'.")

            cert_data = self._get_cert_data(num_certificado)
            if not cert_data:
                return self.json_error(404, f"cert_domiciliario record with num_certificado {num_certificado} not found")

            # Build context
            context: Dict[str, Any] = {}
            context.update(cert_data)
            context.update(self._get_notary_data())

            # Aliases used by templates (lowercase, case-sensitive)
            context['numcrono2'] = formatted
            context['P_NOM'] = context.get('NOMBRE_SOLIC', '')
            # Gendered identity strings
            sex = (context.get('SEXO', '') or 'M').upper()
            tip_doc = context.get('TIP_DOC', '')
            num_doc = context.get('NUM_DOC', '')
            context['P_DOC'] = f"{'IDENTIFICADA' if sex == 'F' else 'IDENTIFICADO'} CON {tip_doc} N°"
            context['DOC'] = f"{tip_doc} N°"
            context['P_IDE'] = num_doc
            # Domicile text
            domicilio = context.get('DIRECCION', '')
            distrito_texto = context.get('DISTRITO_TEXTO', '')
            context['P_DOMICILIO'] = f"CON DOMICILIO EN {domicilio} {distrito_texto}".strip()
            # Civil status, nationality, occupation
            est_civil = context.get('E_CIVIL', '') or ''
            nacionalidad = context.get('NACIONALIDAD', '') or ''
            if est_civil:
                context['P_ESTADO_CIVIL'] = est_civil[:-1] + ('A' if sex == 'F' else 'O') if len(est_civil) > 0 else est_civil
            else:
                context['P_ESTADO_CIVIL'] = ''
            if nacionalidad:
                context['P_NACIONALIDAD'] = nacionalidad[:-1] + ('A' if sex == 'F' else 'O') if len(nacionalidad) > 0 else nacionalidad
            else:
                context['P_NACIONALIDAD'] = ''
            context['P_OCUPACION'] = context.get('PROFESION', '')

            # Testigo line (optional)
            if context.get('NOM_TESTIGO'):
                context['DATOS_TESTIGO'] = (
                    f"INTERVIENE EN CALIDAD DE TESTIGO A RUEGO :{context.get('NOM_TESTIGO', '')}, CON "
                    f"{context.get('TIPDOC_TESTIGO', '')} NUMERO {context.get('NUMDOC_TESTIGO', '')} "
                    f"{context.get('UBIGEO_TESTIGO', '')}"
                )
            else:
                context['DATOS_TESTIGO'] = ''

            # Render and save
            doc = DocxTemplate(io.BytesIO(template_bytes))
            doc.render(context)

            buffer = io.BytesIO()
            doc.save(buffer)
            self._save_document_to_r2(buffer, filename)
            return self._create_response(buffer, filename, formatted, mode)
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
                    'filename': filename, 'num_certificado': key_id,
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

    def _format_num_certificado(self, raw: Optional[str]) -> str:
        if not raw or len(raw) < 6:
            return raw or ''
        return f"{raw[-6:]}-{raw[:4]}"

    def _get_notary_data(self) -> Dict[str, str]:
        with connection.cursor() as cursor:
            cursor.execute("SELECT CONCAT(nombre, ' ', apellido) AS notario, direccion, distrito FROM confinotario")
            row = cursor.fetchone()
            if row:
                return {
                    'NOTARIO': str(row[0]).upper() if row[0] else '',
                    'DIRECCION_NOTARIO': str(row[1]).upper() if row[1] else '',
                    'UBIGEO_NOTARIO': str(row[2]).upper() if row[2] else '',
                }
        return {'NOTARIO': '', 'DIRECCION_NOTARIO': '', 'UBIGEO_NOTARIO': ''}

    def _get_cert_data(self, num_certificado: str) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT 
                    UPPER(cd.num_certificado) AS NUM_CERTI,
                    cd.fec_ingreso AS FEC_INGRESO,
                    UPPER(cd.num_formu) AS NUM_FORMU,
                    CONCAT(c.prinom,' ',c.segnom,' ',c.apepat,' ',c.apemat) AS NOMBRE_SOLIC,
                    UPPER(td.td_abrev) AS TIP_DOC,
                    UPPER(cd.numdoc_solic) AS NUM_DOC,
                    UPPER(cd.domic_solic) AS DIRECCION,
                    UPPER(cd.motivo_solic) AS MOTIVO,
                    UPPER(u.nomdis) AS NOM_DIST,
                    UPPER(cd.texto_cuerpo) AS OBSERVACION,
                    CASE WHEN u.coddis='070101' THEN 'DISTRITO DE CALLAO , PROVINCIA CONSTITUCIONAL DEL CALLAO'
                         ELSE CONCAT('DISTRITO DE ',u.nomdis, ', PROVINCIA DE ',u.nomprov,', DEPARTAMENTO DE ',u.nomdpto) END AS UBIGEO,
                    cd.IDESTCIVIL AS E_CIVIL,
                    cd.profesionc AS IDPROFESION,
                    cd.detprofesionc AS PROFESION,
                    CONCAT(' DEL DISTRITO DE ',u.nomdis,' PROVINCIA DE ',u.nomprov,' Y DEPARTAMENTO DE ',u.nomdpto) AS DISTRITO_TEXTO,
                    cd.id_domiciliario,
                    cd.fecha_ocupa,
                    cd.declara_ser,
                    cd.propietario,
                    cd.recibido,
                    cd.numero_recibo,
                    cd.mes_facturado,
                    cd.recibo_empresa,
                    c.sexo AS SEXO,
                    n.descripcion AS NACIONALIDAD,
                    -- Testigo fields (optional) via correlated selects
                    cd.nom_testigo AS NOM_TESTIGO,
                    (SELECT UPPER(td2.td_abrev) FROM tipodocumento td2 WHERE td2.codtipdoc = cd.tdoc_testigo) AS TIPDOC_TESTIGO,
                    cd.ndocu_testigo AS NUMDOC_TESTIGO,
                    CASE WHEN u.coddis='070101' THEN 'DISTRITO DE CALLAO , PROVINCIA CONSTITUCIONAL DEL CALLAO'
                         ELSE CONCAT('DISTRITO DE ',u.nomdis, ', PROVINCIA DE ',u.nomprov,', DEPARTAMENTO DE ',u.nomdpto) END AS UBIGEO_TESTIGO
                FROM cert_domiciliario cd
                INNER JOIN tipodocumento td ON cd.tipdoc_solic = td.codtipdoc
                INNER JOIN cliente c ON cd.numdoc_solic = c.numdoc
                LEFT JOIN ubigeo u ON u.coddis = cd.distrito_solic
                INNER JOIN nacionalidades n ON n.idnacionalidad = c.nacionalidad
                WHERE cd.num_certificado = %s
                LIMIT 1
                """,
                [num_certificado],
            )
            row = cursor.fetchone()
            if not row:
                return {}
            cols = [col[0] for col in cursor.description]
            data = {k: (str(v).upper() if isinstance(v, str) and v is not None else v) for k, v in dict(zip(cols, row)).items()}

            # Additional date formatting
            fec_ingreso = data.get('FEC_INGRESO')
            if fec_ingreso:
                try:
                    data['FECHA_INGRESO_LETRAS'] = self.letras.date_to_letters(fec_ingreso).upper()
                except Exception:
                    data['FECHA_INGRESO_LETRAS'] = ''
            else:
                data['FECHA_INGRESO_LETRAS'] = ''
        return data 