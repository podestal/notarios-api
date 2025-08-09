import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from django.conf import settings
import os
import io
from decimal import Decimal
from typing import Dict, Any, List
from django.http import HttpResponse, JsonResponse
from notaria.models import TplTemplate, Cliente, Tipodocumento, Nacionalidades, Tipoestacivil, Profesiones, Ubigeo, PermiViaje, ViajeContratantes
from .utils import NumberToLetterConverter
import time
from django.db import connection
import re
from docxtpl import DocxTemplate, RichText
import traceback

_s3_client = None


def get_s3_client():
    """
    Get a cached S3 client for R2 operations
    """
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client(
            's3',
            endpoint_url=os.environ.get('CLOUDFLARE_R2_ENDPOINT'),
            aws_access_key_id=os.environ.get('CLOUDFLARE_R2_ACCESS_KEY'),
            aws_secret_access_key=os.environ.get('CLOUDFLARE_R2_SECRET_KEY'),
            config=Config(signature_version='s3v4'),
            region_name='auto',
        )
    return _s3_client


class BasePermisoViajeDocumentService:
    """
    Base service with common logic for generating Permiso Viaje documents.
    """
    def __init__(self):
        self.letras = NumberToLetterConverter()
        self.template_filename = None  # Must be set by child classes
    
    def retrieve_document(self, id_permiviaje: int, mode: str = "download") -> HttpResponse:
        try:
            permiviaje = PermiViaje.objects.get(id_viaje=id_permiviaje)
            num_kardex = permiviaje.num_kardex
            if not num_kardex:
                return HttpResponse(f"Error: num_kardex is empty for PermiViaje id {id_permiviaje}", status=400)

            filename = f"__PROY__{num_kardex}.docx"
            
            if mode == "open":
                # For 'open' mode, we only need to generate the URL, not download the file content here.
                return self._create_response(None, filename, id_permiviaje, mode)

            # For 'download' mode, fetch the document body.
            s3 = get_s3_client()
            object_key = f"rodriguez-zea/documentos/{filename}"
            response = s3.get_object(Bucket=os.environ.get('CLOUDFLARE_R2_BUCKET'), Key=object_key)
            buffer = io.BytesIO(response['Body'].read())
            
            return self._create_response(buffer, filename, id_permiviaje, mode)

        except PermiViaje.DoesNotExist:
            return HttpResponse(f"Error: PermiViaje with id {id_permiviaje} not found", status=404)
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                return HttpResponse(f"Error: Document '{filename}' not found in R2.", status=404)
            else:
                traceback.print_exc()
                return HttpResponse(f"Error retrieving document: {e}", status=500)
        except Exception as e:
            traceback.print_exc()
            return HttpResponse(f"Error retrieving document: {e}", status=500)

    def _get_template_from_r2(self) -> bytes:
        if not self.template_filename:
            raise ValueError("template_filename must be set in the child service class.")
        s3 = get_s3_client()
        object_key = f"rodriguez-zea/plantillas/{self.template_filename}"
        try:
            response = s3.get_object(Bucket=os.environ.get('CLOUDFLARE_R2_BUCKET'), Key=object_key)
            return response['Body'].read()
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchKey':
                return None
            else:
                raise
        except Exception as e:
            raise

    def _get_licencia_data(self, fecha_ingreso: str) -> Dict[str, str]:
        if not fecha_ingreso:
            return {'licencia': ''}
        with connection.cursor() as cursor:
            cursor.execute("SELECT notario, resolucion, (SELECT CONCAT(nombre, ' ', apellido) FROM confinotario LIMIT 1) as notario_principal, (SELECT direccion FROM confinotario LIMIT 1) as direccion_notario FROM confinotario WHERE %s BETWEEN fechainicio AND fechafin", [fecha_ingreso])
            row = cursor.fetchone()
            if row:
                return {'licencia': f'POR LICENCIA DE LA NOTARIA {row[2]} FIRMA EL NOTARIO {row[0]} SEGUN RESOLUCION N° {row[1]}'}
            else:
                cursor.execute("SELECT CONCAT(nombre, ' ', apellido) as notario, direccion FROM confinotario LIMIT 1")
                notary_info = cursor.fetchone()
                if notary_info:
                    return {'licencia': f'YO {notary_info[0]} ABOGADO - NOTARIO DE PUNO CON OFICIO NOTARIAL EN {notary_info[1]}'}
        return {'licencia': ''}

    def _get_notary_data(self) -> Dict[str, str]:
        with connection.cursor() as cursor:
            cursor.execute("SELECT nombre AS nombres, apellido AS apellidos, CONCAT(nombre,' ',apellido) AS notario, ruc AS ruc_notario, distrito AS distrito_notario FROM confinotario")
            row = cursor.fetchone()
            if row:
                columns = [col[0] for col in cursor.description]
                notary_data = dict(zip(columns, row))
                final_data = {}
                for key, value in notary_data.items():
                    if key == 'ruc_notario' and value:
                        final_data[f'LETRA_{key.upper()}'] = self.letras.number_to_letters(value)
                    final_data[key.upper().strip()] = str(value).upper() if value is not None else '?'
                return final_data
            return {'NOMBRES': '?','APELLIDOS': '?','NOTARIO': '?','RUC_NOTARIO': '?','DISTRITO_NOTARIO': '?','LETRA_RUC_NOTARIO': ''}

    def _get_viaje_data(self, id_permiviaje: int) -> Dict[str, str]:
        try:
            viaje = PermiViaje.objects.get(id_viaje=id_permiviaje)
            data = {
                'ID_VIAJE': str(viaje.id_viaje), 'KARDEX': f"{viaje.num_kardex[4:]}-{viaje.num_kardex[:4]}" if viaje.num_kardex and len(viaje.num_kardex) > 4 else viaje.num_kardex or '?',
                'ASUNTO': viaje.asunto or '?', 'FECHA_INGRESO': viaje.fec_ingreso.strftime('%d/%m/%Y') if viaje.fec_ingreso else '?',
                'FECHA_INGRESO_RAW': viaje.fec_ingreso.strftime('%Y-%m-%d') if viaje.fec_ingreso else None, 'NOMBRE_RECEPCIONISTA': viaje.nom_recep or '?',
                'HORA_RECEPCION': viaje.hora_recep or '?', 'REFERENCIA': viaje.referencia or '?', 'COMUNICARSE': viaje.nom_comu or '?', 'COMUNICARSE_EMAIL': viaje.email_comu or '?',
                'DOCUMENTO': viaje.documento or '?', 'NUMERO_CRONOLOGICO': viaje.num_crono or '?', 'FECHA_CRONOLOGICO': viaje.fecha_crono.strftime('%d/%m/%Y') if viaje.fecha_crono else '?',
                'NUMERO_FORMULARIO': viaje.num_formu or '?', 'DESTINO': viaje.lugar_formu or '?', 'OBSERVACION': viaje.observacion or '?', 'SWT_EST': viaje.swt_est or '?',
                'PARTIDA_E': viaje.partida_e or '?', 'SEDE_REGIS': viaje.sede_regis or '?', 'REFER': viaje.referencia or '?', 'VIA_TRANS': getattr(viaje, 'via', '?') or '?',
                'FEC_DESDE': self.letras.date_to_letters(viaje.fecha_desde) if hasattr(viaje, 'fecha_desde') and viaje.fecha_desde else '?',
                'FEC_HASTA': self.letras.date_to_letters(viaje.fecha_hasta) if hasattr(viaje, 'fecha_hasta') and viaje.fecha_hasta else '?'
            }
            if viaje.fec_ingreso: data['LETRA_FECHA_INGRESO'] = self.letras.date_to_letters(viaje.fec_ingreso)
            return data
        except PermiViaje.DoesNotExist: return {}

    def _get_user_data(self, usuario_imprime: str = None) -> Dict[str, str]:
        if not usuario_imprime: return {'USUARIO': '?','USUARIO_DNI': '?'}
        with connection.cursor() as cursor:
            cursor.execute("SELECT loginusuario, dni FROM usuarios WHERE CONCAT(apepat,' ',prinom) = %s", [usuario_imprime])
            row = cursor.fetchone()
            return {'USUARIO': row[0] or '?','USUARIO_DNI': row[1] or '?'} if row else {'USUARIO': '?','USUARIO_DNI': '?'}

    def _process_document(self, template_bytes: bytes, data: Dict[str, Any]) -> DocxTemplate:
        """
        Renders the document using docxtpl with Jinja2 syntax.
        """
        doc = DocxTemplate(io.BytesIO(template_bytes))
        
        # Temporarily disabling RichText to debug file corruption issue.
        # This will render the document without red color.
        context = {}
        for key, value in data.items():
            if isinstance(value, list):
                new_list = []
                for item in value:
                    if isinstance(item, dict):
                        new_item = {k: RichText(str(v) if v is not None else '', color='#FF0000') for k, v in item.items()}
                        new_list.append(new_item)
                    else:
                        new_list.append(RichText(str(item) if item is not None else '', color='#FF0000'))
                context[key] = new_list
            else:
                context[key] = RichText(str(value) if value is not None else '', color='#FF0000')
        doc.render(context)
        return doc

    def _create_response(self, buffer: io.BytesIO, filename: str, id_permiviaje: int, mode: str = "download"):
        if mode == "open":
            s3 = get_s3_client()
            object_key = f"rodriguez-zea/documentos/{filename}"
            try:
                url = s3.generate_presigned_url(
                    'get_object',
                    Params={'Bucket': os.environ.get('CLOUDFLARE_R2_BUCKET'), 'Key': object_key},
                    ExpiresIn=3600  # URL expires in 1 hour
                )
                response = JsonResponse({
                    'status': 'success',
                    'mode': 'open',
                    'url': url,
                    'filename': filename,
                    'id_permiviaje': id_permiviaje,
                    'message': 'Document is ready to be opened.'
                })
                response['Access-Control-Allow-Origin'] = '*'
                return response
            except Exception as e:
                return HttpResponse(f"Error generating pre-signed URL: {e}", status=500)
        else:
            if buffer is None:
                return HttpResponse("Error: Document buffer is missing for download mode.", status=500)
            buffer.seek(0)
            response = HttpResponse(buffer.read(), content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
            response['Content-Disposition'] = f'inline; filename="{filename}"'
            response['Content-Length'] = str(buffer.getbuffer().nbytes)
            response['Access-Control-Allow-Origin'] = '*'
            return response

    def _save_document_to_r2(self, buffer: io.BytesIO, filename: str):
        s3 = get_s3_client()
        object_key = f"rodriguez-zea/documentos/{filename}"
        buffer.seek(0)
        s3.put_object(
            Bucket=os.environ.get('CLOUDFLARE_R2_BUCKET'),
            Key=object_key,
            Body=buffer.read()
        )
        buffer.seek(0)

class PermisoViajeInteriorDocumentService(BasePermisoViajeDocumentService):
    def __init__(self):
        super().__init__()
        self.template_filename = "AUTORIZACION VIAJE MENOR INTERIOR.docx"

    def generate_permiso_viaje_interior_document(self, id_permiviaje: int, mode: str = "download") -> HttpResponse:
        try:
            permiviaje = PermiViaje.objects.get(id_viaje=id_permiviaje)
            num_kardex = permiviaje.num_kardex
            if not num_kardex:
                return HttpResponse(f"Error: num_kardex is empty for PermiViaje id {id_permiviaje}", status=400)

            template_bytes = self._get_template_from_r2()
            if template_bytes is None:
                return HttpResponse(
                    f"Error: Template file '{self.template_filename}' not found in R2 path 'rodriguez-zea/plantillas/'.",
                    status=404)
            
            document_data = self.get_document_data(id_permiviaje)
            doc = self._process_document(template_bytes, document_data)
            filename = f"__PROY__{num_kardex}.docx"
            buffer = io.BytesIO()
            doc.save(buffer)
            self._save_document_to_r2(buffer, filename)
            
            return self._create_response(buffer, filename, id_permiviaje, mode)

        except PermiViaje.DoesNotExist:
            return HttpResponse(f"Error: PermiViaje with id {id_permiviaje} not found", status=404)
        except Exception as e:
            traceback.print_exc()
            return HttpResponse(f"Error generating document: {e}", status=500)

    def get_document_data(self, id_permiviaje: int) -> Dict[str, Any]:
        notary_data = self._get_notary_data()
        viaje_data = self._get_viaje_data(id_permiviaje)
        user_data = self._get_user_data(viaje_data.get('NOMBRE_RECEPCIONISTA'))
        participants_data, blocks_data = self._get_participants_data(id_permiviaje)
        
        context = {}
        context.update(notary_data)
        context.update(viaje_data)
        context.update(user_data)
        context.update(participants_data)
        context.update(blocks_data)

        context['PADRE_MADRE'] = self._determine_padre_madre(blocks_data)
        context['VACIO'] = ''
        context['CONFIG'] = f"{id_permiviaje}_permiviaje/"
        
        licencia_info = self._get_licencia_data(viaje_data.get('FECHA_INGRESO_RAW'))
        context.update(licencia_info)
        
        c_list = context.get('c', [])
        if c_list:
            first_contractor = c_list[0]
            context['procede'] = first_contractor.get('procede', '')
            context['SOLICITANTE'] = first_contractor.get('SOLICITANTE', '')

        return context

    def _get_participants_data(self, id_permiviaje: int) -> tuple[Dict[str, Any], Dict[str, List[Dict[str, Any]]]]:
        with connection.cursor() as cursor:
            participants_data, blocks_data = {}, {}
            cursor.execute("SELECT COUNT(*) FROM viaje_contratantes WHERE c_condicontrat IN ('001','003','004','005','010') AND id_viaje = %s", [id_permiviaje])
            num_contratantes = cursor.fetchone()[0]
            
            contratantes_query = """SELECT vc.c_condicontrat, CONCAT_WS(' ', c.prinom, c.segnom, c.apepat, c.apemat) AS contratante, td.destipdoc as tipo_documento, td.td_abrev as abreviatura, c.numdoc as numero_documento, n.descripcion as nacionalidad, c.direccion, vc.c_fircontrat, IF(u.coddis='' OR ISNULL(u.coddis), '', CONCAT('DISTRITO DE ',u.nomdis, ', PROVINCIA DE ', u.nomprov,', DEPARTAMENTO DE ',u.nomdpto)) AS ubigeo, tec.desestcivil as estado_civil, IFNULL(p.desprofesion,'') as profesion, IFNULL(vc.codi_podera,'') as codigo_poderado, c.detaprofesion as profesion_cliente, (CASE WHEN vc.condi_edad = 1 THEN CONCAT(vc.edad,' AÑOS') WHEN vc.condi_edad = 2 THEN CONCAT(vc.edad,' MESES') ELSE '' END) as edad, c.sexo FROM viaje_contratantes vc JOIN cliente c ON c.numdoc = vc.c_codcontrat JOIN tipodocumento td ON td.idtipdoc = c.idtipdoc JOIN nacionalidades n ON n.idnacionalidad = c.nacionalidad JOIN tipoestacivil tec ON tec.idestcivil = c.idestcivil LEFT JOIN profesiones p ON p.idprofesion = c.idprofesion LEFT JOIN ubigeo u ON u.coddis = c.idubigeo WHERE vc.c_condicontrat IN ('001','003','004','005','010') AND vc.id_viaje = %s"""
            cursor.execute(contratantes_query, [id_permiviaje])
            
            columns = [col[0] for col in cursor.description]
            contratantes_list = [dict(zip(columns, row)) for row in cursor.fetchall()]

            for p in contratantes_list:
                sex = p.get('sexo', 'M')
                p.update({'identificado': 'IDENTIFICADO' if sex == 'M' else 'IDENTIFICADA', 'domiciliado': 'CON DOMICILIO ', 'senor': 'SEÑOR' if sex == 'M' else 'SEÑORA', 'el': 'EL' if sex == 'M' else 'LA', 'don': 'DON' if sex == 'M' else 'DOÑA'})
                if p.get('nacionalidad'): p['nacionalidad'] = p['nacionalidad'][:-1] + ('O' if sex == 'M' and p['nacionalidad'].endswith('A') else ('A' if sex == 'F' and p['nacionalidad'].endswith('O') else p['nacionalidad'][-1]))
                if num_contratantes > 1: p.update({'SOLICITANTE': 'a los solicitantes', 'procede': 'Los compareciente proceden'})
                else: p.update({'SOLICITANTE': 'al solicitante' if sex == 'M' else 'a la solicitante', 'procede': 'El compareciente procede' if sex == 'M' else 'La compareciente procede'})
            blocks_data['c'] = contratantes_list
            
            max_cols = 3
            signature_rows = []
            for i in range(0, len(contratantes_list), max_cols):
                row = contratantes_list[i:i + max_cols]
                while len(row) < max_cols:
                    row.append(None)
                signature_rows.append(row)
            blocks_data['signature_rows'] = signature_rows

            minors_query = "SELECT CONCAT_WS(' ', c.prinom, c.segnom, c.apepat, c.apemat) AS contratante, (CASE WHEN vc.condi_edad = 1 THEN CONCAT(vc.edad,' AÑOS') WHEN vc.condi_edad = 2 THEN CONCAT(vc.edad,' MESES') ELSE '' END) as edad, c.sexo, td.td_abrev as abreviatura, c.numdoc as numero_documento FROM viaje_contratantes vc JOIN cliente c ON c.numdoc = vc.c_codcontrat JOIN tipodocumento td ON td.idtipdoc=c.idtipdoc WHERE vc.c_condicontrat = '002' AND vc.id_viaje = %s"
            cursor.execute(minors_query, [id_permiviaje])
            
            columns = [col[0] for col in cursor.description]
            minors_list = [dict(zip(columns, row)) for row in cursor.fetchall()]
            all_female = all(p.get('sexo') == 'F' for p in minors_list)
            for i, p in enumerate(minors_list):
                sex = p.get('sexo', 'M')
                p['identificado'] = 'IDENTIFICADO' if sex == 'M' else 'IDENTIFICADA'
                p['y_coma'] = '.' if i == len(minors_list) - 1 else (' Y' if i == len(minors_list) - 2 else ',')
            blocks_data['m'] = minors_list
            blocks_data['f'] = contratantes_list
            
            if len(contratantes_list) > 1: participants_data.update({'A_EL_LOS': 'LOS', 'A_S': 'S', 'A_N': 'N'})
            else: participants_data.update({'A_EL_LOS': 'EL', 'A_S': '', 'A_N': ''})
            
            if len(minors_list) == 1:
                sex = minors_list[0].get('sexo', 'M')
                participants_data.update({'EL_LA_LOS': 'LA' if sex == 'F' else 'EL', 'HIJO': 'HIJA' if sex == 'F' else 'HIJO', 'MENOR': 'SU MENOR', 'AUTORIZA': 'AUTORIZA'})
            else:
                participants_data.update({'EL_LA_LOS': 'LAS' if all_female else 'LOS', 'HIJO': 'HIJAS' if all_female else 'HIJOS', 'MENOR': 'SUS MENORES', 'AUTORIZA': 'AUTORIZAN'})
            
            cursor.execute("SELECT id_condicion, des_condicion FROM c_condiciones WHERE swt_condicion = 'V' AND id_condicion != '002'")
            for id_cond, desc in cursor.fetchall():
                cursor.execute(contratantes_query.replace("WHERE vc.c_condicontrat IN ('001','003','004','005','010')", f"WHERE vc.c_condicontrat = '{id_cond}'"), [id_permiviaje])
                rows = cursor.fetchall()
                if rows:
                    cols = [col[0] for col in cursor.description]
                    participant_dict = dict(zip(cols, rows[0]))
                    for k, v in participant_dict.items():
                        participants_data[f"{desc.lower()}_{k.upper()}"] = v
            
            return participants_data, blocks_data

    def _determine_padre_madre(self, blocks_data: Dict[str, Any]) -> str:
        contratantes = blocks_data.get('c', [])
        has_male = any(p.get('sexo') == 'M' for p in contratantes)
        has_female = any(p.get('sexo') == 'F' for p in contratantes)
        if has_male and has_female: return 'PADRES'
        if has_male: return 'PADRE'
        if has_female: return 'MADRE'
        return ''

class PermisoViajeExteriorDocumentService(BasePermisoViajeDocumentService):
    def __init__(self):
        super().__init__()
        self.template_filename = "AUTORIZACION VIAJE MENOR EXTERIOR.docx"

    def generate_permiso_viaje_exterior_document(self, id_permiviaje: int, mode: str = "download") -> HttpResponse:
        try:
            permiviaje = PermiViaje.objects.get(id_viaje=id_permiviaje)
            num_kardex = permiviaje.num_kardex
            if not num_kardex:
                return HttpResponse(f"Error: num_kardex is empty for PermiViaje id {id_permiviaje}", status=400)

            template_bytes = self._get_template_from_r2()
            if template_bytes is None:
                return HttpResponse(
                    f"Error: Template file '{self.template_filename}' not found in R2 path 'rodriguez-zea/plantillas/'.",
                    status=404)
            
            document_data = self.get_document_data(id_permiviaje)
            doc = self._process_document(template_bytes, document_data)
            filename = f"__PROY__{num_kardex}.docx"
            buffer = io.BytesIO()
            doc.save(buffer)
            self._save_document_to_r2(buffer, filename)
            
            return self._create_response(buffer, filename, id_permiviaje, mode)

        except PermiViaje.DoesNotExist:
            return HttpResponse(f"Error: PermiViaje with id {id_permiviaje} not found", status=404)
        except Exception as e:
            traceback.print_exc()
            return HttpResponse(f"Error generating document: {e}", status=500)

    def get_document_data(self, id_permiviaje: int) -> Dict[str, Any]:
        notary_data = self._get_notary_data()
        viaje_data = self._get_viaje_data(id_permiviaje)
        user_data = self._get_user_data(viaje_data.get('NOMBRE_RECEPCIONISTA'))
        participants_data, blocks_data = self._get_participants_data(id_permiviaje)
        
        context = {}
        context.update(notary_data)
        context.update(viaje_data)
        context.update(user_data)
        context.update(participants_data)
        context.update(blocks_data)

        licencia_info = self._get_licencia_data(viaje_data.get('FECHA_INGRESO_RAW'))
        context.update(licencia_info)
        
        # Pull out standalone values from the first participant for easier access in the template
        c_list = context.get('c', [])
        if c_list:
            context['procede'] = c_list[0].get('procede', '')
            context['SOLICITANTE'] = c_list[0].get('SOLICITANTE', '')

        return context

    def _get_participants_data(self, id_permiviaje: int) -> tuple[Dict[str, Any], Dict[str, List[Dict[str, Any]]]]:
        with connection.cursor() as cursor:
            participants_data = {}
            blocks_data = {}

            # These are all the roles that can sign the Exterior permit
            contratante_conditions = "('001', '003', '004', '005', '010')"
            
            cursor.execute(f"SELECT COUNT(*) FROM viaje_contratantes WHERE c_condicontrat IN {contratante_conditions} AND id_viaje = %s", [id_permiviaje])
            num_contratantes = cursor.fetchone()[0]

            base_query = f"""
                SELECT 
                    vc.c_condicontrat AS id_condicion,
                    CONCAT_WS(' ', c.prinom, c.segnom, c.apepat, c.apemat) AS contratante,
                    td.destipdoc AS tipo_documento,
                    td.td_abrev AS abreviatura,
                    c.numdoc AS numero_documento,
                    IF(c.sexo='M', CONCAT(SUBSTRING(n.descripcion, 1, LENGTH(n.descripcion)-1),'O'), CONCAT(SUBSTRING(n.descripcion, 1, LENGTH(n.descripcion)-1),'A')) AS nacionalidad,
                    CONCAT(' CON DOMICILIO EN ', c.direccion) AS direccion,
                    IF(u.coddis='' OR ISNULL(u.coddis), '', CONCAT('DEL DISTRITO DE ', u.nomdis, ', PROVINCIA DE ', u.nomprov, ', DEPARTAMENTO DE ', u.nomdpto)) AS ubigeo,
                    tec.desestcivil AS estado_civil,
                    IFNULL(p.desprofesion, '') AS profesion,
                    c.sexo
                FROM viaje_contratantes vc
                JOIN cliente c ON c.numdoc = vc.c_codcontrat
                JOIN tipodocumento td ON td.idtipdoc = c.idtipdoc
                JOIN nacionalidades n ON n.idnacionalidad = c.nacionalidad
                JOIN tipoestacivil tec ON tec.idestcivil = c.idestcivil
                LEFT JOIN profesiones p ON p.idprofesion = c.idprofesion
                LEFT JOIN ubigeo u ON u.coddis = c.idubigeo
                WHERE vc.id_viaje = %s AND vc.c_condicontrat IN {contratante_conditions}
            """
            
            cursor.execute(base_query, [id_permiviaje])
            columns = [col[0] for col in cursor.description]
            contratantes_list = [dict(zip(columns, row)) for row in cursor.fetchall()]

            for p in contratantes_list:
                sex = p.get('sexo', 'M')
                p.update({
                    'identificado': 'IDENTIFICADO' if sex == 'M' else 'IDENTIFICADA',
                    'senor': 'SEÑOR' if sex == 'M' else 'SEÑORA',
                    'el': 'EL' if sex == 'M' else 'LA',
                })
                if num_contratantes > 1:
                    p.update({'SOLICITANTE': 'a los solicitantes', 'procede': 'Los comparecientes proceden'})
                else:
                    p.update({'SOLICITANTE': 'al solicitante' if sex == 'M' else 'a la solicitante', 'procede': 'El compareciente procede' if sex == 'M' else 'La compareciente procede'})
            
            blocks_data['c'] = contratantes_list

            # This will be used for the flexible signature block
            max_cols = 2 # Exterior template has 2 signatures per row
            signature_rows = []
            for i in range(0, len(contratantes_list), max_cols):
                row = contratantes_list[i:i + max_cols]
                while len(row) < max_cols:
                    row.append(None)
                signature_rows.append(row)
            blocks_data['signature_rows'] = signature_rows

            minors_query = "SELECT CONCAT_WS(' ', c.prinom, c.segnom, c.apepat, c.apemat) AS contratante, (CASE WHEN vc.condi_edad = 1 THEN CONCAT(vc.edad,' AÑOS') WHEN vc.condi_edad = 2 THEN CONCAT(vc.edad,' MESES') ELSE '' END) as edad, c.sexo, td.td_abrev as abreviatura, c.numdoc as numero_documento FROM viaje_contratantes vc JOIN cliente c ON c.numdoc = vc.c_codcontrat JOIN tipodocumento td ON td.idtipdoc=c.idtipdoc WHERE vc.c_condicontrat = '002' AND vc.id_viaje = %s"
            cursor.execute(minors_query, [id_permiviaje])
            columns = [col[0] for col in cursor.description]
            minors_list = [dict(zip(columns, row)) for row in cursor.fetchall()]
            all_female = all(p.get('sexo') == 'F' for p in minors_list)
            for i, p in enumerate(minors_list):
                sex = p.get('sexo', 'M')
                p['identificado'] = 'IDENTIFICADO' if sex == 'M' else 'IDENTIFICADA'
                p['y_coma'] = '.' if i == len(minors_list) - 1 else (' Y' if i == len(minors_list) - 2 else ',')
            blocks_data['m'] = minors_list

            if len(minors_list) == 1:
                sex = minors_list[0].get('sexo', 'M')
                participants_data.update({'HIJO': 'HIJA' if sex == 'F' else 'HIJO', 'MENOR': 'MENOR', 'AUTORIZA': 'AUTORIZA'})
            else:
                participants_data.update({'HIJO': 'HIJAS' if all_female else 'HIJOS', 'MENOR': 'MENORES', 'AUTORIZA': 'AUTORIZAN'})

            return participants_data, blocks_data 