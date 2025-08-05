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


class TBSTemplateProcessor:
    """
    TinyButStrong-like template processor for Python
    """
    
    def __init__(self):
        self.data = {}
        self.blocks = {}
    
    def set_data(self, data: Dict[str, Any]):
        """Set the data for template processing"""
        self.data = data
    
    def set_blocks(self, blocks: Dict[str, List[Dict[str, Any]]]):
        """Set the blocks for template processing"""
        self.blocks = blocks
    
    def process_document(self, doc: Document) -> Document:
        """Process the document with TBS-like logic"""
        
        # Process paragraphs
        for paragraph in doc.paragraphs:
            self._process_paragraph(paragraph)
        
        # Process tables
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        self._process_paragraph(paragraph)
        
        return doc
    
    def _process_paragraph(self, paragraph):
        """Process a single paragraph with TBS logic - focus on getting blocks to work first"""
        original_text = paragraph.text
        
        # Process blocks first
        processed_text = self._process_blocks(original_text)
        
        # Process variables
        processed_text = self._process_variables(processed_text)
        
        # Update paragraph text if changed
        if processed_text != original_text:
            paragraph.clear()
            if processed_text:
                # Just add the processed text without any red tinting for now
                paragraph.add_run(processed_text)

    def _process_blocks(self, text: str) -> str:
        """Process TBS-style blocks like {c.block=begin;}...{c.block=end;} and {m;block=begin;}...{m;block=end;}"""
        
        # Pattern to match blocks: {prefix.block=begin;}...{prefix.block=end;} or {prefix;block=begin;}...{prefix;block=end;}
        # Updated pattern to handle both formats correctly
        block_pattern = r'\{([a-z])[.;]block=begin;\}(.*?)\{\1[.;]block=end;\}'
        
        def replace_block(match):
            prefix = match.group(1)  # e.g., 'c', 'f', 'm'
            block_content = match.group(2)
            
            print(f"DEBUG: Processing block '{prefix}' with content: {block_content[:50]}...")
            print(f"DEBUG: Available blocks: {list(self.blocks.keys())}")
            
            if prefix in self.blocks and self.blocks[prefix]:
                # Process each item in the block
                results = []
                for item in self.blocks[prefix]:
                    item_text = block_content
                    # Replace variables in this block item
                    for key, value in item.items():
                        placeholder = f"{{{prefix}.{key}}}"
                        if placeholder in item_text:
                            print(f"DEBUG: Replacing {placeholder} with {value}")
                            item_text = item_text.replace(placeholder, str(value))
                    results.append(item_text)
                
                result = ' '.join(results)
                print(f"DEBUG: Block '{prefix}' result: {result[:50]}...")
                return result
            else:
                # Remove block if no data
                print(f"DEBUG: Block '{prefix}' not found in blocks data")
                return ''
        
        # Debug: Print what blocks we're looking for
        print(f"DEBUG: Processing text for blocks: {text[:100]}...")
        
        result = re.sub(block_pattern, replace_block, text, flags=re.DOTALL)
        print(f"DEBUG: Block processing result: {result[:100]}...")
        
        return result
    
    def _process_variables(self, text: str) -> str:
        """Process TBS-style variables like {var.VARIABLE}"""
        
        # Pattern to match variables: {var.VARIABLE} or {prefix.VARIABLE}
        var_pattern = r'\{([a-z]+)\.([A-Z0-9_]+)\}'
        
        def replace_variable(match):
            prefix = match.group(1)  # e.g., 'var', 'c', 'f', 'm'
            variable = match.group(2)  # e.g., 'KARDEX', 'CONTRATANTE'
            
            if prefix == 'var':
                # Direct variable lookup
                value = str(self.data.get(variable, ''))
                print(f"DEBUG: Variable {prefix}.{variable} -> {value}")
                return value
            elif prefix in self.blocks and self.blocks[prefix]:
                # Block variable lookup (take first item)
                value = str(self.blocks[prefix][0].get(variable, ''))
                print(f"DEBUG: Block variable {prefix}.{variable} -> {value}")
                return value
            else:
                # Remove if not found
                print(f"DEBUG: Variable {prefix}.{variable} not found")
                return ''
        
        result = re.sub(var_pattern, replace_variable, text)
        return result


