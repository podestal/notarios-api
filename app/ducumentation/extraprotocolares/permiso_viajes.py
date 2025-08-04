import boto3
from botocore.client import Config
from django.conf import settings
import os
import io
from docx import Document
from docxcompose.properties import CustomProperties
from docx.shared import RGBColor, Pt
from decimal import Decimal
from typing import Dict, Any, List
from django.http import HttpResponse, JsonResponse
from notaria.models import TplTemplate, Cliente, Tipodocumento, Nacionalidades, Tipoestacivil, Profesiones, Ubigeo, PermiViaje, ViajeContratantes
from .utils import NumberToLetterConverter
import time
from django.db import connection
import re

# Cached S3 client to avoid recreating on every request
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


class PermisoViajeInteriorDocumentService:
    """
    Django service to generate Permiso Viaje Interior documents based on the PHP logic
    """
    
    def __init__(self):
        self.letras = NumberToLetterConverter()
    
    def generate_permiso_viaje_interior_document(self, id_permiviaje: int, action: str = 'generate', mode: str = "download") -> HttpResponse:
        """
        Main method to generate Permiso Viaje Interior document
        """
        start_time = time.time()
        print(f"PERF: Starting Permiso Viaje Interior document generation for id: {id_permiviaje}")
        
        try:
            # Get the num_kardex from the PermiViaje model
            from notaria.models import PermiViaje
            try:
                permiviaje = PermiViaje.objects.get(id_viaje=id_permiviaje)
                num_kardex = permiviaje.num_kardex
                if not num_kardex:
                    return HttpResponse(f"Error: num_kardex is empty for PermiViaje id {id_permiviaje}", status=400)
            except PermiViaje.DoesNotExist:
                return HttpResponse(f"Error: PermiViaje with id {id_permiviaje} not found", status=404)
            
            # Step 1: Get template from R2 using fixed filename
            template_start = time.time()
            template = self._get_template_from_r2()
            template_time = time.time() - template_start
            print(f"PERF: Template download took {template_time:.2f}s")
            
            # Step 2: Get document data
            data_start = time.time()
            document_data = self.get_document_data(id_permiviaje)
            data_time = time.time() - data_start
            print(f"PERF: Data retrieval took {data_time:.2f}s")
            
            # Step 3: Process document
            process_start = time.time()
            doc = self._process_document(template, document_data)
            process_time = time.time() - process_start
            print(f"PERF: Document processing took {process_time:.2f}s")
            
            # Step 4: Remove placeholders
            cleanup_start = time.time()
            self.remove_unfilled_placeholders(doc)
            cleanup_time = time.time() - cleanup_start
            print(f"PERF: Placeholder cleanup took {cleanup_time:.2f}s")
            
            # Step 5: Upload to R2
            upload_start = time.time()
            upload_success = self.create_documento_in_r2(doc, num_kardex)
            upload_time = time.time() - upload_start
            print(f"PERF: R2 upload took {upload_time:.2f}s")
            
            if not upload_success:
                print(f"WARNING: Failed to upload document to R2 for num_kardex: {num_kardex}")
            
            total_time = time.time() - start_time
            print(f"PERF: Total Permiso Viaje Interior document generation took {total_time:.2f}s")
            
            return self._create_response(doc, f"__PROY__{num_kardex}.docx", id_permiviaje, mode)
        except FileNotFoundError as e:
            return HttpResponse(str(e), status=404)
        except Exception as e:
            total_time = time.time() - start_time
            print(f"PERF: Permiso Viaje Interior document generation failed after {total_time:.2f}s")
            return HttpResponse(f"Error generating document: {str(e)}", status=500)

    def _get_template_from_r2(self) -> bytes:
        """
        Get template from R2 storage using fixed filename - same as PHP approach
        """
        s3 = get_s3_client()
        
        # Use fixed template filename like PHP
        object_key = f"rodriguez-zea/plantillas/PERMISO_VIAJE_INTERIOR.docx"
        print(f"DEBUG: Template file: PERMISO_VIAJE_INTERIOR.docx")
        
        try:
            response = s3.get_object(Bucket=os.environ.get('CLOUDFLARE_R2_BUCKET'), Key=object_key)
            template_bytes = response['Body'].read()
            print(f"DEBUG: Successfully downloaded template: {len(template_bytes)} bytes")
            
            return template_bytes
        except Exception as e:
            print(f"Error downloading template from R2: {e}")
            raise

    def get_document_data(self, id_permiviaje: int) -> Dict[str, Any]:
        """
        Get all data needed for the Permiso Viaje Interior document
        """
        # Get notary data
        notary_data = self._get_notary_data()
        
        # Get travel permit data
        viaje_data = self._get_viaje_data(id_permiviaje)
        
        # Get participants data by condition
        participants_data = self._get_participants_data(id_permiviaje)
        
        # Determine PADRE_MADRE logic
        padre_madre = self._determine_padre_madre(participants_data)
        
        # Combine all data
        final_data = {}
        final_data.update(notary_data)
        final_data.update(viaje_data)
        final_data.update(participants_data)
        final_data['PADRE_MADRE'] = padre_madre
        final_data['VACIO'] = ''
        final_data['CONFIG'] = f"{id_permiviaje}_permiviaje/"
        
        return final_data

    def _get_notary_data(self) -> Dict[str, str]:
        """
        Get notary configuration data using raw SQL
        """
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT nombre AS nombres, apellido AS apellidos, 
                       CONCAT(nombre,' ',apellido) AS notario, ruc AS ruc_notario, 
                       distrito AS distrito_notario 
                FROM confinotario
            """)
            row = cursor.fetchone()
            
            if row:
                columns = [col[0] for col in cursor.description]
                notary_data = dict(zip(columns, row))
                
                # Convert to uppercase and handle special cases
                final_data = {}
                for key, value in notary_data.items():
                    if key == 'ruc_notario' and value:
                        # Convert RUC to letters
                        letters_ruc = self.letras.number_to_letters(value)
                        final_data[f'LETRA_{key.upper()}'] = letters_ruc
                    
                    key_upper = key.upper().strip()
                    value = value if value is not None else '?'
                    final_data[key_upper] = str(value).upper()
                
                return final_data
            else:
                # Return empty data if no notary found
                return {
                    'NOMBRES': '?',
                    'APELLIDOS': '?',
                    'NOTARIO': '?',
                    'RUC_NOTARIO': '?',
                    'DISTRITO_NOTARIO': '?',
                    'LETRA_RUC_NOTARIO': ''
                }

    def _get_viaje_data(self, id_permiviaje: int) -> Dict[str, str]:
        """
        Get travel permit data
        """
        try:
            viaje = PermiViaje.objects.get(id_viaje=id_permiviaje)
            
            viaje_data = {
                'ID_VIAJE': str(viaje.id_viaje),
                'KARDEX': viaje.num_kardex or '?',
                'ASUNTO': viaje.asunto or '?',
                'FECHA_INGRESO': viaje.fec_ingreso.strftime('%d/%m/%Y') if viaje.fec_ingreso else '?',
                'NOMBRE_RECEPCIONISTA': viaje.nom_recep or '?',
                'HORA_RECEPCION': viaje.hora_recep or '?',
                'REFERENCIA': viaje.referencia or '?',
                'COMUNICARSE': viaje.nom_comu or '?',
                'COMUNICARSE_EMAIL': viaje.email_comu or '?',
                'DOCUMENTO': viaje.documento or '?',
                'NUMERO_CRONOLOGICO': viaje.num_crono or '?',
                'FECHA_CRONOLOGICO': viaje.fecha_crono.strftime('%d/%m/%Y') if viaje.fecha_crono else '?',
                'NUMERO_FORMULARIO': viaje.num_formu or '?',
                'DESTINO': viaje.lugar_formu or '?',
                'OBSERVACION': viaje.observacion or '?',
                'SWT_EST': viaje.swt_est or '?',
                'PARTIDA_E': viaje.partida_e or '?',
                'SEDE_REGIS': viaje.sede_regis or '?'
            }
            
            # Handle special cases
            if viaje.fec_ingreso:
                letters_fecha = self.letras.date_to_letters(viaje.fec_ingreso)
                viaje_data['LETRA_FECHA_INGRESO'] = letters_fecha
            
            return viaje_data
            
        except PermiViaje.DoesNotExist:
            # Return empty data if not found
            return {
                'ID_VIAJE': '?',
                'KARDEX': '?',
                'ASUNTO': '?',
                'FECHA_INGRESO': '?',
                'NOMBRE_RECEPCIONISTA': '?',
                'HORA_RECEPCION': '?',
                'REFERENCIA': '?',
                'COMUNICARSE': '?',
                'COMUNICARSE_EMAIL': '?',
                'DOCUMENTO': '?',
                'NUMERO_CRONOLOGICO': '?',
                'FECHA_CRONOLOGICO': '?',
                'NUMERO_FORMULARIO': '?',
                'DESTINO': '?',
                'OBSERVACION': '?',
                'SWT_EST': '?',
                'PARTIDA_E': '?',
                'SEDE_REGIS': '?',
                'LETRA_FECHA_INGRESO': ''
            }

    def _get_participants_data(self, id_permiviaje: int) -> Dict[str, Any]:
        """
        Get participants data by condition using raw SQL
        """
        with connection.cursor() as cursor:
            # Get all conditions
            cursor.execute("""
                SELECT c_condiciones.id, c_condiciones.id_condicion AS idCondicion,
                       c_condiciones.des_condicion AS condicion, c_condiciones.swt_condicion AS swtCondicion 
                FROM c_condiciones 
                ORDER BY c_condiciones.id
            """)
            conditions = cursor.fetchall()
            
            participants_data = {}
            
            for condition_row in conditions:
                id_condicion = condition_row[1]  # idCondicion
                condicion = condition_row[2].lower()  # condicion
                
                # Get participants for this condition
                cursor.execute("""
                    SELECT viaje_contratantes.c_condicontrat AS id_condicion,
                           CONCAT(cliente.prinom, ' ', cliente.segnom, ' ', cliente.apepat, ' ', cliente.apemat) AS contratante,
                           tipodocumento.destipdoc AS tipo_documento, cliente.numdoc AS numero_documento, 
                           nacionalidades.descripcion AS nacionalidad, cliente.direccion AS direccion,  
                           viaje_contratantes.c_fircontrat, cliente.direccion,
                           IF(ubigeo.coddis='' OR ISNULL(ubigeo.coddis) ,'',
                              CONCAT('DISTRITO DE ',ubigeo.nomdis, ', PROVINCIA DE ', ubigeo.nomprov,', DEPARTAMENTO DE ',ubigeo.nomdpto )) AS ubigeo,
                           tipoestacivil.desestcivil AS estado_civil,
                           IF(ISNULL(profesiones.desprofesion),'',profesiones.desprofesion) AS profesion, 
                           IF(ISNULL(viaje_contratantes.codi_podera),'',viaje_contratantes.codi_podera) AS codigo_poderado,
                           cliente.detaprofesion AS profesion_cliente,
                           (CASE WHEN viaje_contratantes.condi_edad = 1 AND viaje_contratantes.edad != '' 
                                 THEN CONCAT(viaje_contratantes.edad,' AÑOS') 
                                 WHEN viaje_contratantes.condi_edad = 2 AND viaje_contratantes.edad != '' 
                                 THEN CONCAT(viaje_contratantes.edad,' MESES')
                                 ELSE '' END) AS edad
                    FROM viaje_contratantes 
                    INNER JOIN cliente ON cliente.numdoc = viaje_contratantes.c_codcontrat
                    INNER JOIN tipodocumento ON tipodocumento.idtipdoc = cliente.idtipdoc
                    INNER JOIN nacionalidades ON nacionalidades.idnacionalidad = cliente.nacionalidad
                    INNER JOIN tipoestacivil ON tipoestacivil.idestcivil = cliente.idestcivil
                    LEFT OUTER JOIN profesiones ON profesiones.idprofesion = cliente.idprofesion
                    LEFT OUTER JOIN ubigeo ON ubigeo.coddis = cliente.idubigeo
                    WHERE viaje_contratantes.c_condicontrat = %s AND viaje_contratantes.id_viaje = %s
                """, [id_condicion, id_permiviaje])
                
                participants = cursor.fetchall()
                
                if participants:
                    columns = [col[0] for col in cursor.description]
                    participants_list = []
                    
                    for participant_row in participants:
                        participant_dict = dict(zip(columns, participant_row))
                        participants_list.append(participant_dict)
                        
                        # Add individual fields for template
                        for key, value in participant_dict.items():
                            field_name = f"{condicion.upper()}_{key.upper()}"
                            participants_data[field_name] = str(value) if value is not None else ''
                    
                    participants_data[condicion] = participants_list
                else:
                    # Add empty fields for this condition
                    columns = [col[0] for col in cursor.description]
                    for col in columns:
                        field_name = f"{condicion.upper()}_{col.upper()}"
                        participants_data[field_name] = ''
                    
                    participants_data[condicion] = []
            
            return participants_data

    def _determine_padre_madre(self, participants_data: Dict[str, Any]) -> str:
        """
        Determine PADRE_MADRE based on participants data
        """
        padre_count = len(participants_data.get('padre', []))
        madre_count = len(participants_data.get('madre', []))
        
        if padre_count != 0 and madre_count != 0:
            return 'PADRES'
        elif padre_count != 0:
            return 'PADRE'
        else:
            return 'MADRE'

    def _process_document(self, template_bytes: bytes, data: Dict[str, Any]) -> Document:
        """
        Process the document template with data using simple python-docx approach
        """
        # Create document from template bytes using simple python-docx
        buffer = io.BytesIO(template_bytes)
        doc = Document(buffer)
        
        # Replace placeholders in paragraphs
        for paragraph in doc.paragraphs:
            for placeholder, value in data.items():
                placeholder_text = f"{{{{{placeholder}}}}}"
                if placeholder_text in paragraph.text:
                    paragraph.text = paragraph.text.replace(placeholder_text, str(value))
        
        # Replace placeholders in tables
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        for placeholder, value in data.items():
                            placeholder_text = f"{{{{{placeholder}}}}}"
                            if placeholder_text in paragraph.text:
                                paragraph.text = paragraph.text.replace(placeholder_text, str(value))
        
        return doc

    def remove_unfilled_placeholders(self, doc):
        """
        Remove all unfilled {{SOMETHING}} placeholders completely
        """
        import re
        curly_placeholder_pattern = re.compile(r'\{\{[A-Z0-9_]+\}\}')

        def clean_runs(runs):
            for run in runs:
                # Remove all {{SOMETHING}} placeholders
                run.text = curly_placeholder_pattern.sub('', run.text)

        # Clean paragraphs
        for paragraph in doc.paragraphs:
            clean_runs(paragraph.runs)
        # Clean tables
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        clean_runs(paragraph.runs)

    def create_documento_in_r2(self, doc, num_kardex: str):
        """
        Upload the generated document to R2
        """
        try:
            from io import BytesIO
            buffer = BytesIO()
            doc.save(buffer)
            buffer.seek(0)
            object_key = f"rodriguez-zea/documentos/__PROY__{num_kardex}.docx"
            s3 = get_s3_client()
            s3.upload_fileobj(
                buffer,
                os.environ.get('CLOUDFLARE_R2_BUCKET'),
                object_key
            )
            return True
        except Exception as e:
            print(f"Error uploading Permiso Viaje Interior document to R2: {e}")
            return False

    def _create_response(self, doc, filename: str, id_permiviaje: int, mode: str = "download") -> HttpResponse:
        """
        Create HTTP response with the document
        """
        from docxcompose.properties import CustomProperties
        
        # Add the custom property
        custom_props = CustomProperties(doc)
        custom_props['documentoGeneradoId'] = str(id_permiviaje)

        # Save to buffer
        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        
        if mode == "open":
            # Production mode: Return JSON with file info for Word opening
            response = JsonResponse({
                'status': 'success',
                'mode': 'open',
                'filename': filename,
                'id_permiviaje': id_permiviaje,
                'message': 'Document generated and ready to open in Word'
            })
            response['Access-Control-Allow-Origin'] = '*'
            return response
        else:
            # Testing mode: Download the document
            response = HttpResponse(
                buffer.read(),
                content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            )
            response['Content-Disposition'] = f'inline; filename="{filename}"'
            response['Content-Length'] = str(buffer.getbuffer().nbytes)
            response['Access-Control-Allow-Origin'] = '*'
            return response
