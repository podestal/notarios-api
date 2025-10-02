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
from .utils import NumberToLetterConverter


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

    def _get_data_documento(self, raw_data):
        """
        Process basic document data
        Return a dictionary with the document data
        """
        print(f"DEBUG: Processing document data")
        numero_escritura = raw_data.get("numero_escritura") or ""
        fecha_escritura = raw_data.get("fecha_escritura")
        numero_minuta = raw_data.get("numero_minuta") or ""

        numero_acta = (
            f"{numero_escritura}({self.letras.number_to_letters(numero_escritura)})"
            if numero_escritura
            else "{{NRO_ESC}}"
        )
        fecha_impresion = (
            self.letras.date_to_letters(fecha_escritura) if fecha_escritura else "{{F_IMPRESION}}"
        )
        fecha_acta = self.letras.date_to_letters(fecha_escritura) if fecha_escritura else "{{F}}"
        numero_minuta_formatted = numero_minuta if numero_minuta else "{{NRO_MIN}}"

        return {
            "NRO_ESC": numero_acta,
            "K": raw_data.get("kardex", ""),
            "NUM_REG": "1",
            "FEC_LET": self.letras.date_to_letters(fecha_escritura) if fecha_escritura else "",
            "F_IMPRESION": fecha_impresion,
            "USUARIO": raw_data.get("usuario", ""),
            "USUARIO_DNI": raw_data.get("dni_usuario", ""),
            "NRO_MIN": numero_minuta_formatted,
            "COMPROBANTE": "sin",
            "O_S": raw_data.get("kardex", ""),
            "ORDEN_SERVICIO": raw_data.get("kardex", ""),
            "F": fecha_acta,
            "DESCRIPCION_SELLO": f"{raw_data.get('abogado', '')} PUNO {raw_data.get('matricula', '')}",
        }

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
        Get contractors data - mirrors get_data_contratantes PHP function with complex spouse logic
        """
        print(f"DEBUG: Processing contractors data")

        def split_if_not_none(value, separator=","):
            return value.split(separator) if value else []

        # Extract data from raw query result
        condiciones = split_if_not_none(raw_data.get("condicion"))
        nombres = split_if_not_none(raw_data.get("nombres"))
        nacionalidades = split_if_not_none(raw_data.get("nacionalidad"))
        tipos_documento = split_if_not_none(raw_data.get("tipo_documento"))
        numeros_documento = split_if_not_none(raw_data.get("numero_documento"))
        ocupaciones = split_if_not_none(raw_data.get("ocupacion"))
        estados_civil = split_if_not_none(raw_data.get("estado_civil"))
        direcciones = raw_data.get("direccion", "").split(",,") if raw_data.get("direccion") else []
        distritos = split_if_not_none(raw_data.get("distrito"))
        provincias = split_if_not_none(raw_data.get("provincia"))
        departamentos = split_if_not_none(raw_data.get("departamento"))
        sexos = split_if_not_none(raw_data.get("sexo"))
        id_clientes = split_if_not_none(raw_data.get("id_cliente"))
        id_conyuges = split_if_not_none(raw_data.get("id_conyuge"))

        # Company data
        nombres_empresa = split_if_not_none(raw_data.get("nombre_empresa"))
        numeros_documento_empresa = split_if_not_none(raw_data.get("numero_documento_empresa"))
        direcciones_empresa = split_if_not_none(raw_data.get("domicilio_empresa"))
        distritos_empresa = split_if_not_none(raw_data.get("distrito_empresa"))
        provincias_empresa = split_if_not_none(raw_data.get("provincia_empresa"))
        departamentos_empresa = split_if_not_none(raw_data.get("departamento_empresa"))
        condiciones_empresa = split_if_not_none(raw_data.get("condicion_empresa"))
        oficinas_registrales = (
            raw_data.get("oficina_registral", "").split(",,")
            if raw_data.get("oficina_registral")
            else []
        )
        numeros_partida = split_if_not_none(raw_data.get("numero_partida"))

        transferentes = []
        adquirientes = []
        sexo_transferentes = []
        sexo_adquirientes = []

        # Process each contractor
        for k, condicion in enumerate(condiciones):
            if not condicion:
                continue

            # Get data for this contractor
            nombre = nombres[k] if k < len(nombres) else ""
            nacionalidad = nacionalidades[k] if k < len(nacionalidades) else ""
            tipo_doc = tipos_documento[k] if k < len(tipos_documento) else ""
            num_doc = numeros_documento[k] if k < len(numeros_documento) else ""
            ocupacion = ocupaciones[k] if k < len(ocupaciones) else ""
            estado_civil = estados_civil[k] if k < len(estados_civil) else ""
            direccion = direcciones[k] if k < len(direcciones) else ""
            distrito = distritos[k] if k < len(distritos) else ""
            provincia = provincias[k] if k < len(provincias) else ""
            departamento = departamentos[k] if k < len(departamentos) else ""
            sexo = sexos[k] if k < len(sexos) else "M"
            id_cliente = id_clientes[k] if k < len(id_clientes) else ""
            id_conyuge = id_conyuges[k] if k < len(id_conyuges) else "NO"

            # Company data
            nombre_empresa = nombres_empresa[k] if k < len(nombres_empresa) else ""
            num_doc_empresa = (
                numeros_documento_empresa[k] if k < len(numeros_documento_empresa) else ""
            )
            direccion_empresa = direcciones_empresa[k] if k < len(direcciones_empresa) else ""
            distrito_empresa = distritos_empresa[k] if k < len(distritos_empresa) else ""
            provincia_empresa = provincias_empresa[k] if k < len(provincias_empresa) else ""
            departamento_empresa = (
                departamentos_empresa[k] if k < len(departamentos_empresa) else ""
            )
            condicion_empresa = condiciones_empresa[k] if k < len(condiciones_empresa) else ""
            oficina_registral = oficinas_registrales[k] if k < len(oficinas_registrales) else ""
            numero_partida = numeros_partida[k] if k < len(numeros_partida) else ""

            contractor_data = {
                "condiciones": condicion,
                "nombres": nombre,
                "nacionalidad": nacionalidad,
                "tipoDocumento": tipo_doc,
                "numeroDocumento": num_doc,
                "ocupacion": ocupacion,
                "estadoCivil": estado_civil,
                "direccion": direccion,
                "distrito": distrito,
                "provincia": provincia,
                "departamento": departamento,
                "sexo": sexo,
                "idCliente": id_cliente,
                "idConyuge": id_conyuge,
                "nombreEmpresa": nombre_empresa,
                "numeroDocumentoEmpresa": num_doc_empresa,
                "direccionEmpresa": direccion_empresa,
                "distritoEmpresa": distrito_empresa,
                "provinciaEmpresa": provincia_empresa,
                "departamentoEmpresa": departamento_empresa,
                "oficinaRegistral": oficina_registral,
                "numeroPartida": numero_partida,
                "condicionEmpresa": condicion_empresa,
            }

            # TRANSFERENTES (VENDEDOR, PODERDANTE, etc.)
            if condicion in [
                "VENDEDOR",
                "PODERDANTE",
                "OTORGANTE",
                "REPRESENTANTE",
                "ANTICIPANTE",
                "ADJUDICANTE",
                "DONANTE",
                "USUFRUCTUANTE",
                "TRANSFERENTE",
                "TITULAR",
                "MUTUANTE",
                "PROPIETARIO",
                "DEUDOR",
                "ASOCIANTE",
                "TRANSFERENTE / PROPIETARIO (VENDEDOR)",
            ]:
                transferentes.append(contractor_data)
                sexo_transferentes.append(sexo)

            # ADQUIRIENTES (COMPRADOR, APODERADO, etc.)
            elif condicion in [
                "COMPRADOR",
                "APODERADO",
                "ANTICIPADO",
                "ADJUDICATARIO",
                "DONATARIO",
                "USUFRUCTUARIO",
                "TESTIGO A RUEGO",
                "ADQUIRIENTE",
                "ACREEDOR",
                "OTORGADO",
                "MUTUATARIO",
                "BENEFICIARIA",
                "ASOCIADO",
                "ADQUIRENTE / BENEFICIARIO (COMPRADOR)",
            ]:
                adquirientes.append(contractor_data)
                sexo_adquirientes.append(sexo)

        # Determine gender classification for groups
        sexo_transferentes_clasificado = self._classify_gender(sexo_transferentes)
        sexo_adquirientes_clasificado = self._classify_gender(sexo_adquirientes)

        # Sort by gender (DESC means males first)
        transferentes = sorted(transferentes, key=lambda x: x["sexo"], reverse=True)
        adquirientes = sorted(adquirientes, key=lambda x: x["sexo"], reverse=True)

        return {
            "transferentes": transferentes,
            "adquirientes": adquirientes,
            "sexoTransferentes": sexo_transferentes_clasificado,
            "sexoAdquirientes": sexo_adquirientes_clasificado,
        }

    def _classify_gender(self, sexos: list) -> str:
        """Helper method to classify gender groups"""
        if not sexos:
            return "MIXTO"

        has_female = False
        has_male = False

        for sexo in sexos:
            if sexo == "F":
                has_female = True
            elif sexo == "M":
                has_male = True

        if has_male:
            return "MIXTO"
        elif has_female:
            return "MUJERES"
        else:
            return "MIXTO"

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

        return {**data_documento, **data_contratantes}

    # ========================================
    # PHASE 4: TEMPLATE PROCESSING
    # ========================================

    def _replace_placeholders(self, template_bytes, final_data):
        """
        Replace {{PLACEHOLDERS}} while preserving formatting
        """
        print(f"DEBUG: Replacing placeholders")

        buffer = io.BytesIO(template_bytes)
        doc = Document(buffer)
        print(f"DEBUG: Document loaded")

        # Replace in paragraphs
        for paragraph in doc.paragraphs:
            self._replace_in_paragraph(paragraph, final_data)

        # Replace in tables
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        self._replace_in_paragraph(paragraph, final_data)

        return doc

    def _replace_in_paragraph(self, paragraph, final_data):
        """
        Replace placeholders in a paragraph while preserving formatting

        STRATEGY:
        1. Get full paragraph text
        2. Find all {{PLACEHOLDERS}}
        3. Replace in runs that contain them
        4. Handle placeholders split across multiple runs
        """
        full_text = paragraph.text

        # Quick check - if no placeholders, skip
        if "{{" not in full_text or "}}" not in full_text:
            return

        # Try simple replacement first (works if placeholder is in one run)
        for key, value in final_data.items():
            placeholder = f"{{{{{key}}}}}"

            if placeholder in full_text:
                # Try to find and replace in individual runs
                for run in paragraph.runs:
                    if placeholder in run.text:
                        run.text = run.text.replace(placeholder, str(value))
                        return  # Success!

        # If we get here, placeholder is split across runs
        # Fall back to paragraph-level replacement (loses formatting)
        for key, value in final_data.items():
            placeholder = f"{{{{{key}}}}}"
            if placeholder in full_text:
                # Get the formatting from the first run
                if paragraph.runs:
                    first_run_font = paragraph.runs[0].font

                # Clear all runs and create one new run
                for run in paragraph.runs:
                    run.text = ""

                # Create new run with replaced text
                new_run = paragraph.runs[0] if paragraph.runs else paragraph.add_run()
                new_run.text = full_text.replace(placeholder, str(value))

                # Try to preserve some formatting from first run
                if paragraph.runs and first_run_font:
                    try:
                        new_run.font.color.rgb = first_run_font.color.rgb
                        new_run.font.bold = first_run_font.bold
                        new_run.font.italic = first_run_font.italic
                    except:
                        pass  # Ignore if formatting can't be copied

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
