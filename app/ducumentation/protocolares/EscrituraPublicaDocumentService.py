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
from notaria import models
from .utils import (
    NumberToLetterConverter,
    DocumentFormatter,
    PlaceholderProcessor,
    DataValidator,
    TemplateManager,
)


class EscrituraDocumentService:
    """
    Service to generate escritura publica documents based on PHP legacy script
    """

    def __init__(
        self,
        letras=None,
        formatter=None,
        placeholder_processor=None,
        data_validator=None,
        template_manager=None,
    ):
        """
        Initialize with dependency injection

        PARAMETERS:
        - letras: NumberToLetterConverter instance (optional)
        - formatter: DocumentFormatter instance (optional)
        - processor: PlaceholderProcessor instance (optional)
        - validator: DataValidator instance (optional)
        - template_manager: TemplateManager instance (optional)

        If not provided, will create new instances
        """

        self.letras = letras or NumberToLetterConverter()
        self.formatter = DocumentFormatter(self.letras)
        self.placeholder_processor = placeholder_processor or PlaceholderProcessor()
        self.data_validator = data_validator or DataValidator()
        self.template_manager = template_manager or TemplateManager()

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
        template_bytes = self.template_manager.get_template_from_r2(
            template_id, template_info["filename"]
        )
        print(f"DEBUG: Template downloaded: {len(template_bytes)} bytes")

        # STEP 3: Fetch ALL data from database (mirrors PHP consulta_escritura)
        # TODO: Implement this - fetch all data in ONE query
        raw_data = self._consulta_escritura(kardex, action, template_id)
        print(f"DEBUG: Data fetched from database")

        data_documento = self.formatter.format_document_data(raw_data)
        data_vehiculos = self.formatter.format_vehicle_data(raw_data)
        data_pagos = self.formatter.format_payment_data(raw_data)
        data_escrituracion = self.formatter.format_escrituracion_data(raw_data)
        data_contratantes = self.formatter.format_contractor_data(raw_data)

        final_data = self.formatter.combine_all_data(
            data_documento,
            data_vehiculos,
            data_pagos,
            data_escrituracion,
            data_contratantes,
        )

        buffer = io.BytesIO(template_bytes)
        doc = Document(buffer)

        self.placeholder_processor.replace_placeholders(doc, final_data)
        self.placeholder_processor.clean_unfilled_placeholders(doc)

        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)

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
