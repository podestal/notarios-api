from django.db import connection
from django.http import HttpResponse, JsonResponse
from docx import Document
import io
import time
from decimal import Decimal
from datetime import datetime
import locale
import re
from docx.shared import RGBColor
import gc
from typing import Dict
from functools import lru_cache
import os
from rest_framework.response import Response
import boto3
from botocore.config import Config

from notaria import models

# from .utils import get_s3_client
from jinja2 import Template


class NumberToLetterConverter:
    """
    Utility class to convert numbers and dates to letter format in Spanish
    """

    def __init__(self):
        # Set locale for Spanish date formatting
        try:
            locale.setlocale(locale.LC_TIME, "es_ES.UTF-8")
        except:
            try:
                locale.setlocale(locale.LC_TIME, "es_ES")
            except:
                print("WARNING: Spanish locale not available, falling back to default")

    def number_to_letters(self, number) -> str:
        """Convert number to words in Spanish"""
        try:
            number = int(number)
        except (ValueError, TypeError):
            print(f"WARNING: Invalid number value: {number}")
            return str(number)

        UNITS = ["", "UNO", "DOS", "TRES", "CUATRO", "CINCO", "SEIS", "SIETE", "OCHO", "NUEVE"]
        TENS = [
            "",
            "DIEZ",
            "VEINTE",
            "TREINTA",
            "CUARENTA",
            "CINCUENTA",
            "SESENTA",
            "SETENTA",
            "OCHENTA",
            "NOVENTA",
        ]
        TEENS = [
            "DIEZ",
            "ONCE",
            "DOCE",
            "TRECE",
            "CATORCE",
            "QUINCE",
            "DIECISEIS",
            "DIECISIETE",
            "DIECIOCHO",
            "DIECINUEVE",
        ]
        HUNDREDS = [
            "",
            "CIENTO",
            "DOSCIENTOS",
            "TRESCIENTOS",
            "CUATROCIENTOS",
            "QUINIENTOS",
            "SEISCIENTOS",
            "SETECIENTOS",
            "OCHOCIENTOS",
            "NOVECIENTOS",
        ]

        if number == 0:
            return "CERO"

        if number < 10:
            return UNITS[number]

        if number < 20:
            return TEENS[number - 10]

        if number < 100:
            tens = number // 10
            units = number % 10
            if units == 0:
                return TENS[tens]
            return f"{TENS[tens]} Y {UNITS[units]}"

        if number < 1000:
            hundreds = number // 100
            rest = number % 100
            if rest == 0:
                return HUNDREDS[hundreds]
            return f"{HUNDREDS[hundreds]} {self.number_to_letters(rest)}"

        return str(number)

    def date_to_letters(self, date_str) -> str:
        """Convert date to words in Spanish"""
        if not date_str:
            print(f"WARNING: Empty date value")
            return ""

        try:
            if isinstance(date_str, str):
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            else:
                date_obj = date_str

            day = self.number_to_letters(date_obj.day)
            month = date_obj.strftime("%B").upper()
            year = self.number_to_letters(date_obj.year)

            return f"{day} DE {month} DEL {year}"
        except Exception as e:
            print(f"ERROR: Failed to convert date to letters: {e}")
            return str(date_str)

    def money_to_letters(self, currency: str, amount: Decimal) -> str:
        """Convert money amount to words in Spanish"""
        try:
            integer_part = int(amount)
            decimal_part = int((amount % 1) * 100)

            integer_text = self.number_to_letters(integer_part)
            decimal_text = self.number_to_letters(decimal_part)

            if currency == "SOLES":
                return f"{integer_text} SOLES CON {decimal_text} CÉNTIMOS"
            elif currency == "DOLARES N.A.":
                return f"{integer_text} DÓLARES AMERICANOS CON {decimal_text} CENTAVOS"
            else:
                return f"{integer_text} {currency} CON {decimal_text} CENTAVOS"
        except Exception as e:
            print(f"ERROR: Failed to convert money to letters: {e}")
            return f"{amount} {currency}"