class PermisoViajeInteriorDocumentService:
    """
    Django service to generate Permiso Viaje Interior documents based on the PHP logic
    """
    
    def __init__(self):
        self.letras = NumberToLetterConverter()
        self.tbs_processor = TBSTemplateProcessor()
    
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
            document_data, blocks_data = self.get_document_data(id_permiviaje)
            data_time = time.time() - data_start
            print(f"PERF: Data retrieval took {data_time:.2f}s")
            
            # Step 3: Process document with TBS-like processor
            process_start = time.time()
            doc = self._process_document_with_red_tinting(template, document_data, blocks_data)
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
        object_key = f"rodriguez-zea/plantillas/AUTORIZACION VIAJE MENOR INTERIOR.docx"
        print(f"DEBUG: Template file: AUTORIZACION VIAJE MENOR INTERIOR.docx")
        print(f"DEBUG: Template path: {object_key}")
        
        try:
            response = s3.get_object(Bucket=os.environ.get('CLOUDFLARE_R2_BUCKET'), Key=object_key)
            template_bytes = response['Body'].read()
            print(f"DEBUG: Successfully downloaded template: {len(template_bytes)} bytes")
            
            return template_bytes
        except Exception as e:
            print(f"Error downloading template from R2: {e}")
            print(f"Template path attempted: {object_key}")
            print(f"")
            print(f"SOLUTION: You need to upload the AUTORIZACION VIAJE MENOR INTERIOR.docx template to your R2 storage.")
            print(f"Upload the template to: rodriguez-zea/plantillas/AUTORIZACION VIAJE MENOR INTERIOR.docx")
            print(f"")
            print(f"Template should contain placeholders like:")
            print(f"  - {{var.KARDEX}}")
            print(f"  - {{var.LETRA_FECHA_INGRESO}}")
            print(f"  - {{c.block=begin;}}{{c.contratante}}{{c.block=end;}}")
            print(f"  - {{m.block=begin;}}{{m.contratante}}{{m.block=end;}}")
            print(f"  - etc.")
            raise

    def get_document_data(self, id_permiviaje: int) -> tuple[Dict[str, Any], Dict[str, List[Dict[str, Any]]]]:
        """
        Get all data needed for the Permiso Viaje Interior document
        Returns both variables and blocks data
        """
        # Get notary data
        notary_data = self._get_notary_data()
        
        # Get travel permit data
        viaje_data = self._get_viaje_data(id_permiviaje)
        
        # Get user data
        user_data = self._get_user_data(viaje_data.get('NOMBRE_RECEPCIONISTA'))
        
        # Get participants data by condition
        participants_data, blocks_data = self._get_participants_data(id_permiviaje)
        
        # Determine PADRE_MADRE logic
        padre_madre = self._determine_padre_madre(participants_data)
        
        # Combine all data
        final_data = {}
        final_data.update(notary_data)
        final_data.update(viaje_data)
        final_data.update(user_data)
        final_data.update(participants_data)
        final_data['PADRE_MADRE'] = padre_madre
        final_data['VACIO'] = ''
        final_data['CONFIG'] = f"{id_permiviaje}_permiviaje/"
        
        return final_data, blocks_data

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
                'SEDE_REGIS': viaje.sede_regis or '?',
                # Additional fields from PHP script
                'REFER': viaje.referencia or '?',
                'VIA_TRANS': getattr(viaje, 'via', '?') or '?',
                'FEC_DESDE': self.letras.date_to_letters(viaje.fecha_desde) if hasattr(viaje, 'fecha_desde') and viaje.fecha_desde else '?',
                'FEC_HASTA': self.letras.date_to_letters(viaje.fecha_hasta) if hasattr(viaje, 'fecha_hasta') and viaje.fecha_hasta else '?'
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
                'LETRA_FECHA_INGRESO': '',
                'REFER': '?',
                'VIA_TRANS': '?',
                'FEC_DESDE': '?',
                'FEC_HASTA': '?'
            }

    def _get_user_data(self, usuario_imprime: str = None) -> Dict[str, str]:
        """
        Get user data for the document
        """
        if not usuario_imprime:
            return {
                'USUARIO': '?',
                'USUARIO_DNI': '?'
            }
        
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT loginusuario, dni
                FROM usuarios 
                WHERE CONCAT(apepat,' ',prinom) = %s
            """, [usuario_imprime])
            row = cursor.fetchone()
            
            if row:
                return {
                    'USUARIO': row[0] or '?',
                    'USUARIO_DNI': row[1] or '?'
                }
            else:
                return {
                    'USUARIO': '?',
                    'USUARIO_DNI': '?'
                }

    def _get_participants_data(self, id_permiviaje: int) -> tuple[Dict[str, Any], Dict[str, List[Dict[str, Any]]]]:
        """
        Get participants data by condition using raw SQL
        Returns both variables and blocks data
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
            blocks_data = {}
            
            # Get number of contratantes for logic
            cursor.execute("""
                SELECT COUNT(*) as num_contratantes
                FROM viaje_contratantes
                WHERE (c_condicontrat = '001' 
                       OR c_condicontrat='003'
                       OR c_condicontrat='004'
                       OR c_condicontrat='005'
                       OR c_condicontrat='010') 
                       AND viaje_contratantes.id_viaje = %s
            """, [id_permiviaje])
            num_contratantes_result = cursor.fetchone()
            num_contratantes = num_contratantes_result[0] if num_contratantes_result else 0
            
            # Get all contratantes for the 'c' block (parents/guardians)
            cursor.execute("""
                SELECT viaje_contratantes.c_condicontrat AS id_condicion,
                       CONCAT(cliente.prinom, ' ', cliente.segnom, ' ', cliente.apepat, ' ', cliente.apemat) AS contratante,
                       tipodocumento.destipdoc AS tipo_documento, tipodocumento.destipdoc AS abreviatura, 
                       cliente.numdoc AS numero_documento, nacionalidades.descripcion AS nacionalidad, 
                       cliente.direccion AS direccion, viaje_contratantes.c_fircontrat, cliente.direccion,
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
                             ELSE '' END) AS edad,
                       cliente.sexo
                FROM viaje_contratantes 
                INNER JOIN cliente ON cliente.numdoc = viaje_contratantes.c_codcontrat
                INNER JOIN tipodocumento ON tipodocumento.idtipdoc = cliente.idtipdoc
                INNER JOIN nacionalidades ON nacionalidades.idnacionalidad = cliente.nacionalidad
                INNER JOIN tipoestacivil ON tipoestacivil.idestcivil = cliente.idestcivil
                LEFT OUTER JOIN profesiones ON profesiones.idprofesion = cliente.idprofesion
                LEFT OUTER JOIN ubigeo ON ubigeo.coddis = cliente.idubigeo
                WHERE (viaje_contratantes.c_condicontrat = '001' 
                       OR viaje_contratantes.c_condicontrat='003'
                       OR viaje_contratantes.c_condicontrat='004'
                       OR viaje_contratantes.c_condicontrat='005'
                       OR viaje_contratantes.c_condicontrat='010') 
                       AND viaje_contratantes.id_viaje = %s
            """, [id_permiviaje])
            
            contratantes = cursor.fetchall()
            contratantes_list = []
            
            for contratante_row in contratantes:
                columns = [col[0] for col in cursor.description]
                contratante_dict = dict(zip(columns, contratante_row))
                
                # Add PHP-style computed fields
                sex = contratante_dict.get('sexo', 'M')
                contratante_dict['identificado'] = 'IDENTIFICADO' if sex == 'M' else 'IDENTIFICADA'
                contratante_dict['domiciliado'] = 'CON DOMICILIO '
                contratante_dict['senor'] = 'SEÑOR' if sex == 'M' else 'SEÑORA'
                contratante_dict['el'] = 'EL' if sex == 'M' else 'LA'
                contratante_dict['don'] = 'DON' if sex == 'M' else 'DOÑA'
                
                # Handle nationality gender
                nacionalidad = contratante_dict.get('nacionalidad', '')
                if nacionalidad:
                    if sex == 'M':
                        contratante_dict['nacionalidad'] = nacionalidad[:-1] + 'O'
                    else:
                        contratante_dict['nacionalidad'] = nacionalidad[:-1] + 'A'
                
                # Add logic for multiple contratantes
                if num_contratantes > 1:
                    contratante_dict['SOLICITANTE'] = 'a los solicitantes'
                    contratante_dict['procede'] = 'Los compareciente proceden'
                else:
                    contratante_dict['SOLICITANTE'] = 'al solicitante' if sex == 'M' else 'a la solicitante'
                    contratante_dict['procede'] = 'El compareciente procede' if sex == 'M' else 'La compareciente procede'
                
                contratantes_list.append(contratante_dict)
            
            # Add contratantes to blocks data
            blocks_data['c'] = contratantes_list
            
            # Add the 'procede' field to the main data based on the first contratante
            if contratantes_list:
                participants_data['procede'] = contratantes_list[0].get('procede', 'El compareciente procede')
                # Also add to the 'c' block data for variable lookup
                for contratante in contratantes_list:
                    if 'procede' not in contratante:
                        contratante['procede'] = contratante.get('procede', 'El compareciente procede')
            else:
                participants_data['procede'] = 'El compareciente procede'
            
            # Debug: Print 'c' block data
            print(f"DEBUG: 'c' block data:")
            for i, cont in enumerate(contratantes_list):
                print(f"  Contratante {i+1}: contratante='{cont.get('contratante', 'N/A')}', procede='{cont.get('procede', 'N/A')}'")
            
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
                                 ELSE '' END) AS edad,
                           cliente.sexo
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
                        
                        # Add PHP-style computed fields
                        sex = participant_dict.get('sexo', 'M')
                        participant_dict['identificado'] = 'IDENTIFICADO' if sex == 'M' else 'IDENTIFICADA'
                        participant_dict['domiciliado'] = 'CON DOMICILIO '
                        participant_dict['senor'] = 'SEÑOR' if sex == 'M' else 'SEÑORA'
                        participant_dict['el'] = 'EL' if sex == 'M' else 'LA'
                        participant_dict['don'] = 'DON' if sex == 'M' else 'DOÑA'
                        
                        # Handle nationality gender
                        nacionalidad = participant_dict.get('nacionalidad', '')
                        if nacionalidad:
                            if sex == 'M':
                                participant_dict['nacionalidad'] = nacionalidad[:-1] + 'O'
                            else:
                                participant_dict['nacionalidad'] = nacionalidad[:-1] + 'A'
                        
                        # Add logic for multiple contratantes
                        if num_contratantes > 1:
                            participant_dict['SOLICITANTE'] = 'a los solicitantes'
                            participant_dict['procede'] = 'Los compareciente proceden'
                        else:
                            participant_dict['SOLICITANTE'] = 'al solicitante' if sex == 'M' else 'a la solicitante'
                            participant_dict['procede'] = 'El compareciente procede' if sex == 'M' else 'La compareciente procede'
                        
                        participants_list.append(participant_dict)
                        
                        # Add individual fields for template
                        for key, value in participant_dict.items():
                            field_name = f"{condicion.upper()}_{key.upper()}"
                            participants_data[field_name] = str(value) if value is not None else ''
                    
                    participants_data[condicion] = participants_list
                    blocks_data[condicion] = participants_list
                else:
                    # Add empty fields for this condition
                    columns = [col[0] for col in cursor.description]
                    for col in columns:
                        field_name = f"{condicion.upper()}_{col.upper()}"
                        participants_data[field_name] = ''
                    
                    participants_data[condicion] = []
                    blocks_data[condicion] = []
            
            # Add logic for determining participant types
            padre_count = len(blocks_data.get('padre', []))
            madre_count = len(blocks_data.get('madre', []))
            apoderado_count = len(blocks_data.get('apoderado', []))
            tutor_count = len(blocks_data.get('tutor', []))
            
            if padre_count != 0 and madre_count != 0:
                condicion = 'PADRES'
                manifiesta = 'MANIFIESTAN'
                losella_padres = 'LOS PADRES'
            elif padre_count != 0:
                condicion = 'PADRE'
                manifiesta = 'MANIFIESTA'
                losella_padres = 'EL PADRE'
            elif madre_count != 0:
                condicion = 'MADRE'
                manifiesta = 'MANIFIESTA'
                losella_padres = 'LA MADRE'
            elif apoderado_count != 0:
                condicion = 'APODERADO'
                manifiesta = 'MANIFIESTA'
                losella_padres = 'EL APODERADO'
            elif tutor_count != 0:
                condicion = 'TUTOR'
                manifiesta = 'MANIFIESTA'
                losella_padres = ''
            else:
                condicion = 'TESTIGO'
                manifiesta = 'MANIFIESTA'
                losella_padres = ''
            
            participants_data['CONDICION'] = condicion
            participants_data['MANIFIESTA'] = manifiesta
            participants_data['LOSELLA_PADRES'] = losella_padres if losella_padres else 'SIN DATO'
            
            # Add the 'procede' field based on the first contratante
            if contratantes_list:
                participants_data['procede'] = contratantes_list[0].get('procede', 'El compareciente procede')
            else:
                participants_data['procede'] = 'El compareciente procede'
            
            # Get minors (children) data - separate query like PHP
            cursor.execute("""
                SELECT viaje_contratantes.c_condicontrat AS id_condicion,
                       CONCAT(cliente.prinom, ' ', cliente.segnom, ' ', cliente.apepat, ' ', cliente.apemat) AS contratante,
                       tipodocumento.destipdoc AS tipo_documento, tipodocumento.destipdoc AS abreviatura,
                       cliente.numdoc AS numero_documento, nacionalidades.descripcion AS nacionalidad, 
                       cliente.direccion AS direccion, viaje_contratantes.c_fircontrat, cliente.direccion,
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
                             ELSE '' END) AS edad,
                       cliente.sexo
                FROM viaje_contratantes 
                INNER JOIN cliente ON cliente.numdoc = viaje_contratantes.c_codcontrat
                INNER JOIN tipodocumento ON tipodocumento.idtipdoc = cliente.idtipdoc
                INNER JOIN nacionalidades ON nacionalidades.idnacionalidad = cliente.nacionalidad
                INNER JOIN tipoestacivil ON tipoestacivil.idestcivil = cliente.idestcivil
                LEFT OUTER JOIN profesiones ON profesiones.idprofesion = cliente.idprofesion
                LEFT OUTER JOIN ubigeo ON ubigeo.coddis = cliente.idubigeo
                WHERE viaje_contratantes.c_condicontrat = '002' AND viaje_contratantes.id_viaje = %s
            """, [id_permiviaje])
            
            minors = cursor.fetchall()
            minors_list = []
            all_female = True
            i = 1
            
            for minor_row in minors:
                columns = [col[0] for col in cursor.description]
                minor_dict = dict(zip(columns, minor_row))
                
                sex = minor_dict.get('sexo', 'M')
                minor_dict['identificado'] = 'IDENTIFICADO' if sex == 'M' else 'IDENTIFICADA'
                
                if sex == 'M':
                    all_female = False
                
                # Add y_coma logic
                if len(minors) == i:
                    minor_dict['y_coma'] = '.'
                elif (len(minors) - 1) == i:
                    minor_dict['y_coma'] = 'Y'
                else:
                    minor_dict['y_coma'] = ','
                
                minors_list.append(minor_dict)
                i += 1
            
            # Add minors to blocks data
            blocks_data['m'] = minors_list
            
            # Get signature data (f block) - all contratantes
            cursor.execute("""
                SELECT viaje_contratantes.c_condicontrat AS id_condicion,
                       CONCAT(cliente.prinom, ' ', cliente.segnom, ' ', cliente.apepat, ' ', cliente.apemat) AS contratante,
                       tipodocumento.destipdoc AS tipo_documento, tipodocumento.destipdoc AS abreviatura, 
                       cliente.numdoc AS numero_documento, nacionalidades.descripcion AS nacionalidad, 
                       cliente.direccion AS direccion, viaje_contratantes.c_fircontrat, cliente.direccion,
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
                             ELSE '' END) AS edad,
                       cliente.sexo
                FROM viaje_contratantes 
                INNER JOIN cliente ON cliente.numdoc = viaje_contratantes.c_codcontrat
                INNER JOIN tipodocumento ON tipodocumento.idtipdoc = cliente.idtipdoc
                INNER JOIN nacionalidades ON nacionalidades.idnacionalidad = cliente.nacionalidad
                INNER JOIN tipoestacivil ON tipoestacivil.idestcivil = cliente.idestcivil
                LEFT OUTER JOIN profesiones ON profesiones.idprofesion = cliente.idprofesion
                LEFT OUTER JOIN ubigeo ON ubigeo.coddis = cliente.idubigeo
                WHERE (viaje_contratantes.c_condicontrat = '001' 
                       OR viaje_contratantes.c_condicontrat='003'
                       OR viaje_contratantes.c_condicontrat='004'
                       OR viaje_contratantes.c_condicontrat='005'
                       OR viaje_contratantes.c_condicontrat='010') 
                       AND viaje_contratantes.id_viaje = %s
            """, [id_permiviaje])
            
            signatures = cursor.fetchall()
            signatures_list = []
            x = 1
            
            for signature_row in signatures:
                columns = [col[0] for col in cursor.description]
                signature_dict = dict(zip(columns, signature_row))
                
                # Add y_coma logic for signatures
                if len(signatures) == x:
                    signature_dict['y_coma'] = '.'
                elif (len(signatures) - 1) == x:
                    signature_dict['y_coma'] = 'Y'
                else:
                    signature_dict['y_coma'] = ','
                
                signatures_list.append(signature_dict)
                x += 1
            
            # Add signatures to blocks data
            blocks_data['f'] = signatures_list
            
            # Debug: Print signature data
            print(f"DEBUG: Signature data for 'f' block:")
            for i, sig in enumerate(signatures_list):
                print(f"  Signature {i+1}: contratante='{sig.get('contratante', 'N/A')}', abreviatura='{sig.get('abreviatura', 'N/A')}', numero_documento='{sig.get('numero_documento', 'N/A')}'")
                print(f"    Full signature data: {sig}")
            
            # Add logic for A_EL_LOS, A_S, A_N
            if len(signatures_list) == 1:
                participants_data['A_EL_LOS'] = 'EL'
                participants_data['A_S'] = ''
                participants_data['A_N'] = ''
            else:
                participants_data['A_EL_LOS'] = 'LOS'
                participants_data['A_S'] = 'S'
                participants_data['A_N'] = 'N'
            
            # Determine EL_LA_LOS, HIJO, MENOR, AUTORIZA based on minors
            if len(minors_list) == 1:
                sex = minors_list[0].get('sexo', 'M')
                if sex == 'M':
                    participants_data['EL_LA_LOS'] = 'EL'
                    participants_data['HIJO'] = 'HIJO'
                else:
                    participants_data['EL_LA_LOS'] = 'LA'
                    participants_data['HIJO'] = 'HIJA'
                participants_data['MENOR'] = 'SU MENOR'
                participants_data['AUTORIZA'] = 'AUTORIZA'
            else:
                if all_female:
                    participants_data['EL_LA_LOS'] = 'LAS'
                    participants_data['HIJO'] = 'HIJAS'
                else:
                    participants_data['EL_LA_LOS'] = 'LOS'
                    participants_data['HIJO'] = 'HIJOS'
                participants_data['MENOR'] = 'SUS MENORES'
                participants_data['AUTORIZA'] = 'AUTORIZAN'
            
            return participants_data, blocks_data

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

    def _process_document(self, template_bytes: bytes, data: Dict[str, Any], blocks: Dict[str, List[Dict[str, Any]]]) -> Document:
        """
        Process the document template with data using TBS-like approach
        """
        # Create document from template bytes
        buffer = io.BytesIO(template_bytes)
        doc = Document(buffer)
        
        # Set up TBS processor
        self.tbs_processor.set_data(data)
        self.tbs_processor.set_blocks(blocks)
        
        # Process the document
        return self.tbs_processor.process_document(doc)

    def _replace_placeholders_in_paragraph(self, paragraph, data: Dict[str, str]):
        """
        Replace placeholders in a paragraph with red tinting, following the NonContentiousDocumentService approach
        """
        # Get the full text of the paragraph
        full_text = paragraph.text
        modified_text = full_text
        
        # Replace all placeholders in the text
        for key, value in data.items():
            placeholder = f'{{{{{key}}}}}'
            if placeholder in modified_text:
                print(f"DEBUG: Replacing {placeholder} with '{value}'")
                modified_text = modified_text.replace(placeholder, str(value))
        
        # If the text changed, rebuild the paragraph with proper coloring
        if modified_text != full_text:
            print(f"DEBUG: Text changed from '{full_text[:50]}...' to '{modified_text[:50]}...'")
            # Clear all runs
            paragraph.clear()
            
            # Split the text by all possible placeholders to identify what was replaced
            import re
            placeholder_pattern = re.compile(r'\{\{[A-Z0-9_]+\}\}')
            
            # Find all placeholders in the original text
            original_placeholders = placeholder_pattern.findall(full_text)
            
            # Build the new text with coloring
            current_pos = 0
            for match in placeholder_pattern.finditer(full_text):
                placeholder = match.group()
                start_pos = match.start()
                end_pos = match.end()
                
                # Add text before this placeholder
                if start_pos > current_pos:
                    text_before = full_text[current_pos:start_pos]
                    if text_before:
                        paragraph.add_run(text_before)
                
                # Find the replacement value
                replacement = None
                for key, value in data.items():
                    if f'{{{{{key}}}}}' == placeholder:
                        replacement = value
                        break
                
                if replacement:
                    # Add replacement in red
                    red_run = paragraph.add_run(str(replacement))
                    red_run.font.color.rgb = RGBColor(255, 0, 0)  # Red color
                else:
                    # Keep original placeholder if no replacement found
                    paragraph.add_run(placeholder)
                
                current_pos = end_pos
            
            # Add remaining text after the last placeholder
            if current_pos < len(full_text):
                remaining_text = full_text[current_pos:]
                if remaining_text:
                    paragraph.add_run(remaining_text)
        else:
            print(f"DEBUG: No changes detected in paragraph: '{full_text[:50]}...'")
            # If no changes in full text, try replacing in individual runs
            for run in paragraph.runs:
                run_text = run.text
                modified_run_text = run_text
                
                for key, value in data.items():
                    placeholder = f'{{{{{key}}}}}'
                    if placeholder in modified_run_text:
                        print(f"DEBUG: Replacing in run: {placeholder} -> {value}")
                        modified_run_text = modified_run_text.replace(placeholder, str(value))
                
                if modified_run_text != run_text:
                    run.text = modified_run_text
                    # Color the entire run red since we can't easily identify just the replacement
                    run.font.color.rgb = RGBColor(255, 0, 0)  # Red color

    def _process_document_with_red_tinting(self, template_bytes: bytes, data: Dict[str, Any], blocks: Dict[str, List[Dict[str, Any]]]) -> Document:
        """
        Process the document template with data and red tinting using TBS-style processing
        """
        # Create document from template bytes
        buffer = io.BytesIO(template_bytes)
        doc = Document(buffer)
        
        # Process paragraphs with TBS-style processing
        for paragraph in doc.paragraphs:
            self._process_paragraph_tbs_style(paragraph, data, blocks)
        
        # Process tables with TBS-style processing
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        self._process_paragraph_tbs_style(paragraph, data, blocks)
        
        return doc

    def _process_paragraph_tbs_style(self, paragraph, data: Dict[str, Any], blocks: Dict[str, List[Dict[str, Any]]]):
        """
        Process a paragraph with TBS-style placeholders and selective red tinting
        """
        original_text = paragraph.text
        processed_text = original_text
        
        # Process blocks first (like {c.block=begin;}...{c.block=end;})
        processed_text = self._process_blocks_tbs_style(processed_text, blocks)
        
        # Process variables (like {var.KARDEX})
        processed_text = self._process_variables_tbs_style(processed_text, data)
        
        # If text changed, rebuild paragraph with selective red tinting
        if processed_text != original_text:
            print(f"DEBUG: Processing paragraph: '{original_text[:50]}...' -> '{processed_text[:50]}...'")
            paragraph.clear()
            
            # Apply selective red tinting - only replaced parts are red
            self._apply_selective_red_tinting(paragraph, original_text, processed_text, data, blocks)

    def _apply_selective_red_tinting(self, paragraph, original_text: str, processed_text: str, data: Dict[str, Any], blocks: Dict[str, List[Dict[str, Any]]]):
        """
        Apply selective red tinting - only replaced values are red
        """
        import re
        
        # Find all TBS-style placeholders in original text
        var_pattern = r'\{var\.([A-Z0-9_]+)\}'
        block_pattern = r'\{([a-z])[.;]block=begin;\}(.*?)\{\1[.;]block=end;\}'
        
        # Collect all replacements
        replacements = {}
        
        # Find variable replacements
        for match in re.finditer(var_pattern, original_text):
            var_name = match.group(1)
            placeholder = match.group(0)
            if var_name in data:
                replacements[placeholder] = str(data[var_name])
        
        # Find block replacements
        for match in re.finditer(block_pattern, original_text, re.DOTALL):
            prefix = match.group(1)
            block_content = match.group(2)
            placeholder = match.group(0)
            
            if prefix in blocks and blocks[prefix]:
                # Process block content
                results = []
                for item in blocks[prefix]:
                    item_text = block_content
                    for key, value in item.items():
                        item_placeholder = f'{{{prefix}.{key}}}'
                        if item_placeholder in item_text:
                            item_text = item_text.replace(item_placeholder, str(value))
                    results.append(item_text)
                replacements[placeholder] = '\n'.join(results)
        
        # Build the new text with selective coloring
        current_pos = 0
        text_to_process = original_text
        
        # Process all replacements in order
        all_placeholders = list(replacements.keys())
        all_placeholders.sort(key=lambda x: text_to_process.find(x))
        
        for placeholder in all_placeholders:
            start_pos = text_to_process.find(placeholder)
            if start_pos == -1:
                continue
                
            end_pos = start_pos + len(placeholder)
            replacement = replacements[placeholder]
            
            # Add text before this placeholder
            if start_pos > current_pos:
                text_before = text_to_process[current_pos:start_pos]
                if text_before:
                    paragraph.add_run(text_before)
            
            # Add replacement in red
            red_run = paragraph.add_run(replacement)
            red_run.font.color.rgb = RGBColor(255, 0, 0)  # Red color
            
            current_pos = end_pos
        
        # Add remaining text after the last placeholder
        if current_pos < len(text_to_process):
            remaining_text = text_to_process[current_pos:]
            if remaining_text:
                paragraph.add_run(remaining_text)

    def _process_blocks_tbs_style(self, text: str, blocks: Dict[str, List[Dict[str, Any]]]) -> str:
        """
        Process TBS-style blocks like {c.block=begin;}...{c.block=end;} and {m;block=begin;}...{m;block=end;}
        """
        import re
        
        # Pattern to match blocks: {prefix.block=begin;}...{prefix.block=end;} or {prefix;block=begin;}...{prefix;block=end;}
        block_pattern = r'\{([a-z])[.;]block=begin;\}(.*?)\{\1[.;]block=end;\}'
        
        def replace_block(match):
            prefix = match.group(1)  # e.g., 'c', 'f', 'm'
            block_content = match.group(2)
            
            print(f"DEBUG: Processing block '{prefix}' with content: {block_content[:50]}...")
            print(f"DEBUG: Available blocks: {list(blocks.keys())}")
            print(f"DEBUG: Block '{prefix}' data: {blocks.get(prefix, 'NOT FOUND')}")
            
            if prefix in blocks and blocks[prefix]:
                # Process each item in the block
                results = []
                for item in blocks[prefix]:
                    # Replace placeholders in block content with item data
                    item_text = block_content
                    for key, value in item.items():
                        placeholder = f'{{{prefix}.{key}}}'
                        if placeholder in item_text:
                            print(f"DEBUG: Replacing {placeholder} with '{value}'")
                            item_text = item_text.replace(placeholder, str(value))
                    results.append(item_text)
                
                # Join all results
                final_result = '\n'.join(results)
                print(f"DEBUG: Final result for block '{prefix}': {final_result[:100]}...")
                return final_result
            else:
                print(f"DEBUG: No data found for block '{prefix}'")
                return ''  # Remove block if no data
        
        return re.sub(block_pattern, replace_block, text, flags=re.DOTALL)

    def _process_variables_tbs_style(self, text: str, data: Dict[str, Any]) -> str:
        """
        Process TBS-style variables like {var.KARDEX}, {var.LETRA_FECHA_INGRESO}
        """
        import re
        
        def replace_variable(match):
            var_name = match.group(1)
            if var_name in data:
                value = data[var_name]
                print(f"DEBUG: Replacing {var_name} with '{value}'")
                return str(value)
            else:
                print(f"DEBUG: Variable {var_name} not found in data")
                return match.group(0)  # Keep original if not found
        
        # Pattern for {var.VARIABLE} style variables
        var_pattern = r'\{var\.([A-Z0-9_]+)\}'
        return re.sub(var_pattern, replace_variable, text)

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
