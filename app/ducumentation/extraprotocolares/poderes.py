import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
import os
import io
from typing import Dict, Any, List, Optional
from django.http import HttpResponse, JsonResponse
from django.db import connection
from docxtpl import DocxTemplate, RichText
import traceback
from ..extraprotocolares.permiso_viajes import get_s3_client
from ..utils import NumberToLetterConverter


class BasePoderDocumentService:
    """
    Base service with common logic for generating Poder documents.
    - Loads templates from R2 under rodriguez-zea/plantillas/
    - Saves generated docs to R2 under rodriguez-zea/documentos/
    - Supports 'generate' and 'retrieve' workflows
    """
    def __init__(self) -> None:
        self.letras = NumberToLetterConverter()
        self.template_filename: Optional[str] = None

    def retrieve_document(self, id_poder: int, filename: str, mode: str = "download") -> HttpResponse:
        try:
            if not filename:
                return HttpResponse("Error: filename is required to retrieve document", status=400)

            if mode == "open":
                return self._create_response(None, filename, id_poder, mode)

            s3 = get_s3_client()
            object_key = f"rodriguez-zea/documentos/{filename}"
            response = s3.get_object(Bucket=os.environ.get('CLOUDFLARE_R2_BUCKET'), Key=object_key)
            buffer = io.BytesIO(response['Body'].read())
            return self._create_response(buffer, filename, id_poder, mode)
        except ClientError as e:
            code = e.response.get('Error', {}).get('Code')
            if code == 'NoSuchKey':
                return HttpResponse(f"Error: Document '{filename}' not found in R2.", status=404)
            traceback.print_exc()
            return HttpResponse(f"Error retrieving document: {e}", status=500)
        except Exception as e:
            traceback.print_exc()
            return HttpResponse(f"Error retrieving document: {e}", status=500)

    def _get_template_from_r2(self) -> Optional[bytes]:
        if not self.template_filename:
            raise ValueError("template_filename must be set in child class")
        s3 = get_s3_client()
        object_key = f"rodriguez-zea/plantillas/{self.template_filename}"
        try:
            response = s3.get_object(Bucket=os.environ.get('CLOUDFLARE_R2_BUCKET'), Key=object_key)
            return response['Body'].read()
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                return None
            raise

    def _render_with_coloring(self, template_bytes: bytes, context: Dict[str, Any]) -> DocxTemplate:
        doc = DocxTemplate(io.BytesIO(template_bytes))
        colored: Dict[str, Any] = {}
        for key, value in context.items():
            if isinstance(value, list):
                new_list = []
                for item in value:
                    if isinstance(item, dict):
                        new_item = {k: RichText(str(v) if v is not None else '', color='#FF0000') for k, v in item.items()}
                        new_list.append(new_item)
                    else:
                        new_list.append(RichText(str(item) if item is not None else '', color='#FF0000'))
                colored[key] = new_list
            elif isinstance(value, dict):
                colored[key] = {k: RichText(str(v) if v is not None else '', color='#FF0000') for k, v in value.items()}
            else:
                colored[key] = RichText(str(value) if value is not None else '', color='#FF0000')
        doc.render(colored)
        return doc

    def _create_response(self, buffer: Optional[io.BytesIO], filename: str, id_poder: int, mode: str = "download") -> HttpResponse:
        if mode == "open":
            s3 = get_s3_client()
            object_key = f"rodriguez-zea/documentos/{filename}"
            try:
                url = s3.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': os.environ.get('CLOUDFLARE_R2_BUCKET'), 'Key': object_key},
                    ExpiresIn=3600,
                )
                response = JsonResponse({
                    'status': 'success', 'mode': 'open', 'url': url,
                    'filename': filename, 'id_poder': id_poder,
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

    def _save_document_to_r2(self, buffer: io.BytesIO, filename: str) -> None:
        s3 = get_s3_client()
        object_key = f"rodriguez-zea/documentos/{filename}"
        buffer.seek(0)
        s3.put_object(
            Bucket=os.environ.get('CLOUDFLARE_R2_BUCKET'),
            Key=object_key,
            Body=buffer.read(),
        )
        buffer.seek(0)


class PoderFueraDeRegistroDocumentService(BasePoderDocumentService):
    """
    Poder Fuera de Registro document service.
    Template expected name (in R2): 'PODER FUERA DE REGISTRO BASE.docx'
    Output filename format: '__PODER__{num_kardex}.docx'
    """
    def __init__(self) -> None:
        super().__init__()
        self.template_filename = "PODER FUERA DE REGISTRO BASE.docx"

    def generate_poder_fuera_registro_document(self, id_poder: int, mode: str = "download") -> HttpResponse:
        try:
            poder_data = self._get_poder_data(id_poder)
            if not poder_data.get('NUM_KARDEX'):
                return HttpResponse(f"Error: num_kardex is empty for id_poder {id_poder}", status=400)

            filename = f"__PODER__{poder_data['NUM_KARDEX']}.docx"

            template_bytes = self._get_template_from_r2()
            if template_bytes is None:
                return HttpResponse(
                    f"Error: Template '{self.template_filename}' not found in 'rodriguez-zea/plantillas/'.",
                    status=404,
                )

            context = self._build_context(id_poder, poder_data)
            doc = self._render_with_coloring(template_bytes, context)
            buffer = io.BytesIO()
            doc.save(buffer)
            self._save_document_to_r2(buffer, filename)
            return self._create_response(buffer, filename, id_poder, mode)
        except Exception as e:
            traceback.print_exc()
            return HttpResponse(f"Error generating document: {e}", status=500)

    def _get_poder_data(self, id_poder: int) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT 
                    id_poder,
                    num_kardex,
                    fec_ingreso,
                    fec_crono,
                    num_formu
                FROM ingreso_poderes
                WHERE id_poder = %s
                """,
                [id_poder],
            )
            row = cursor.fetchone()
            if row:
                data['ID_PODER'] = str(row[0])
                data['NUM_KARDEX'] = row[1]
                data['FEC_INGRESO'] = row[2]
                data['FEC_CRONO'] = row[3]
                data['NUM_FORMU'] = row[4]
                if data['NUM_KARDEX'] and len(data['NUM_KARDEX']) >= 5:
                    data['anio_crono'] = data['NUM_KARDEX'][:4]
                    data['num_crono3'] = data['NUM_KARDEX'][4:]
                else:
                    data['anio_crono'] = ''
                    data['num_crono3'] = ''
                if data['FEC_INGRESO']:
                    data['fecha_letras_viaext'] = self.letras.date_to_letters(data['FEC_INGRESO'])
                else:
                    data['fecha_letras_viaext'] = ''
            # poderes_fuerareg
            cursor.execute(
                """
                SELECT f_fecotor, f_fecvcto, f_plazopoder, f_solicita
                FROM poderes_fuerareg
                WHERE id_poder = %s
                """,
                [id_poder],
            )
            row2 = cursor.fetchone()
            if row2:
                data['FEC_OTORGAMIENTO'] = row2[0]
                data['FEC_VENCIMIENTO'] = row2[1]
                data['PLAZO_PODER'] = row2[2]
                data['solicita'] = row2[3] or ''
        return data

    def _get_participants_data(self, id_poder: int) -> Dict[str, Any]:
        """
        Build the 'E' structure consumed by the Jinja2 template. We support up to two principals and two witnesses.
        """
        E: Dict[str, Any] = {}
        with connection.cursor() as cursor:
            # Principals (poderdantes): take up to two by appearance order
            cursor.execute(
                """
                SELECT 
                    UPPER(CONCAT_WS(' ', c.prinom, c.segnom, c.apepat, c.apemat)) AS nom,
                    UPPER(n.descripcion) AS nacionalidad,
                    CASE WHEN c.sexo='F' THEN 'IDENTIFICADA CON' ELSE 'IDENTIFICADO CON' END AS ide,
                    UPPER(td.td_abrev) AS tipo_doc,
                    UPPER(c.numdoc) AS numdoc,
                    UPPER(te.desestcivil) AS estado_civil,
                    UPPER(COALESCE(c.detaprofesion, '')) AS ocupacion,
                    CONCAT('CON DOMICILIO EN ', UPPER(c.direccion), ' ',
                           UPPER(COALESCE(CONCAT('DEL DISTRITO DE ', u.nomdis, ', PROVINCIA DE ', u.nomprov, ', DEPARTAMENTO DE ', u.nomdpto), ''))) AS domicilio,
                    c.sexo
                FROM poderes_contratantes pc
                JOIN cliente c ON c.numdoc = pc.c_codcontrat
                JOIN tipodocumento td ON td.idtipdoc = c.idtipdoc
                JOIN tipoestacivil te ON te.idestcivil = c.idestcivil
                LEFT JOIN nacionalidades n ON n.idnacionalidad = c.nacionalidad
                LEFT JOIN ubigeo u ON u.coddis = c.idubigeo
                WHERE pc.id_poder = %s AND pc.c_condicontrat IN ('007','011','009')
                ORDER BY pc.id_poder, pc.c_codcontrat
                """,
                [id_poder],
            )
            principals = cursor.fetchall() or []
            for idx, p in enumerate(principals[:2], start=1):
                suffix = '' if idx == 1 else '_2'
                E[f'P_NOM{suffix}'] = p[0] or ''
                E[f'P_NACIONALIDAD{suffix}'] = p[1] or ''
                E[f'P_IDE{suffix}'] = p[2] or 'IDENTIFICADO CON'
                E[f'P_DOC{suffix}'] = f"{p[3] or ''} N° {p[4] or ''}"
                E[f'P_ESTADO_CIVIL{suffix}'] = p[5] or ''
                E[f'P_OCUPACION{suffix}'] = p[6] or ''
                E[f'P_DOMICILIO{suffix}'] = p[7] or ''
                E[f'P_SEXO{suffix}'] = p[8] or 'M'

            # Witnesses a ruego (testigos): up to two
            cursor.execute(
                """
                SELECT 
                    UPPER(CONCAT_WS(' ', c.prinom, c.segnom, c.apepat, c.apemat)) AS nom,
                    UPPER(n.descripcion) AS nacionalidad,
                    CASE WHEN c.sexo='F' THEN 'IDENTIFICADA CON' ELSE 'IDENTIFICADO CON' END AS ide,
                    UPPER(td.td_abrev) AS tipo_doc,
                    UPPER(c.numdoc) AS numdoc,
                    UPPER(te.desestcivil) AS estado_civil,
                    UPPER(COALESCE(c.detaprofesion, '')) AS ocupacion,
                    CONCAT('CON DOMICILIO EN ', UPPER(c.direccion), ' ',
                           UPPER(COALESCE(CONCAT('DEL DISTRITO DE ', u.nomdis, ', PROVINCIA DE ', u.nomprov, ', DEPARTAMENTO DE ', u.nomdpto), ''))) AS domicilio,
                    c.sexo
                FROM poderes_contratantes pc
                JOIN cliente c ON c.numdoc = pc.c_codcontrat
                JOIN tipodocumento td ON td.idtipdoc = c.idtipdoc
                JOIN tipoestacivil te ON te.idestcivil = c.idestcivil
                LEFT JOIN nacionalidades n ON n.idnacionalidad = c.nacionalidad
                LEFT JOIN ubigeo u ON u.coddis = c.idubigeo
                WHERE pc.id_poder = %s AND pc.c_condicontrat = '008'
                ORDER BY pc.id_poder, pc.c_codcontrat
                """,
                [id_poder],
            )
            witnesses = cursor.fetchall() or []
            for idx, w in enumerate(witnesses[:2], start=1):
                suffix = '' if idx == 1 else '_2'
                E[f'T_INTERVIENE{suffix}'] = 'INTERVIENE:'
                E[f'T_NOM{suffix}'] = w[0] or ''
                E[f'T_NACIONALIDAD{suffix}'] = w[1] or ''
                E[f'T_IDE{suffix}'] = w[2] or 'IDENTIFICADO CON'
                E[f'T_DOC{suffix}'] = f"{w[3] or ''} N° {w[4] or ''}"
                E[f'T_ESTADO_CIVIL{suffix}'] = w[5] or ''
                E[f'T_OCUPACION{suffix}'] = w[6] or ''
                E[f'T_DOMICILIO{suffix}'] = w[7] or ''
                E[f'T_CALIDAD{suffix}'] = 'QUIEN INTERVIENE EN CALIDAD DE TESTIGO A RUEGO'

            # Apoderado (representative) summary line used in text
            cursor.execute(
                """
                SELECT UPPER(CONCAT_WS(' ', c.prinom, c.segnom, c.apepat, c.apemat)) AS nom,
                       UPPER(td.td_abrev) AS tipo_doc,
                       UPPER(c.numdoc) AS numdoc,
                       c.sexo
                FROM poderes_contratantes pc
                JOIN cliente c ON c.numdoc = pc.c_codcontrat
                JOIN tipodocumento td ON td.idtipdoc = c.idtipdoc
                WHERE pc.id_poder = %s AND pc.c_condicontrat = '006'
                ORDER BY pc.id_poder, pc.c_codcontrat
                LIMIT 1
                """,
                [id_poder],
            )
            ap = cursor.fetchone()
            if ap:
                ap_text = f"{ap[0]} {'IDENTIFICADA' if (ap[3] or 'M')=='F' else 'IDENTIFICADO'} CON {ap[1]} N° {ap[2]}"
                E['apoderadoPoder'] = ap_text
            else:
                E['apoderadoPoder'] = ''

        # Pluralization helpers derived from number of principals
        num_principals = 0
        if 'P_NOM' in E and E['P_NOM']:
            num_principals += 1
        if 'P_NOM_2' in E and E['P_NOM_2']:
            num_principals += 1
        if num_principals > 1:
            return {
                **E,
                'P_EL': 'Los', 'P_S': 's', 'P_ES_SON': 'son', 'P_ES': 'es',
                'P_O_ARON': 'aron', 'P_N': 'n', 'P_DEL_LOS': 'de los', 'P_A_LOS': 'a los'
            }
        else:
            # Use first principal's sex if available
            sex = E.get('P_SEXO', 'M')
            if sex == 'F':
                return {
                    **E,
                    'P_EL': 'La', 'P_S': '', 'P_ES_SON': 'es', 'P_ES': '',
                    'P_O_ARON': 'ó', 'P_N': '', 'P_DEL_LOS': 'de la', 'P_A_LOS': 'a la'
                }
            return {
                **E,
                'P_EL': 'El', 'P_S': '', 'P_ES_SON': '', 'P_ES': '',
                'P_O_ARON': 'ó', 'P_N': '', 'P_DEL_LOS': 'del', 'P_A_LOS': 'al'
            }

    def _get_user_data(self, usuario_imprime: Optional[str]) -> Dict[str, str]:
        if not usuario_imprime:
            return {'usuario': '?', 'dni_usuario': '?'}
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
                return {'usuario': row[0] or '?', 'dni_usuario': row[1] or '?'}
            return {'usuario': '?', 'dni_usuario': '?'}

    def _build_context(self, id_poder: int, poder_data: Dict[str, Any]) -> Dict[str, Any]:
        context: Dict[str, Any] = {}
        # Map top-level vars expected by the template
        context.update({
            'aniocrono': poder_data.get('anio_crono', ''),
            'numcrono3': poder_data.get('num_crono3', ''),
            'fecha_letras_viaext': poder_data.get('fecha_letras_viaext', ''),
            'solicita': poder_data.get('solicita', ''),
        })
        # Pull user data if available (optional: you can adapt who is usuario_imprime)
        # Here we attempt to get from last editor; if not applicable, leave blanks
        context.update(self._get_user_data(None))
        # Participants block "E"
        E = self._get_participants_data(id_poder)
        context['E'] = E
        # Pronoun helpers also placed at top level for convenience
        for k in ['P_EL', 'P_S', 'P_ES_SON', 'P_ES', 'P_O_ARON', 'P_N', 'P_DEL_LOS', 'P_A_LOS', 'apoderadoPoder']:
            context[k] = E.get(k, '')
        return context


class PoderONPDocumentService(BasePoderDocumentService):
    def __init__(self) -> None:
        super().__init__()
        self.template_filename = "PODER ONP.docx"


class PoderEssaludDocumentService(BasePoderDocumentService):
    def __init__(self) -> None:
        super().__init__()
        self.template_filename = "PODER ESSALUD.docx" 