class EscrituraDocumentService:
    """
    Service to generate escritura publica documents based on PHP legacy script
    """

    def __init__(self):
        self.letras = NumberToLetterConverter()
        print("DEBUG: EscrituraPublicaService initialized")

    def generate_escritura_publica_document(self, template_id, kardex, action, mode):
        """
        Main entry point for generating escritura publica documents

        FLOW:
        1. Get template information from database (filename, etc.)
        2. Download the template from R2 storage
        3. Fetch data from database (consulta_escritura)
        4. Process data into sections (documento, vehiculos, pagos, contratantes)
        5. Replace placeholders in template
        6. Upload to R2
        7. Return HTTP response

        PARAMETERS:
        - template_id: ID of the template in the database
        - kardex: Document identifier (e.g., "KAR6508-2025")
        - action: Action type ("generate", "actualizar", "parte")
        - mode: Response mode ("download" or "open")
        """
        print(f"DEBUG: Starting document generation for kardex: {kardex}")

        # STEP 1: Get template info
        template_info = self._get_template_info(template_id)
        print(f"DEBUG: Template info: {template_info['filename']}")

        # STEP 2: Download template from R2
        template_bytes = self._get_template_from_r2(template_id, template_info["filename"])
        print(f"DEBUG: Template downloaded: {len(template_bytes)} bytes")

        # STEP 3: Fetch ALL data from database (mirrors PHP consulta_escritura)
        # TODO: Implement this - fetch all data in ONE query
        raw_data = self._consulta_escritura(kardex, action, template_id)
        print(f"DEBUG: Data fetched from database")

        # STEP 4: Process data into sections (mirrors PHP functions)
        # TODO: Process document basic data (kardex, date, user, etc.)
        data_documento = self._get_data_documento(raw_data)

        # TODO: Process vehicle data
        data_vehiculos = self._get_data_vehiculos(raw_data)

        # TODO: Process payment data
        data_pagos = self._get_data_pagos(raw_data)

        # TODO: Process contractors data (most complex part)
        data_contratantes = self._get_data_contratantes(raw_data)

        # TODO: Process escrituracion data (folio, papel)
        data_escrituracion = self._get_data_escrituracion(raw_data)

        # STEP 5: Combine all data (mirrors PHP combining arrays)
        # TODO: Merge all data dictionaries into one
        final_data = self._combine_all_data(
            data_documento, data_vehiculos, data_pagos, data_contratantes, data_escrituracion
        )

        # STEP 6: Replace placeholders in template
        # TODO: Load template and replace {{PLACEHOLDERS}}
        doc = self._replace_placeholders(template_bytes, final_data)
        print(f"DEBUG: Placeholders replaced")

        # STEP 7: Clean up unfilled placeholders
        # TODO: Remove or hide unfilled {{PLACEHOLDERS}}
        self._clean_unfilled_placeholders(doc)

        # STEP 8: Upload to R2
        # TODO: Save document to R2 storage
        self._upload_to_r2(doc, kardex)

        # STEP 9: Return HTTP response
        filename = f"__PROY__{kardex}.docx"
        return self._create_response(doc, filename, kardex, mode)

    def _get_template_info(self, template_id):
        """
        Get template information from database
        """
        print(f"DEBUG: Getting template info for template_id: {template_id}")

        template = models.TplTemplate.objects.get(pktemplate=template_id)
        return {"filename": template.filename}

    def _get_template_from_r2(self, template_id, filename):
        """
        Get template from R2 storage
        """
        print(f"DEBUG: Downloading template from R2: {filename}")

        s3 = boto3.client(
            "s3",
            endpoint_url=os.environ.get("CLOUDFLARE_R2_ENDPOINT"),
            aws_access_key_id=os.environ.get("CLOUDFLARE_R2_ACCESS_KEY"),
            aws_secret_access_key=os.environ.get("CLOUDFLARE_R2_SECRET_KEY"),
            config=Config(signature_version="s3v4"),
            region_name="auto",
        )

        object_key = f"rodriguez-zea/plantillas/{filename}"

        try:
            response = s3.get_object(Bucket=os.environ.get("CLOUDFLARE_R2_BUCKET"), Key=object_key)
            template_bytes = response["Body"].read()
            print(f"DEBUG: Template downloaded successfully: {len(template_bytes)} bytes")
            return template_bytes
        except Exception as e:
            print(f"ERROR: Failed to download template from R2: {e}")
            raise

    def _create_response(self, doc, filename, kardex, mode):
        """
        Create HTTP response with the document
        """
        print(f"DEBUG: Creating response with mode: {mode}")

        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)

        if mode == "open":
            response = JsonResponse(
                {
                    "status": "success",
                    "mode": "open",
                    "filename": filename,
                    "kardex": kardex,
                    "message": "Document generated and ready to open in Word",
                }
            )
            response["Access-Control-Allow-Origin"] = "*"
            return response
        else:
            response = HttpResponse(
                buffer.read(),
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            response["Content-Disposition"] = f'inline; filename="{filename}"'
            response["Content-Length"] = str(buffer.getbuffer().nbytes)
            response["Access-Control-Allow-Origin"] = "*"
            return response

    # ========================================
    # PHASE 1: DATA FETCHING FROM DATABASE
    # ========================================

    def _consulta_escritura(self, num_kardex, action, template_id):
        """
        MAIN SQL QUERY - Fetch ALL data from database in ONE query
        Mirrors: PHP consulta_escritura()

        TASK:
        - Execute raw SQL query with all LEFT JOINS
        - Get kardex, contratantes, vehiculos, pagos, empresas in ONE query
        - Return dictionary with all raw data

        TABLES NEEDED:
        - kardex (main table)
        - contratantesxacto, contratantes, cliente2 (contractors)
        - detallevehicular (vehicle data)
        - patrimonial, detallemediopago (payment data)
        - nacionalidades, tipodocumento, tipoestacivil, ubigeo (lookups)
        - tb_abogado, usuarios (notary/user data)

        SOLUTION: See app/ducumentation/services.py line 3032-3164
        """
        print(f"DEBUG: _consulta_escritura for kardex: {num_kardex}")

        #########################################################
        """
        Get idtipoacto from kardex we need to use the id tipoacto from the parameters and do not query the database again
        """
        idtipoacto = models.Kardex.objects.get(kardex=num_kardex).idtipkar
        #########################################################

        query = """
            SELECT k.idkardex as id_kardex,
                k.kardex,
                k.numescritura as numero_escritura,
                k.fechaescritura as fecha_escritura,
                k.txa_minuta as registro_escritura,
                CURRENT_DATE() as fecha_generado,
                k.fechaconclusion as fecha_conclusion,
                k.numminuta as numero_minuta,
                k.kardexconexo as kardex_conexo,
                k.folioini as folio_inicial, 
                k.foliofin as folio_final, 
                k.papelini as papel_inicial, 
                k.papelfin as papel_final,
                (SELECT desacto FROM tiposdeacto WHERE idtipoacto=%s) as acto,
                (SELECT fileName FROM tpl_template WHERE pkTemplate=%s) as plantilla,
                (SELECT urlTemplate FROM tpl_template WHERE pkTemplate=%s) as url_plantilla,
                k.fechaingreso as fecha_ingreso,
                k.responsable_new as usuario,
                abo.razonsocial as abogado,
                abo.matricula as matricula,
                abo.sede_colegio as sede_colegio,
                usu.dni as dni_usuario,
                GROUP_CONCAT(c2.idcliente) as id_cliente,
                GROUP_CONCAT(IF(c2.conyuge='','NO',c2.conyuge)) as id_conyuge,
                GROUP_CONCAT(cxa.idcontratante) as id_contratante,
                GROUP_CONCAT(TRIM(CONCAT(IFNULL(c2.prinom, ''), ' ', IFNULL(c2.segnom, ''), IF(c2.segnom='','',' ') ,IFNULL(c2.apepat, ''), ' ',IFNULL(c2.apemat, ''),
            IFNULL(c2.razonsocial, '')))) AS nombres,
                GROUP_CONCAT(cxa.uif) as uif,
                GROUP_CONCAT(ac.condicion) as condicion,
                GROUP_CONCAT(IF(n.descripcion IS NULL OR n.descripcion='','EMPRESA',n.descripcion)) as nacionalidad,
                GROUP_CONCAT(td.destipdoc) as tipo_documento,
                GROUP_CONCAT(c2.numdoc) AS numero_documento,
                GROUP_CONCAT(UPPER(c2.profesion_plantilla)) AS ocupacion,
                GROUP_CONCAT(IF(tec.desestcivil IS NULL OR tec.desestcivil='','EMPRESA',tec.desestcivil)) as estado_civil,
                GROUP_CONCAT(IF(c2.tipper='N',c2.direccion,c2.domfiscal) SEPARATOR ',,') as direccion,
                GROUP_CONCAT(IFNULL(u.codpto, '')) as codigo_departamento,
                GROUP_CONCAT(IFNULL(u.coddis, '')) as codigo_distrito,
                GROUP_CONCAT(IFNULL(u.codprov, '')) as codigo_provincia,
                GROUP_CONCAT(IFNULL(IF(SUBSTRING_INDEX(c2.ubigeo_plantilla, '/', -1)='',u.nomdis,SUBSTRING_INDEX(c2.ubigeo_plantilla, '/', -1)),(IFNULL(u.nomdis, '')))) AS distrito,
                GROUP_CONCAT(IFNULL(u.nomprov, '')) as provincia,
                GROUP_CONCAT(IFNULL(u.nomdpto, '')) as departamento,
                GROUP_CONCAT(c2.sexo) AS sexo,
                GROUP_CONCAT(c2.tipper) as tipo_persona,
                GROUP_CONCAT(IF(cn.firma = '0', 'NO', 'SI')) AS firma,
                GROUP_CONCAT(cn.firma) as n_firma,
                GROUP_CONCAT(cn.tiporepresentacion) AS tipo_representacion,
                dv.numplaca AS placa, 
                dv.marca AS marca, 
                dv.clase AS clase,
                dv.anofab AS anio,
                dv.numserie AS serie, 
                dv.color AS color,
                dv.motor AS motor, 
                dv.modelo AS modelo, 
                dv.carroceria AS carroceria,
                dv.pregistral as partida,
                dv.fecinsc AS fecha_inscripcion,
                dv.combustible AS combustible,
                UPPER(sr.dessede) AS sede,
                UPPER(sr.num_zona) AS numero_zona,
                pat.importetrans AS precio , 
                pat.idmon AS moneda,
                pat.exhibiomp, 
                pat.idoppago, 
                uif.descripcion AS medio_pago, 
                mon.simbolo as simbolo_moneda,
                mon.desmon as descripcion_moneda,
                mp.desmpagos as descripcion_medio_pago,
                mp.sunat as sunat_medio_pago,
                GROUP_CONCAT(cnr.idcontratanterp) as id_empresa,
                GROUP_CONCAT(TRIM(CONCAT(IFNULL(cr2.prinom, ''), ' ', IFNULL(cr2.segnom, ''), IF(cr2.segnom='','',' ') ,IFNULL(cr2.apepat, ''), ' ',IFNULL(cr2.apemat, ''),
            IFNULL(cr2.razonsocial, '')))) AS nombre_empresa,
                GROUP_CONCAT(cr2.tipper) as tipo_persona_empresa,
                GROUP_CONCAT(acr.condicion) as condicion_empresa,
                GROUP_CONCAT(tdr.destipdoc) as tipo_documento_empresa,
                GROUP_CONCAT(cr2.numdoc) AS numero_documento_empresa,
                GROUP_CONCAT(cr2.domfiscal) as domicilio_empresa,
                GROUP_CONCAT(ur.nomdis) as distrito_empresa,
                GROUP_CONCAT(ur.nomprov) as provincia_empresa,
                GROUP_CONCAT(ur.nomdpto) as departamento_empresa,
                GROUP_CONCAT(srr2.zona_depar SEPARATOR ',,') as oficina_registral,
                GROUP_CONCAT(cr2.numpartida) as numero_partida,
                dmp.foperacion as fecha_operacion,
                dmp.documentos as documentos,
                ban.desbanco as banco
            FROM kardex as k
            LEFT JOIN tb_abogado as abo on abo.idabogado=k.idabogado
            LEFT JOIN usuarios as usu on usu.idusuario=k.idusuario
            LEFT JOIN contratantesxacto as cxa on cxa.kardex=k.kardex
            LEFT JOIN actocondicion as ac ON cxa.idcondicion=ac.idcondicion
            LEFT JOIN contratantes cn ON cxa.idcontratante = cn.idcontratante
            LEFT JOIN cliente2 as c2 on c2.idcontratante=cxa.idcontratante
            LEFT JOIN nacionalidades as n on n.idnacionalidad=c2.nacionalidad
            LEFT JOIN tipodocumento as td ON td.idtipdoc = c2.idtipdoc
            LEFT OUTER JOIN tipoestacivil as tec ON tec.idestcivil = c2.idestcivil
            LEFT OUTER JOIN ubigeo as u ON u.coddis = c2.idubigeo
            LEFT JOIN detallevehicular as dv ON dv.kardex=k.kardex
            LEFT JOIN sedesregistrales as sr ON sr.idsedereg=dv.idsedereg
            LEFT JOIN patrimonial as pat ON pat.kardex=k.kardex
            LEFT JOIN fpago_uif as uif ON uif.id_fpago = pat.fpago
            LEFT JOIN monedas as mon ON mon.idmon = pat.idmon
            LEFT JOIN detallemediopago as dmp ON pat.kardex = dmp.kardex
            LEFT JOIN mediospago as mp ON dmp.codmepag = mp.codmepag
            LEFT JOIN contratantes as cnr ON cxa.idcontratante = cnr.idcontratante
            LEFT JOIN contratantesxacto as cxar on cxar.idcontratante=cnr.idcontratanterp
            LEFT JOIN actocondicion as acr ON acr.idcondicion=cxar.idcondicion
            LEFT JOIN cliente2 as cr2 on cr2.idcontratante=cnr.idcontratanterp
            left JOIN nacionalidades as nr on nr.idnacionalidad=cr2.nacionalidad
            LEFT JOIN sedesregistrales as srr2 on srr2.idsedereg=cr2.idsedereg
            LEFT JOIN tipodocumento as tdr ON tdr.idtipdoc = cr2.idtipdoc
            LEFT OUTER JOIN tipoestacivil as tecr ON tecr.idestcivil = cr2.idestcivil
            LEFT OUTER JOIN ubigeo as ur ON ur.coddis = cr2.idubigeo
            LEFT JOIN  bancos as ban ON ban.idbancos=dmp.idbancos
            WHERE k.kardex=%s and (c2.tipper='N')
            GROUP BY k.idkardex, dmp.detmp LIMIT 1
        """

        with connection.cursor() as cursor:
            print(f"DEBUG: Executing SQL query ...")
            cursor.execute(query, [idtipoacto, template_id, template_id, num_kardex])
            desc = cursor.description
            row = cursor.fetchone()
            if not row:
                return None
            return dict(zip([col[0] for col in desc], row))

    # ========================================
    # PHASE 2: DATA PROCESSING METHODS
    # ========================================

    def _get_data_documento(self, raw_data):
        """
        Process basic document data
        Mirrors: PHP get_data_documento()

        TASK:
        - Extract kardex number, date, user info
        - Convert numbers to letters (NRO_ESC)
        - Convert dates to letters (F, F_IMPRESION)
        - Handle sede colegio (CAP., CAA.)

        RETURNS: Dictionary with keys like:
        - NRO_ESC: "123(CIENTO VEINTITRES)"
        - K: "KAR6508-2025"
        - F: "DIEZ DE ENERO DEL DOS MIL VEINTICINCO"
        - USUARIO: "Juan Perez"
        - etc.

        SOLUTION: See app/ducumentation/services.py line 3166-3201
        """
        print(f"DEBUG: Processing document data")

        # TODO: Extract numero_escritura, fecha_escritura from raw_data
        # TODO: Use self.letras.number_to_letters() for numbers
        # TODO: Use self.letras.date_to_letters() for dates
        # TODO: Handle sede_colegio logic
        # TODO: Return dictionary

        pass  # Remove and implement

    def _get_data_vehiculos(self, raw_data):
        """
        Process vehicle data
        Mirrors: PHP get_data_vehiculos()

        TASK:
        - Extract vehicle info (placa, marca, modelo, etc.)
        - Convert all to uppercase
        - Handle sede registral parsing

        RETURNS: Dictionary with keys like:
        - PLACA: "ABC-123"
        - MARCA: "TOYOTA"
        - MODELO: "COROLLA"
        - etc.

        SOLUTION: See app/ducumentation/services.py line 3203-3229
        """
        print(f"DEBUG: Processing vehicle data")

        # TODO: Extract vehicle fields from raw_data
        # TODO: Convert to uppercase
        # TODO: Parse sede registral
        # TODO: Return dictionary

        pass  # Remove and implement

    def _get_data_pagos(self, raw_data):
        """
        Process payment data
        Mirrors: PHP get_data_pagos()

        TASK:
        - Extract payment amount and currency
        - Convert amount to letters
        - Handle sunat_medio_pago logic (switch statement)
        - Generate payment text based on payment method

        RETURNS: Dictionary with keys like:
        - MONTO: "2000.00"
        - MONTO_LETRAS: "DOS MIL SOLES"
        - MED_PAGO: "EL COMPRADOR DECLARA..."
        - etc.

        SOLUTION: See app/ducumentation/services.py line 3231-3299
        """
        print(f"DEBUG: Processing payment data")

        # TODO: Extract precio, moneda, sunat_medio_pago
        # TODO: Use self.letras.money_to_letters()
        # TODO: Implement switch logic for payment method
        # TODO: Return dictionary

        pass  # Remove and implement

    def _get_data_contratantes(self, raw_data):
        """
        Process contractors data - MOST COMPLEX PART!
        Mirrors: PHP get_data_contratantes()

        TASK:
        - Split comma-separated data into arrays
        - Separate transferentes (sellers) from adquirientes (buyers)
        - Handle married couples logic (casados)
        - Handle gender-specific text (F/M)
        - Handle empresa (company) data
        - Generate grammatical articles (EL/LA, LOS/LAS, etc.)

        RETURNS: Dictionary with contractor data for up to 10 people:
        - P_NOM, P_NOM_2, P_NOM_3... (transferentes names)
        - C_NOM, C_NOM_2, C_NOM_3... (adquirientes names)
        - P_DOC, C_DOC (documents)
        - EL_P, EL_C (articles)
        - etc.

        SOLUTION: See app/ducumentation/services.py line 3301-3670
        """
        print(f"DEBUG: Processing contractors data")

        # TODO: Split comma-separated data
        # TODO: Loop through condiciones and separate P vs C
        # TODO: Check for married couples
        # TODO: Generate text with gender logic
        # TODO: Handle empresas
        # TODO: Fill empty placeholders (P_NOM_3 to P_NOM_10)
        # TODO: Generate articles (EL_P, INICIO_P, etc.)
        # TODO: Return dictionary

        pass  # Remove and implement

    def _get_data_escrituracion(self, raw_data):
        """
        Process escrituracion data (folio and papel numbers)
        Mirrors: PHP get_data_escrituracion()

        TASK:
        - Extract folio_inicial, folio_final
        - Extract papel_inicial, papel_final
        - Use placeholders if empty

        RETURNS: Dictionary with keys:
        - FI: folio inicial or {{FI}}
        - FF: folio final or {{FF}}
        - S_IN: papel inicial or {{S_IN}}
        - S_FN: papel final or {{S_FN}}

        SOLUTION: See app/ducumentation/services.py line 3795-3809
        """
        print(f"DEBUG: Processing escrituracion data")

        # TODO: Extract folio and papel data
        # TODO: Use placeholders if empty
        # TODO: Return dictionary

        pass  # Remove and implement

    # ========================================
    # PHASE 3: DATA COMBINATION
    # ========================================

    def _combine_all_data(
        self, data_documento, data_vehiculos, data_pagos, data_contratantes, data_escrituracion
    ):
        """
        Combine all data dictionaries into one
        Mirrors: PHP array merging with +=

        TASK:
        - Merge all dictionaries into one final_data
        - This will have ALL placeholders with their values

        EXAMPLE:
        {
            'NRO_ESC': '123(CIENTO VEINTITRES)',
            'K': 'KAR6508-2025',
            'PLACA': 'ABC-123',
            'MONTO': '2000.00',
            'P_NOM': 'JUAN PEREZ, ',
            'C_NOM': 'MARIA LOPEZ, ',
            ...
        }
        """
        print(f"DEBUG: Combining all data")

        # TODO: Merge all dictionaries
        # HINT: final_data = {**data_documento, **data_vehiculos, ...}

        pass  # Remove and implement

    # ========================================
    # PHASE 4: TEMPLATE PROCESSING
    # ========================================

    def _replace_placeholders(self, template_bytes, final_data):
        """
        Replace {{PLACEHOLDERS}} in the Word template

        TASK:
        - Load template as Document
        - Loop through paragraphs and replace {{KEY}} with final_data[KEY]
        - Loop through tables and replace placeholders
        - Return modified Document object (python-docx Document)

        RETURNS: Document object (NOT bytes, NOT buffer, but the Document itself)

        NOTE: We're NOT using TinyButStrong (PHP library)
        We're using python-docx directly
        """
        print(f"DEBUG: Replacing placeholders")

        # STEP 1: Load Document from bytes
        buffer = io.BytesIO(template_bytes)
        doc = Document(buffer)
        print(f"DEBUG: Document loaded, ready for placeholder replacement")

        # STEP 2: Loop through paragraphs and replace (commented for now)
        # TODO: Uncomment when you have final_data ready
        # for paragraph in doc.paragraphs:
        #     for key, value in final_data.items():
        #         placeholder = f"{{{{{key}}}}}"  # Creates {{KEY}}
        #         if placeholder in paragraph.text:
        #             paragraph.text = paragraph.text.replace(placeholder, str(value))

        # STEP 3: Loop through tables and replace (commented for now)
        # TODO: Uncomment when you have final_data ready
        # for table in doc.tables:
        #     for row in table.rows:
        #         for cell in row.cells:
        #             for paragraph in cell.paragraphs:
        #                 for key, value in final_data.items():
        #                     placeholder = f"{{{{{key}}}}}"
        #                     if placeholder in paragraph.text:
        #                         paragraph.text = paragraph.text.replace(placeholder, str(value))

        # RETURN: Document object
        # This is what gets passed to _clean_unfilled_placeholders() and _upload_to_r2()
        return doc

    def _clean_unfilled_placeholders(self, doc):
        """
        Remove or hide unfilled {{PLACEHOLDERS}}

        TASK:
        - Find any remaining {{SOMETHING}} placeholders
        - Either remove them or hide with white color
        - Keep {{NRO_ESC}}, {{FI}}, {{FF}}, {{S_IN}}, {{S_FN}} (hide with white)
        - Remove all others like {{P_NOM_5}}, {{C_DOC_7}}
        """
        print(f"DEBUG: Cleaning unfilled placeholders")

        # TODO: Loop through runs and find {{PLACEHOLDERS}}
        # TODO: Remove or hide based on placeholder type

        pass  # Remove and implement

    def _upload_to_r2(self, doc, kardex):
        """
        Upload document to R2 storage

        TASK:
        - Save doc to BytesIO buffer
        - Upload to R2 with key: rodriguez-zea/documentos/__PROY__{kardex}.docx
        """
        print(f"DEBUG: Uploading to R2")

        # TODO: Save doc to buffer
        # TODO: Upload to R2 using boto3

        pass  # Remove and implement
