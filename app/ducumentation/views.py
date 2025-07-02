from django.shortcuts import render
from rest_framework.viewsets import ModelViewSet
from rest_framework.decorators import action
from rest_framework.response import Response
from . import models, serializers
from notaria.models import TplTemplate, Detallevehicular, Patrimonial, Contratantes, Actocondicion, Cliente2, Nacionalidades
from notaria.constants import MONEDAS, OPORTUNIDADES_PAGO, FORMAS_PAGO
from notaria import pagination
from django.http import HttpResponse
import boto3
from botocore.client import Config
from django.conf import settings
import os
from docx import Document
import io
from .constants import ROLE_LABELS, TIPO_DOCUMENTO, CIVIL_STATUS
import re
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any
from botocore.config import Config


class VehicleTransferDocumentService:
    """
    Django service to generate vehicle transfer documents based on the PHP logic
    """
    
    def __init__(self):
        self.letras = NumberToLetterConverter()
    
    def generate_vehicle_transfer_document(self, template_id: int, num_kardex: str, action: str = 'generate') -> HttpResponse:
        """
        Main method to generate vehicle transfer document
        """
        try:
            template = self._get_template_from_r2(template_id)
            document_data = self._get_dummy_document_data(num_kardex)
            doc = self._process_document(template, document_data)
            self.remove_unfilled_placeholders(doc)
            return self._create_response(doc, f"__PROY__{num_kardex}.docx")
        except FileNotFoundError as e:
            return HttpResponse(str(e), status=404)
        except Exception as e:
            return HttpResponse(f"Error generating document: {str(e)}", status=500)

    def remove_unfilled_placeholders(self, doc):
        """
        Remove all [E.SOMETHING] placeholders that were not filled.
        """
        placeholder_pattern = re.compile(r'\[E\.[A-Z0-9_]+\]')
        for paragraph in doc.paragraphs:
            if placeholder_pattern.search(paragraph.text):
                paragraph.text = placeholder_pattern.sub('', paragraph.text)
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        if placeholder_pattern.search(paragraph.text):
                            paragraph.text = placeholder_pattern.sub('', paragraph.text)
    
    def _get_template_from_r2(self, template_id: int) -> bytes:
        """
        Get template from R2 storage (placeholder for your existing logic)
        """
        template = TplTemplate.objects.get(pktemplate=template_id)
        s3 = boto3.client(
            's3',
            endpoint_url=os.environ.get('CLOUDFLARE_R2_ENDPOINT'),
            aws_access_key_id=os.environ.get('CLOUDFLARE_R2_ACCESS_KEY'),
            aws_secret_access_key=os.environ.get('CLOUDFLARE_R2_SECRET_KEY'),
            config=Config(signature_version='s3v4'),
            region_name='auto',
        )
        
        # Dummy template path - replace with actual logic
        object_key = f"rodriguez-zea/PROTOCOLARES/ACTAS DE TRANSFERENCIA DE BIENES MUEBLES REGISTRABLES/{template.filename}"
        
        try:
            s3_response = s3.get_object(
                Bucket=os.environ.get('CLOUDFLARE_R2_BUCKET'), 
                Key=object_key
            )
            return s3_response['Body'].read()
        except Exception as e:
            # Log the error and return a 404 or raise
            print(f'Template not found in R2: {e}')
            raise FileNotFoundError(f"Template not found in R2: {object_key}")
    
    def _create_dummy_template(self) -> bytes:
        """
        Create a dummy template for testing
        """
        doc = Document()
        doc.add_paragraph("ACTA DE TRANSFERENCIA DE VEHÍCULO")
        doc.add_paragraph("Kardex: [E.K]")
        doc.add_paragraph("Número de Escritura: [E.NRO_ESC]")
        doc.add_paragraph("Fecha: [E.F_IMPRESION]")
        doc.add_paragraph("")
        doc.add_paragraph("TRANSFERENTE:")
        doc.add_paragraph("[E.P_NOM], [E.P_NACIONALIDAD] [E.P_TIP_DOC] [E.P_DOC] [E.P_OCUPACION] [E.P_ESTADO_CIVIL] [E.P_DOMICILIO]")
        doc.add_paragraph("")
        doc.add_paragraph("ADQUIRIENTE:")
        doc.add_paragraph("[E.C_NOM], [E.C_NACIONALIDAD] [E.C_TIP_DOC] [E.C_DOC] [E.C_OCUPACION] [E.C_ESTADO_CIVIL] [E.C_DOMICILIO]")
        doc.add_paragraph("")
        doc.add_paragraph("VEHÍCULO:")
        doc.add_paragraph("Placa: [E.PLACA]")
        doc.add_paragraph("Marca: [E.MARCA]")
        doc.add_paragraph("Modelo: [E.MODELO]")
        doc.add_paragraph("Año: [E.AÑO_FABRICACION]")
        doc.add_paragraph("Serie: [E.NRO_SERIE]")
        doc.add_paragraph("Motor: [E.NRO_MOTOR]")
        doc.add_paragraph("")
        doc.add_paragraph("PRECIO: [E.MONTO_LETRAS]")
        doc.add_paragraph("MEDIO DE PAGO: [E.MED_PAGO]")
        
        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        return buffer.read()
    
    def _get_dummy_document_data(self, num_kardex: str) -> Dict[str, Any]:
        """
        Get dummy data for document placeholders
        """
        # Extract year from kardex (similar to PHP logic)
        arr_kardex = num_kardex.split('-')
        anio_kardex = arr_kardex[1] if len(arr_kardex) > 1 else "2024"
        
        # Document data
        document_data = self._get_document_data(num_kardex, anio_kardex)
        
        # Vehicle data
        vehicle_data = self._get_vehicle_data(num_kardex)
        
        # Payment data
        payment_data = self._get_payment_data(num_kardex)
        
        # Contractors data
        contractors_data = self._get_contractors_data(num_kardex)
        
        # Merge all data
        final_data = {}
        final_data.update(document_data)
        final_data.update(vehicle_data)
        final_data.update(payment_data)
        final_data.update(contractors_data)
        
        return final_data
    
    def _get_document_data(self, num_kardex: str, anio_kardex: str) -> Dict[str, str]:
        """
        Get document basic information
        """
        numero_escritura = "001"
        fecha_escritura = datetime.now()
        
        return {
            'K': num_kardex,
            'NRO_ESC': f"{numero_escritura}({self.letras.number_to_letters(numero_escritura)})",
            'NUM_REG': '1',
            'FEC_LET': self.letras.date_to_letters(fecha_escritura),
            'F_IMPRESION': self.letras.date_to_letters(fecha_escritura),
            'USUARIO': 'JUAN PÉREZ GARCÍA',
            'USUARIO_DNI': '12345678',
            'NRO_MIN': '12345678',
            'COMPROBANTE': 'sin',
            'O_S': num_kardex,
            'ORDEN_SERVICIO': num_kardex,
            'FECHA_ACT': self.letras.date_to_letters(fecha_escritura),
            'FECHA_MAX': self.letras.date_to_letters(fecha_escritura),
        }
    
    def _get_vehicle_data(self, kardex) -> Dict[str, str]:
        """
        Get vehicle information
        """

        vehicle = Detallevehicular.objects.filter(
            kardex=kardex
        ).first()

        return {
            'PLACA': vehicle.numplaca if vehicle else '',
            'CLASE': vehicle.clase if vehicle else '',
            'MARCA': vehicle.marca if vehicle else '',
            'MODELO': vehicle.modelo if vehicle else '',
            'AÑO_FABRICACION': vehicle.anofab if vehicle else '',
            'CARROCERIA': vehicle.carroceria if vehicle else '',
            'COLOR': vehicle.color if vehicle else '',
            'NRO_MOTOR': vehicle.motor if vehicle else '',
            'NRO_SERIE': vehicle.numserie if vehicle else '',
            'FEC_INS': vehicle.fecinsc if vehicle else '',
            'FECHA_INSCRIPCION': vehicle.fecinsc if vehicle else '',
            'ZONA_REGISTRAL': vehicle.idsedereg if vehicle else '',
            'NUM_ZONA_REG': vehicle.idsedereg if vehicle else '',
            'SEDE': '',
            'INSTRUIDO': 'INSTRUIDO',
            'COMBUSTIBLE': vehicle.combustible if vehicle else '',
            'NRO_TARJETA': '',
            'NRO_CILINDROS': vehicle.numcil if vehicle else '',
        }
    
    def _get_payment_data(self, kardex) -> Dict[str, str]:
        """
        Get payment information based on payment method
        """

        patrimonial = Patrimonial.objects.filter(
            kardex=kardex)
        if patrimonial.exists():
            patrimonial = patrimonial.first()

        sunat_medio_pago = "008"  # Cash payment
        precio = patrimonial.importetrans if patrimonial else '0.00'
        moneda = MONEDAS[patrimonial.idmon]['desmon'] if patrimonial else '' 
        simbolo_moneda = MONEDAS[patrimonial.idmon]['simbolo'] if patrimonial else ''
        forma_pago = FORMAS_PAGO[patrimonial.fpago]['descripcion'] if patrimonial else ''
        
        # Payment method logic (similar to PHP switch)
        if sunat_medio_pago == "008":
            medio_pago = f'EL COMPRADOR DECLARA QUE HA PAGADO EL PRECIO DEL VEHICULO EN DINERO EN EFECTIVO Y CON ANTERIORIDAD A LA CELEBRACION DE LA PRESENTE ACTA DE TRANSFERENCIA. NO HABIENDO UTILIZADO NINGÚN MEDIO DE PAGO ESTABLECIDO EN LA LEY Nº 28194, PORQUE EL MONTO TOTAL NO ES IGUAL NI SUPERA LOS S/ 2,000.00 O US$ 500.00. EL TIPO Y CÓDIGO DEL MEDIO EMPLEADO ES: "EFECTIVO POR OPERACIONES EN LAS QUE NO EXISTE OBLIGACIÓN DE UTILIZAR MEDIOS DE PAGO-008". POR SER EL PAGO DEL PRECIO INFERIOR A 1 UIT. MODIFICADO POR EL DECRETO LEGISLATIVO N° 1529.'
            exhibio_medio_pago = 'SE DEJA CONSTANCIA QUE PARA LA REALIZACIÓN DEL PRESENTE ACTO, LAS PARTES NO ME HAN EXHIBIDO NINGÚN MEDIO DE PAGO. DOY FE.'
            fin_medio_pago = 'EN DINERO EN EFECTIVO'
        else:
            # Default case
            medio_pago = 'EL COMPRADOR DECLARA QUE HA PAGADO EL PRECIO DEL VEHICULO EN DINERO EN EFECTIVO Y CON ANTERIORIDAD A LA CELEBRACION DE LA PRESENTE ACTA DE TRANSFERENCIA.'
            exhibio_medio_pago = 'SE DEJA CONSTANCIA QUE PARA LA REALIZACIÓN DEL PRESENTE ACTO, LAS PARTES NO ME HAN EXHIBIDO NINGÚN MEDIO DE PAGO. DOY FE.'
            fin_medio_pago = 'EN DINERO EN EFECTIVO'
        
        return {
            'MONTO': precio,
            'MON_VEHI': moneda,
            'MONTO_LETRAS': self.letras.money_to_letters(moneda, Decimal(precio)),
            'MONEDA_C': simbolo_moneda,
            'SUNAT_MED_PAGO': sunat_medio_pago,
            'DES_PRE_VEHI': self.letras.money_to_letters(moneda, Decimal(precio)),
            'EXH_MED_PAGO': exhibio_medio_pago,
            'MED_PAGO': medio_pago,
            'FIN_MED_PAGO': fin_medio_pago,
            'FORMA_PAGO': forma_pago,
            'C_INICIO_MP': '',
            'TIPO_PAGO_E': '',
            'TIPO_PAGO_C': '',
            'MONTO_MP': '',
            'CONSTANCIA': exhibio_medio_pago,
            'DETALLE_MP': '',
            'FORMA_PAGO_S': '',
            'MONEDA_C_MP': '',
            'MEDIO_PAGO_C': '',
            'MP_MEDIO_PAGO': '',
            'MP_COMPLETO': '',
            'USO': '',
        }
    
    # def _get_contractors_data(self) -> Dict[str, str]:
    #     """
    #     Get contractors (transferor and acquirer) information
    #     """
    #     # Transferor data
    #     transferor_data = {
    #         'P_NOM': 'MARÍA GONZÁLEZ LÓPEZ, ',
    #         'P_NACIONALIDAD': 'PERUANA, ',
    #         'P_TIP_DOC': 'DNI',
    #         'P_DOC': 'IDENTIFICADA CON DNI N° 12345678, ',
    #         'P_OCUPACION': 'INGENIERA CIVIL',
    #         'P_ESTADO_CIVIL': 'CASADA, ',
    #         'P_DOMICILIO': 'CON DOMICILIO EN AV. AREQUIPA 123 DEL DISTRITO DE MIRAFLORES PROVINCIA DE LIMA Y DEPARTAMENTO DE LIMA',
    #         'P_IDE': ' ',
    #         'SEXO_P': 'F',
    #         'P_FIRMAN': 'MARÍA GONZÁLEZ LÓPEZ, ',
    #         'P_IMPRIME': f' FIRMA EN: {self.letras.date_to_letters(datetime.now())}',
    #     }
        
    #     # Acquirer data
    #     acquirer_data = {
    #         'C_NOM': 'CARLOS RODRÍGUEZ MARTÍNEZ, ',
    #         'C_NACIONALIDAD': 'PERUANO, ',
    #         'C_TIP_DOC': 'DNI',
    #         'C_DOC': 'IDENTIFICADO CON DNI N° 87654321, ',
    #         'C_OCUPACION': 'ABOGADO',
    #         'C_ESTADO_CIVIL': 'SOLTERO, ',
    #         'C_DOMICILIO': 'CON DOMICILIO EN JR. BOLÍVAR 456 DEL DISTRITO DE SAN ISIDRO PROVINCIA DE LIMA Y DEPARTAMENTO DE LIMA',
    #         'C_IDE': ' ',
    #         'SEXO_C': 'M',
    #         'C_FIRMAN': 'CARLOS RODRÍGUEZ MARTÍNEZ, ',
    #         'C_IMPRIME': f' FIRMA EN: {self.letras.date_to_letters(datetime.now())}',
    #     }
        
    #     # Articles and grammar
    #     articles_data = {
    #         'EL_P': 'LA',
    #         'EL_C': 'EL',
    #         'AMBOS': ' AMBOS ',
    #         'S_P': '  ',
    #         'ES_P': '  ',
    #         'C_INICIO': ' SEÑOR',
    #         'C_CALIDAD': 'COMPRADOR',
    #         'Y_CON_C': '',
    #         'N_C': '',
    #         'Y_C': '',
    #         'L_C': '',
    #         'O_A_C': 'O',
    #         'C_FIRMA': 'FIRMA EN',
    #         'C_AMBOS': ' ',
    #         'P_INICIO': ' SEÑORA',
    #         'P_CALIDAD': 'VENDEDORA',
    #         'Y_CON_P': '',
    #         'N_P': '',
    #         'Y_P': '',
    #         'L_P': '',
    #         'O_A_P': 'A',
    #         'P_FIRMA': 'FIRMA EN',
    #         'P_AMBOS': ' ',
    #     }
        
    #     # Merge all contractor data
    #     contractors_data = {}
    #     contractors_data.update(transferor_data)
    #     contractors_data.update(acquirer_data)
    #     contractors_data.update(articles_data)
        
    #     return contractors_data

    def _get_contractors_data(self, kardex) -> Dict[str, str]:
        """
        Get contractors (transferor and acquirer) information, with dynamic articles/grammar.
        """
        # 1. Define your people lists (simulate DB or input)
        
        # update contractors view set and add a new field called condicion_str
        # get contractors data
        # try with more then vendedor y comprador

        contratantes = Contratantes.objects.filter(kardex=kardex)
        contratantes_list = []


        for contratante in contratantes:
            condiciones = contratante.condicion.split('/')
            condiciones_list = []
            for condicion in condiciones:
                if condicion:
                    condicion_int = condicion.split('.')[0]
                    condicion_str = Actocondicion.objects.get(idcondicion=condicion_int).condicion
                    condiciones_list.append(condicion_str)

            cliente2 = Cliente2.objects.get(idcontratante=contratante.idcontratante)
            nacionalidad = Nacionalidades.objects.get(idnacionalidad=cliente2.nacionalidad)
            contratante_obj = {
                'sexo': cliente2.sexo,
                'condiciones': (', ').join(condiciones_list),
                'nombres': f'{cliente2.prinom} {cliente2.segnom} {cliente2.apepat} {cliente2.apemat}',
                'nacionalidad': nacionalidad.descripcion,
                'tipoDocumento': TIPO_DOCUMENTO[cliente2.idtipdoc]['destipdoc'] if cliente2.idtipdoc in TIPO_DOCUMENTO else '',
                'numeroDocumento': cliente2.numdoc,
                'ocupacion': re.split(r'[/,;]', cliente2.detaprofesion)[0].strip() if cliente2.detaprofesion else '',
                'estadoCivil': CIVIL_STATUS[cliente2.idestcivil]['label'] if cliente2.idestcivil in CIVIL_STATUS else '',
                'direccion': cliente2.direccion if cliente2.direccion else '',
            }
            contratantes_list.append(contratante_obj)

        print('contratantes_list:', contratantes_list)
        transferors, acquirers = self.classify_contratantes(contratantes_list)

        # transferors = [
        #     {
        #         'sexo': 'F',
        #         'condiciones': 'VENDEDOR',
        #         'idCliente': 1,
        #         'idConyuge': 2,
        #         'nombres': 'MARÍA GONZÁLEZ LÓPEZ',
        #         'nacionalidad': 'PERUANA',
        #         'tipoDocumento': 'DNI',
        #         'numeroDocumento': '12345678',
        #         'ocupacion': 'INGENIERA CIVIL',
        #         'estadoCivil': 'CASADA',
        #         'direccion': 'AV. AREQUIPA 123 DEL DISTRITO DE MIRAFLORES PROVINCIA DE LIMA Y DEPARTAMENTO DE LIMA',
        #     }
        #     # Add more transferors as needed
        # ]
        # acquirers = [
        #     {
        #         'sexo': 'M',
        #         'condiciones': 'COMPRADOR',
        #         'idCliente': 3,
        #         'idConyuge': None,
        #         'nombres': 'CARLOS RODRÍGUEZ MARTÍNEZ',
        #         'nacionalidad': 'PERUANO',
        #         'tipoDocumento': 'DNI',
        #         'numeroDocumento': '87654321',
        #         'ocupacion': 'ABOGADO',
        #         'estadoCivil': 'SOLTERO',
        #         'direccion': 'JR. BOLÍVAR 456 DEL DISTRITO DE SAN ISIDRO PROVINCIA DE LIMA Y DEPARTAMENTO DE LIMA',
        #     }
        #     # Add more acquirers as needed
        # ]

        # 2. Build the data for the first transferor/acquirer (for placeholders)
        transferor_data = {
            'P_NOM': transferors[0]['nombres'] + ', ',
            'P_NACIONALIDAD': transferors[0]['nacionalidad'] + ', ',
            'P_TIP_DOC': transferors[0]['tipoDocumento'],
            'P_DOC': f"IDENTIFICADA CON {transferors[0]['tipoDocumento']} N° {transferors[0]['numeroDocumento']}, ",
            'P_OCUPACION': transferors[0]['ocupacion'],
            'P_ESTADO_CIVIL': transferors[0]['estadoCivil'] + ', ',
            'P_DOMICILIO': 'CON DOMICILIO EN ' + transferors[0]['direccion'],
            'P_IDE': ' ',
            'SEXO_P': transferors[0]['sexo'],
            'P_FIRMAN': transferors[0]['nombres'] + ', ',
            'P_IMPRIME': f' FIRMA EN: {self.letras.date_to_letters(datetime.now())}',
        }
        acquirer_data = {
            'C_NOM': acquirers[0]['nombres'] + ', ',
            'C_NACIONALIDAD': acquirers[0]['nacionalidad'] + ', ',
            'C_TIP_DOC': acquirers[0]['tipoDocumento'],
            'C_DOC': f"IDENTIFICADO CON {acquirers[0]['tipoDocumento']} N° {acquirers[0]['numeroDocumento']}, ",
            'C_OCUPACION': acquirers[0]['ocupacion'],
            'C_ESTADO_CIVIL': acquirers[0]['estadoCivil'] + ', ',
            'C_DOMICILIO': 'CON DOMICILIO EN ' + acquirers[0]['direccion'],
            'C_IDE': ' ',
            'SEXO_C': acquirers[0]['sexo'],
            'C_FIRMAN': acquirers[0]['nombres'] + ', ',
            'C_IMPRIME': f' FIRMA EN: {self.letras.date_to_letters(datetime.now())}',
        }

        # 3. Get articles/grammar dynamically
        articles_transferor = self.get_articles_and_grammar(transferors, 'P')
        articles_acquirer = self.get_articles_and_grammar(acquirers, 'C')

        # 4. Merge all data
        contractors_data = {}
        contractors_data.update(transferor_data)
        contractors_data.update(acquirer_data)
        contractors_data.update(articles_transferor)
        contractors_data.update(articles_acquirer)

        return contractors_data

  
    def classify_contratantes(self, contratantes):
        TRANSFEROR_ROLES = {'VENDEDOR', 'DONANTE', 'APODERADO', 'CEDENTE', 'ARRENDADOR', 'MUTUANTE', 'ADJUDICANTE'}
        ACQUIRER_ROLES = {'COMPRADOR', 'DONATARIO', 'CESIONARIO', 'ARRENDATARIO', 'MUTUARIO', 'ADJUDICATARIO'}

        transferors = [c for c in contratantes if c['condiciones'] in TRANSFEROR_ROLES]
        acquirers = [c for c in contratantes if c['condiciones'] in ACQUIRER_ROLES]
        return transferors, acquirers

    def get_articles_and_grammar(self, people, role_prefix):
        count = len(people)
        all_female = all(p['sexo'] == 'F' for p in people)
        all_male = all(p['sexo'] == 'M' for p in people)
        ambos = ' AMBOS ' if count > 1 else ' '
        main_role = people[0]['condiciones'] if people else ''
        role_labels = ROLE_LABELS.get(main_role, {})
        if count > 1:
            calidad = role_labels.get('F_PL' if all_female else 'M_PL', main_role + 'S')
            inicio = ' SEÑORAS' if all_female else ' SEÑORES'
            el = 'LAS' if all_female else 'LOS'
        else:
            calidad = role_labels.get('F' if all_female else 'M', main_role)
            inicio = ' SEÑORA' if all_female else ' SEÑOR'
            el = 'LA' if all_female else 'EL'
        return {
            f'EL_{role_prefix}': el,
            f'{role_prefix}_CALIDAD': calidad,
            f'{role_prefix}_INICIO': inicio,
            f'{role_prefix}_AMBOS': ambos,
        }

    # def get_articles_and_grammar(self, people, role_prefix):
    #     """
    #     Returns a dict with the correct articles and word forms for the given people.
    #     people: list of dicts with at least 'sexo' and 'condiciones'
    #     role_prefix: 'P' for transferor, 'C' for acquirer
    #     """


    #     count = len(people)
    #     all_female = all(p['sexo'] == 'F' for p in people)
    #     all_male = all(p['sexo'] == 'M' for p in people)
    #     ambos = ' AMBOS ' if count > 1 else ' '
    #     # Get the main role (assume all have the same for this group)
    #     main_role = people[0]['condiciones'] if people else ''
    #     role_labels = ROLE_LABELS.get(main_role, {})
    #     if count > 1:
    #         calidad = role_labels.get('F_PL' if all_female else 'M_PL', main_role + 'S')
    #         inicio = ' SEÑORAS' if all_female else ' SEÑORES'
    #         el = 'LAS' if all_female else 'LOS'
    #     else:
    #         calidad = role_labels.get('F' if all_female else 'M', main_role)
    #         inicio = ' SEÑORA' if all_female else ' SEÑOR'
    #         el = 'LA' if all_female else 'EL'
    #     return {
    #         f'EL_{role_prefix}': el,
    #         f'{role_prefix}_CALIDAD': calidad,
    #         f'{role_prefix}_INICIO': inicio,
    #         f'{role_prefix}_AMBOS': ambos,
    #     }
    
    def _process_document(self, template_bytes: bytes, data: Dict[str, str]) -> Document:
        """
        Process the document template with data
        """
        doc = Document(io.BytesIO(template_bytes))
        
        # Replace placeholders in paragraphs
        for paragraph in doc.paragraphs:
            for placeholder, value in data.items():
                if f'[E.{placeholder}]' in paragraph.text:
                    paragraph.text = paragraph.text.replace(f'[E.{placeholder}]', str(value))
        
        # Replace placeholders in tables
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        for placeholder, value in data.items():
                            if f'[E.{placeholder}]' in paragraph.text:
                                paragraph.text = paragraph.text.replace(f'[E.{placeholder}]', str(value))
        
        return doc
    
    def _create_response(self, doc: Document, filename: str) -> HttpResponse:
        """
        Create HTTP response with the document
        """
        buffer = io.BytesIO()
        doc.save(buffer)
        buffer.seek(0)
        
        response = HttpResponse(
            buffer.read(),
            content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        response['Content-Length'] = str(buffer.getbuffer().nbytes)
        response['Access-Control-Allow-Origin'] = '*'
        
        return response


class NumberToLetterConverter:
    """
    Utility class to convert numbers to letters (Spanish)
    """
    
    def __init__(self):
        self.unidades = ['', 'UNO', 'DOS', 'TRES', 'CUATRO', 'CINCO', 'SEIS', 'SIETE', 'OCHO', 'NUEVE']
        self.decenas = ['', 'DIEZ', 'VEINTE', 'TREINTA', 'CUARENTA', 'CINCUENTA', 'SESENTA', 'SETENTA', 'OCHENTA', 'NOVENTA']
        self.especiales = {
            11: 'ONCE', 12: 'DOCE', 13: 'TRECE', 14: 'CATORCE', 15: 'QUINCE',
            16: 'DIECISÉIS', 17: 'DIECISIETE', 18: 'DIECIOCHO', 19: 'DIECINUEVE'
        }
        self.meses = [
            'ENERO', 'FEBRERO', 'MARZO', 'ABRIL', 'MAYO', 'JUNIO',
            'JULIO', 'AGOSTO', 'SEPTIEMBRE', 'OCTUBRE', 'NOVIEMBRE', 'DICIEMBRE'
        ]
    
    def number_to_letters(self, number: str) -> str:
        """
        Convert number to letters in Spanish
        """
        try:
            num = int(number)
            if num == 0:
                return 'CERO'
            return self._convert_number_to_letters(num)
        except:
            return number
    
    def _convert_number_to_letters(self, num: int) -> str:
        """
        Internal method to convert number to letters
        """
        if num < 10:
            return self.unidades[num]
        elif num < 20:
            return self.especiales.get(num, '')
        elif num < 100:
            decena = num // 10
            unidad = num % 10
            if unidad == 0:
                return self.decenas[decena]
            else:
                return f"{self.decenas[decena]} Y {self.unidades[unidad]}"
        elif num < 1000:
            centena = num // 100
            resto = num % 100
            if resto == 0:
                return f"{self.unidades[centena]}CIENTOS"
            else:
                return f"{self.unidades[centena]}CIENTOS {self._convert_number_to_letters(resto)}"
        elif num < 1000000:
            miles = num // 1000
            resto = num % 1000
            if miles == 1:
                return f"MIL {self._convert_number_to_letters(resto)}"
            else:
                return f"{self._convert_number_to_letters(miles)} MIL {self._convert_number_to_letters(resto)}"
        elif num < 1000000000:
            millones = num // 1000000
            resto = num % 1000000
            if millones == 1:
                return f"UN MILLÓN {self._convert_number_to_letters(resto)}"
            else:
                return f"{self._convert_number_to_letters(millones)} MILLONES {self._convert_number_to_letters(resto)}"
        else:
            return str(num)  # Simplified for demo
    
    def date_to_letters(self, date: datetime) -> str:
        """
        Convert date to letters in Spanish
        """
        dia = date.day
        mes = self.meses[date.month - 1]
        anio = date.year
        
        return f"{self.number_to_letters(str(dia))} DE {mes} DEL {self.number_to_letters(str(anio))}"
    
    def money_to_letters(self, currency: str, amount: Decimal) -> str:
        """
        Convert money amount to letters
        """
        if currency == "PEN":
            return f"{self.number_to_letters(str(int(amount)))} SOLES CON {self.number_to_letters(str(int((amount % 1) * 100)))} CÉNTIMOS"
        elif currency == "USD":
            return f"{self.number_to_letters(str(int(amount)))} DÓLARES AMERICANOS CON {self.number_to_letters(str(int((amount % 1) * 100)))} CENTAVOS"
        else:
            return f"{self.number_to_letters(str(int(amount)))} {currency}"


# Usage example in your Django view:
# def open_template_with_vehicle_transfer(request):
#     """
#     Django view that uses the service
#     """
#     template_id = request.query_params.get("template_id")
#     num_kardex = request.query_params.get("num_kardex", "ACT2040-2024")
#     action = request.query_params.get("action", "generate")
    
#     if not template_id:
#         return HttpResponse({"error": "Missing template_id parameter."}, status=400)
    
#     try:
#         template_id = int(template_id)
#     except ValueError:
#         return HttpResponse({"error": "Invalid template_id format."}, status=400)
    
#     service = VehicleTransferDocumentService()
    # return service.generate_vehicle_transfer_document(template_id, num_kardex, action)

class DocumentosGeneradosViewSet(ModelViewSet):
    """
    ViewSet for the Documentogenerados model.
    """
    queryset = models.Documentogenerados.objects.all()
    serializer_class = serializers.DocumentosGeneradosSerializer
    pagination_class = pagination.KardexPagination

    @action(detail=False, methods=['get'])
    def by_kardex(self, request):
        """
        Get Documentogenerados records by Kardex.
        """
        kardex = request.query_params.get('kardex')
        if not kardex:
            return Response(
                {"error": "kardex parameter is required."},
                status=400
            )
        
        documentos_generados = models.Documentogenerados.objects.filter(kardex=kardex)
        if not documentos_generados.exists():
            return Response([], status=200)

        serializer = serializers.DocumentosGeneradosSerializer(documentos_generados, many=True)
        return Response(serializer.data)


    @action(detail=False, methods=['get'], url_path='open-template')
    def open_template(self, request):
        template_id = request.query_params.get("template_id", '2')
        num_kardex = request.query_params.get("num_kardex", "ACT401-2025")
        action = request.query_params.get("action", "generate")
        
        if not template_id:
            return HttpResponse({"error": "Missing template_id parameter."}, status=400)
        
        try:
            template_id = int(template_id)
        except ValueError:
            return HttpResponse({"error": "Invalid template_id format."}, status=400)
        
        service = VehicleTransferDocumentService()
        return service.generate_vehicle_transfer_document(template_id, num_kardex, action)
    #     """
    #     Stream a filled Word document (.docx) directly from R2 so Word can open it.
    #     """
    #     template_id = request.query_params.get("template_id")
    #     if not template_id:
    #         return Response({"error": "Missing template_id parameter."}, status=400)

    #     try:
    #         template_id = int(template_id)
    #     except ValueError:
    #         return Response({"error": "Invalid template_id format."}, status=400)

    #     try:
    #         template = TplTemplate.objects.get(pktemplate=template_id)
    #     except TplTemplate.DoesNotExist:
    #         return Response({"error": "Template not found."}, status=404)

    #     object_key = f"rodriguez-zea/PROTOCOLARES/ACTAS DE TRANSFERENCIA DE BIENES MUEBLES REGISTRABLES/{template.filename}"

    #     # Connect to R2
    #     s3 = boto3.client(
    #         's3',
    #         endpoint_url=os.environ.get('CLOUDFLARE_R2_ENDPOINT'),
    #         aws_access_key_id=os.environ.get('CLOUDFLARE_R2_ACCESS_KEY'),
    #         aws_secret_access_key=os.environ.get('CLOUDFLARE_R2_SECRET_KEY'),
    #         config=Config(signature_version='s3v4'),
    #         region_name='auto',
    #     )

    #     try:
    #         # Retrieve the template file from R2
    #         s3_response = s3.get_object(Bucket=os.environ.get('CLOUDFLARE_R2_BUCKET'), Key=object_key)
    #         file_stream = s3_response['Body'].read()

    #         # Load the template into python-docx
    #         doc = Document(io.BytesIO(file_stream))

    #         # Placeholder data
    #         acquirer_data = {
    #             "[E.C_NOM_1]": "Carlos Alberto Gómez",
    #             "[E.C_NOM_2]": "Ana María Rodríguez",
    #             "[E.C_NACIONALIDAD_1]": "Peruano",
    #             "[E.C_NACIONALIDAD_2]": "Colombiana",
    #             "[E.C_TIP_DOC_1]": "DNI",
    #             "[E.C_TIP_DOC_2]": "Pasaporte",
    #             "[E.C_DOC_1]": "45678912",
    #             "[E.C_DOC_2]": "AB123456",
    #             "[E.C_OCUPACION_1]": "Ingeniero Civil",
    #             "[E.C_OCUPACION_2]": "Abogada",
    #             "[E.C_ESTADO_CIVIL_1]": "Casado",
    #             "[E.C_ESTADO_CIVIL_2]": "Soltera",
    #             "[E.C_DOMICILIO_1]": "Av. Los Próceres 123, Lima, Perú",
    #             "[E.C_DOMICILIO_2]": "Calle 45 #23-10, Bogotá, Colombia",
    #             "[E.C_CALIDAD_1]": "Comprador",
    #             "[E.C_CALIDAD_2]": "Compradora",
    #             "[E.C_IDE_1]": "Identificación válida",
    #             "[E.C_IDE_2]": "Identificación válida",
    #             "[E.C_FIRMA_1]": "Firma de Carlos Gómez",
    #             "[E.C_FIRMA_2]": "Firma de Ana Rodríguez",
    #             "[E.C_AMBOS_1]": "Ambos",
    #             "[E.C_AMBOS_2]": "Ambos",
    #         }

    #         # Add default values for missing placeholders
    #         placeholders = [
    #             "[E.C_NOM_3]", "[E.C_NACIONALIDAD_3]", "[E.C_TIP_DOC_3]", "[E.C_DOC_3]",
    #             "[E.C_OCUPACION_3]", "[E.C_ESTADO_CIVIL_3]", "[E.C_DOMICILIO_3]",
    #             "[E.C_CALIDAD_3]", "[E.C_IDE_3]", "[E.C_FIRMA_3]", "[E.C_AMBOS_3]"
    #         ]
    #         acquirer_data = add_default_values(acquirer_data, placeholders)

    #         # Handle singular/plural and gender-specific text
    #         acquirer_data = handle_singular_plural(acquirer_data, count=2, gender="M")

    #         # Replace placeholders in the document
    #         doc = replace_placeholders(doc, acquirer_data)

    #         # Remove unused placeholders
    #         doc = remove_placeholders(doc)

    #         # Save the modified document to a buffer
    #         buffer = io.BytesIO()
    #         doc.save(buffer)
    #         buffer.seek(0)

    #         # Respond directly with the modified document
    #         response = HttpResponse(
    #             buffer.read(),
    #             content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    #         )
    #         response['Content-Disposition'] = f'inline; filename="{template.filename}"'
    #         response['Content-Length'] = str(buffer.getbuffer().nbytes)
    #         response['Access-Control-Allow-Origin'] = '*'
    #         return response

    #     except Exception as e:
    #         return Response({"error": f"Failed to open document: {str(e)}"}, status=500)

    # @action(detail=False, methods=['get'], url_path='open-template')
    # def open_template(self, request):
    #     """
    #     Stream a filled Word document (.docx) directly from R2 so Word can open it.
    #     """
    #     template_id = request.query_params.get("template_id")
    #     if not template_id:
    #         return Response({"error": "Missing template_id parameter."}, status=400)

    #     try:
    #         template_id = int(template_id)  # Ensure template_id is an integer
    #     except ValueError:
    #         return Response({"error": "Invalid template_id format."}, status=400)

    #     try:
    #         template = TplTemplate.objects.get(pktemplate=template_id)
    #     except TplTemplate.DoesNotExist:
    #         return Response({"error": "Template not found."}, status=404)

    #     object_key = f"rodriguez-zea/PROTOCOLARES/ACTAS DE TRANSFERENCIA DE BIENES MUEBLES REGISTRABLES/{template.filename}"

    #     # Connect to R2
    #     s3 = boto3.client(
    #         's3',
    #         endpoint_url=os.environ.get('CLOUDFLARE_R2_ENDPOINT'),
    #         aws_access_key_id=os.environ.get('CLOUDFLARE_R2_ACCESS_KEY'),
    #         aws_secret_access_key=os.environ.get('CLOUDFLARE_R2_SECRET_KEY'),
    #         config=Config(signature_version='s3v4'),
    #         region_name='auto',
    #     )

    #     try:
    #         # Retrieve the template file from R2
    #         s3_response = s3.get_object(Bucket=os.environ.get('CLOUDFLARE_R2_BUCKET'), Key=object_key)
    #         file_stream = s3_response['Body'].read()

    #         # Load the template into python-docx
    #         doc = Document(io.BytesIO(file_stream))

    #         acquirer_data = {
    #             "[E.C_NOM_1]": "Carlos Alberto Gómez",
    #             "[E.C_NOM_2]": "Ana María Rodríguez",
    #             "[E.C_NACIONALIDAD_1]": "Peruano",
    #             "[E.C_NACIONALIDAD_2]": "Colombiana",
    #             "[E.C_TIP_DOC_1]": "DNI",
    #             "[E.C_TIP_DOC_2]": "Pasaporte",
    #             "[E.C_DOC_1]": "45678912",
    #             "[E.C_DOC_2]": "AB123456",
    #             "[E.C_OCUPACION_1]": "Ingeniero Civil",
    #             "[E.C_OCUPACION_2]": "Abogada",
    #             "[E.C_ESTADO_CIVIL_1]": "Casado",
    #             "[E.C_ESTADO_CIVIL_2]": "Soltera",
    #             "[E.C_DOMICILIO_1]": "Av. Los Próceres 123, Lima, Perú",
    #             "[E.C_DOMICILIO_2]": "Calle 45 #23-10, Bogotá, Colombia",
    #             "[E.C_CALIDAD_1]": "Comprador",
    #             "[E.C_CALIDAD_2]": "Compradora",
    #             "[E.C_IDE_1]": "Identificación válida",
    #             "[E.C_IDE_2]": "Identificación válida",
    #             "[E.C_FIRMA_1]": "Firma de Carlos Gómez",
    #             "[E.C_FIRMA_2]": "Firma de Ana Rodríguez",
    #             "[E.C_AMBOS_1]": "Ambos",
    #             "[E.C_AMBOS_2]": "Ambos",
    #         }

    #         # Add default values for missing placeholders
    #         placeholders = [
    #             "[E.C_NOM_3]", "[E.C_NACIONALIDAD_3]", "[E.C_TIP_DOC_3]", "[E.C_DOC_3]",
    #             "[E.C_OCUPACION_3]", "[E.C_ESTADO_CIVIL_3]", "[E.C_DOMICILIO_3]",
    #             "[E.C_CALIDAD_3]", "[E.C_IDE_3]", "[E.C_FIRMA_3]", "[E.C_AMBOS_3]"
    #         ]

    #         transferor_data = {
    #             "[E.P_NOM_1]": "Luis Fernando Pérez",
    #             "[E.P_NOM_2]": "María Elena Torres",
    #             "[E.P_NACIONALIDAD_1]": "Peruano",
    #             "[E.P_NACIONALIDAD_2]": "Ecuatoriana",
    #             "[E.P_TIP_DOC_1]": "DNI",
    #             "[E.P_TIP_DOC_2]": "Pasaporte",
    #             "[E.P_DOC_1]": "12345678",
    #             "[E.P_DOC_2]": "EC987654",
    #             "[E.P_OCUPACION_1]": "Empresario",
    #             "[E.P_OCUPACION_2]": "Contadora",
    #             "[E.P_ESTADO_CIVIL_1]": "Casado",
    #             "[E.P_ESTADO_CIVIL_2]": "Soltera",
    #             "[E.P_DOMICILIO_1]": "Av. Las Flores 456, Arequipa, Perú",
    #             "[E.P_DOMICILIO_2]": "Av. Amazonas 789, Quito, Ecuador",
    #             "[E.P_CALIDAD_1]": "Vendedor",
    #             "[E.P_CALIDAD_2]": "Vendedora",
    #             "[E.P_IDE_1]": "Identificación válida",
    #             "[E.P_IDE_2]": "Identificación válida",
    #             "[E.P_FIRMA_1]": "Firma de Luis Pérez",
    #             "[E.P_FIRMA_2]": "Firma de María Torres",
    #             "[E.P_AMBOS_1]": "Ambos",
    #             "[E.P_AMBOS_2]": "Ambos",
    #         }

    #         payment_data = {
    #             "[E.MONTO]": "45000",
    #             "[E.MON_VEHI]": "USD",
    #             "[E.MONTO_LETRAS]": "Cuarenta y cinco mil dólares americanos",
    #             "[E.MONEDA_C]": "$",
    #             "[E.SUNAT_MED_PAGO]": "007",
    #             "[E.DES_PRE_VEHI]": "Pago por transferencia vehicular",
    #             "[E.EXH_MED_PAGO]": "Se exhibió el comprobante de pago correspondiente.",
    #             "[E.MED_PAGO]": "Transferencia bancaria",
    #             "[E.FIN_MED_PAGO]": "Transferencia bancaria",
    #             "[E.FORMA_PAGO]": "Al contado",
    #         }

    #         vehicle_data = {
    #             "[E.PLACA]": "ABC-123",
    #             "[E.CLASE]": "Automóvil",
    #             "[E.MARCA]": "Toyota",
    #             "[E.MODELO]": "Corolla",
    #             "[E.AÑO_FABRICACION]": "2020",
    #             "[E.CARROCERIA]": "Sedán",
    #             "[E.COLOR]": "Rojo",
    #             "[E.NRO_MOTOR]": "1NZ-FE123456",
    #             "[E.NRO_SERIE]": "JTDBR32E123456789",
    #             "[E.FEC_INS]": "2021-05-15",
    #             "[E.FECHA_INSCRIPCION]": "15 de Mayo de 2021",
    #             "[E.ZONA_REGISTRAL]": "Zona Registral N° IX",
    #             "[E.NUM_ZONA_REG]": "9",
    #             "[E.SEDE]": "Lima",
    #         }

    #         document_metadata = {
    #             "[E.NRO_ESC]": "12345",
    #             "[E.F_IMPRESION]": "2023-07-01",
    #             "[E.FI]": "1",
    #             "[E.FF]": "10",
    #             "[E.S_IN]": "A001",
    #             "[E.S_FN]": "A010",
    #         }


    #         # doc = replace_placeholders(doc, combined_data)

    #         acquirer_data = add_default_values(acquirer_data, placeholders)

    #         # Format data for singular/plural and gender-specific text
    #         acquirer_data = format_data(acquirer_data, count=2, gender="M")

    #         combined_data = {**acquirer_data, **transferor_data, **vehicle_data, **payment_data, **document_metadata}

    #         # Replace placeholders in the document
    #         doc = replace_placeholders(doc, combined_data)

    #         # Remove unused placeholders
    #         doc = remove_placeholders(doc)

    #         # Save the modified document to a buffer
    #         buffer = io.BytesIO()
    #         doc.save(buffer)
    #         buffer.seek(0)

    #         # Respond directly with the modified document
    #         response = HttpResponse(
    #             buffer.read(),
    #             content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    #         )
    #         response['Content-Disposition'] = f'inline; filename="{template.filename}"'
    #         response['Content-Length'] = str(buffer.getbuffer().nbytes)
    #         response['Access-Control-Allow-Origin'] = '*'
    #         return response

    #     except Exception as e:
    #         return Response({"error": f"Failed to open document: {str(e)}"}, status=500)
    
    # @action(detail=False, methods=['get'], url_path='open-template')
    # def open_template(self, request):
    #     """
    #     Stream a filled Word document (.docx) directly from R2 so Word can open it.
    #     """
    #     template_id = request.query_params.get("template_id")
    #     if not template_id:
    #         return Response({"error": "Missing template_id parameter."}, status=400)

    #     try:
    #         template_id = int(template_id)  # Ensure template_id is an integer
    #     except ValueError:
    #         return Response({"error": "Invalid template_id format."}, status=400)

    #     try:
    #         template = TplTemplate.objects.get(pktemplate=template_id)
    #     except TplTemplate.DoesNotExist:
    #         return Response({"error": "Template not found."}, status=404)

    #     object_key = f"rodriguez-zea/PROTOCOLARES/ACTAS DE TRANSFERENCIA DE BIENES MUEBLES REGISTRABLES/{template.filename}"

    #     # Connect to R2
    #     s3 = boto3.client(
    #         's3',
    #         endpoint_url=os.environ.get('CLOUDFLARE_R2_ENDPOINT'),
    #         aws_access_key_id=os.environ.get('CLOUDFLARE_R2_ACCESS_KEY'),
    #         aws_secret_access_key=os.environ.get('CLOUDFLARE_R2_SECRET_KEY'),
    #         config=Config(signature_version='s3v4'),
    #         region_name='auto',
    #     )

    #     try:
    #         # Retrieve the template file from R2
    #         s3_response = s3.get_object(Bucket=os.environ.get('CLOUDFLARE_R2_BUCKET'), Key=object_key)
    #         file_stream = s3_response['Body'].read()

    #         # Load the template into python-docx
    #         doc = Document(io.BytesIO(file_stream))

    #         # Replace placeholders with actual data
    #         acquirer_data = {
    #             "[E.C_NOM_1]": "Juanito Pérez",
    #             "[E.C_NOM_2]": "María López",
    #             "[E.C_NACIONALIDAD_1]": "Español",
    #             "[E.C_NACIONALIDAD_2]": "Mexicana",
    #             "[E.C_TIP_DOC_1]": "DNI",
    #             "[E.C_TIP_DOC_2]": "Pasaporte",
    #             "[E.C_DOC_1]": "12345678",
    #             "[E.C_DOC_2]": "987654321",
    #             "[E.C_OCUPACION_1]": "Panadero",
    #             "[E.C_OCUPACION_2]": "Ingeniera",
    #             "[E.C_ESTADO_CIVIL_1]": "Soltero",
    #             "[E.C_ESTADO_CIVIL_2]": "Casada",
    #             "[E.C_DOMICILIO_1]": "Calle Falsa 123, Madrid",
    #             "[E.C_DOMICILIO_2]": "Avenida Siempre Viva 456, Ciudad de México",
    #             "[E.C_CALIDAD_1]": "Comprador",
    #             "[E.C_CALIDAD_2]": "Compradora",
    #             "[E.C_IDE_1]": "Identificación válida",
    #             "[E.C_IDE_2]": "Identificación válida",
    #             "[E.C_FIRMA_1]": "Firma de Juanito",
    #             "[E.C_FIRMA_2]": "Firma de María",
    #             "[E.C_AMBOS_1]": "Ambos",
    #             "[E.C_AMBOS_2]": "Ambos",
    #         }

    #         # Replace placeholders in the document
    #         for paragraph in doc.paragraphs:
    #             for placeholder, value in acquirer_data.items():
    #                 if placeholder in paragraph.text:
    #                     paragraph.text = paragraph.text.replace(placeholder, value)

    #         # Save the modified document to a buffer
    #         buffer = io.BytesIO()
    #         doc.save(buffer)
    #         buffer.seek(0)

    #         # Respond directly with the modified document
    #         response = HttpResponse(
    #             buffer.read(),
    #             content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    #         )
    #         response['Content-Disposition'] = f'inline; filename="{template.filename}"'
    #         response['Content-Length'] = str(buffer.getbuffer().nbytes)
    #         response['Access-Control-Allow-Origin'] = '*'
    #         return response

    #     except Exception as e:
    #         return Response({"error": f"Failed to open document: {str(e)}"}, status=500)
    # /to download
    # @action(detail=False, methods=['get'], url_path='open-template')
    # def open_template(self, request):
    #     """
    #     Stream a filled Word document (.docx) directly from R2 so Word can open it.
    #     """
    #     template_id = request.query_params.get("template_id")
    #     if not template_id:
    #         return Response({"error": "Missing template_id parameter."}, status=400)

    #     try:
    #         template_id = int(template_id)  # this ensures we only accept clean integers
    #     except ValueError:
    #         return Response({"error": "Invalid template_id format."}, status=400)

    #     try:
    #         template = TplTemplate.objects.get(pktemplate=template_id)
    #     except TplTemplate.DoesNotExist:
    #         return Response({"error": "Template not found."}, status=404)

    #     object_key = f"rodriguez-zea/PROTOCOLARES/ACTAS DE TRANSFERENCIA DE BIENES MUEBLES REGISTRABLES/{template.filename}"

    #     # Connect to R2
    #     s3 = boto3.client(
    #         's3',
    #         endpoint_url=os.environ.get('CLOUDFLARE_R2_ENDPOINT'),
    #         aws_access_key_id=os.environ.get('CLOUDFLARE_R2_ACCESS_KEY'),
    #         aws_secret_access_key=os.environ.get('CLOUDFLARE_R2_SECRET_KEY'),
    #         config=Config(signature_version='s3v4'),
    #         region_name='auto',
    #     )

    #     try:
    #         # Retrieve and modify the file
    #         s3_response = s3.get_object(Bucket=os.environ.get('CLOUDFLARE_R2_BUCKET'), Key=object_key)
    #         file_stream = s3_response['Body'].read()

    #         doc = Document(io.BytesIO(file_stream))

    #         acquirer_data = {
    #             "[E.C_NOM_1]": "Juanito Pérez ",
    #             # ... your other placeholder replacements ...
    #         }

    #         for paragraph in doc.paragraphs:
    #             for placeholder, value in acquirer_data.items():
    #                 if placeholder in paragraph.text:
    #                     paragraph.text = paragraph.text.replace(placeholder, value)

    #         buffer = io.BytesIO()
    #         doc.save(buffer)
    #         buffer.seek(0)

    #         # Respond directly with the document
    #         # response = HttpResponse(buffer.read(), content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    #         # response['Content-Disposition'] = f'inline; filename="{template.filename}"'  # NOT attachment
    #         # return response

    #         response = HttpResponse(
    #             buffer.read(),
    #             content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    #         )
    #         response['Content-Disposition'] = f'inline; filename="{template.filename}"'
    #         response['Content-Length'] = str(buffer.getbuffer().nbytes)
    #         response['Access-Control-Allow-Origin'] = '*'
    #         return response

    #     except Exception as e:
    #         return Response({"error": f"Failed to open document: {str(e)}"}, status=500)

    
    # @action(detail=False, methods=['get'], url_path='template-download')
    # def download_template(self, request):
    #     """
    #     Return a pre-signed URL for the filled .docx template from R2 given a template_id.
    #     """
    #     template_id = request.query_params.get("template_id")
    #     if not template_id:
    #         return Response({"error": "Missing template_id parameter."}, status=400)

    #     try:
    #         template = TplTemplate.objects.get(pktemplate=template_id)
    #     except TplTemplate.DoesNotExist:
    #         return Response({"error": "Template not found."}, status=404)

    #     object_key = f"rodriguez-zea/PROTOCOLARES/ACTAS DE TRANSFERENCIA DE BIENES MUEBLES REGISTRABLES/{template.filename}"

    #     # Connect to R2
    #     s3 = boto3.client(
    #         's3',
    #         endpoint_url=os.environ.get('CLOUDFLARE_R2_ENDPOINT'),
    #         aws_access_key_id=os.environ.get('CLOUDFLARE_R2_ACCESS_KEY'),
    #         aws_secret_access_key=os.environ.get('CLOUDFLARE_R2_SECRET_KEY'),
    #         config=Config(signature_version='s3v4'),
    #         region_name='auto',
    #     )

    #     try:
    #         # Retrieve the template file from R2
    #         s3_response = s3.get_object(
    #             Bucket=os.environ.get('CLOUDFLARE_R2_BUCKET'),
    #             Key=object_key,
    #         )
    #         file_stream = s3_response['Body'].read()

    #         # Load and modify the document
    #         doc = Document(io.BytesIO(file_stream))

    #         acquirer_data = {
    #             "[E.C_NOM_1]": "Juanito Pérez ",
    #             "[E.C_NOM_2]": "María López ",
    #             "[E.C_NACIONALIDAD_1]": "Mexicana",
    #             "[E.C_NACIONALIDAD_2]": "",
    #             "[E.C_TIP_DOC_1]": "DNI",
    #             "[E.C_TIP_DOC_2]": "",
    #             "[E.C_DOC_1]": "12345678",
    #             "[E.C_DOC_2]": "",
    #             "[E.C_OCUPACION_1]": "Panadero",
    #             "[E.C_OCUPACION_2]": "",
    #             "[E.C_ESTADO_CIVIL_1]": "Soltero",
    #             "[E.C_ESTADO_CIVIL_2]": "",
    #             "[E.C_DOMICILIO_1]": "Calle Falsa 123, Madrid",
    #             "[E.C_DOMICILIO_2]": "",
    #             "[E.C_CALIDAD_1]": "Comprador",
    #             "[E.C_CALIDAD_2]": "",
    #             "[E.C_IDE_1]": "",
    #             "[E.C_IDE_2]": "",
    #             "[E.C_FIRMA_1]": "Firma de Juanito",
    #             "[E.C_FIRMA_2]": "Firma de María",
    #             "[E.C_AMBOS_1]": "Ambos",
    #             "[E.C_AMBOS_2]": "Ambos",
    #         }

    #         for paragraph in doc.paragraphs:
    #             for placeholder, value in acquirer_data.items():
    #                 if placeholder in paragraph.text:
    #                     paragraph.text = paragraph.text.replace(placeholder, value)

    #         # Save to in-memory buffer
    #         buffer = io.BytesIO()
    #         doc.save(buffer)
    #         buffer.seek(0)

    #         # Upload to R2 under a new key
    #         new_key = f"rodriguez-zea/generated/{uuid.uuid4()}_{template.filename}"

    #         s3.put_object(
    #             Bucket=os.environ.get('CLOUDFLARE_R2_BUCKET'),
    #             Key=new_key,
    #             Body=buffer,
    #             ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    #         )

    #         # Generate pre-signed URL
    #         presigned_url = s3.generate_presigned_url(
    #             ClientMethod='get_object',
    #             Params={
    #                 'Bucket': os.environ.get('CLOUDFLARE_R2_BUCKET'),
    #                 'Key': new_key,
    #             },
    #             ExpiresIn=600  # 10 minutes
    #         )

    #         return Response({"url": presigned_url})

    #     except Exception as e:
    #         return Response({"error": f"Failed to process document: {str(e)}"}, status=500)

    

    # @action(detail=False, methods=['get'], url_path='template-download')
    # def download_template(self, request):
    #     """
    #     Return the .docx file from R2 given a template_id and fill Acquirer (Buyer) data.
    #     """
    #     template_id = request.query_params.get("template_id")
    #     if not template_id:
    #         return Response({"error": "Missing template_id parameter."}, status=400)

    #     try:
    #         template = TplTemplate.objects.get(pktemplate=template_id)
    #     except TplTemplate.DoesNotExist:
    #         return Response({"error": "Template not found."}, status=404)

    #     object_key = f"rodriguez-zea/PROTOCOLARES/ACTAS DE TRANSFERENCIA DE BIENES MUEBLES REGISTRABLES/{template.filename}"

    #     # Connect to R2 via boto3
    #     s3 = boto3.client(
    #         's3',
    #         endpoint_url=os.environ.get('CLOUDFLARE_R2_ENDPOINT'),
    #         aws_access_key_id=os.environ.get('CLOUDFLARE_R2_ACCESS_KEY'),
    #         aws_secret_access_key=os.environ.get('CLOUDFLARE_R2_SECRET_KEY'),
    #         config=Config(signature_version='s3v4'),
    #         region_name='auto',
    #     )

    #     try:
    #         # Retrieve the template file from R2
    #         s3_response = s3.get_object(
    #             Bucket=os.environ.get('CLOUDFLARE_R2_BUCKET'),
    #             Key=object_key,
    #         )
    #         file_stream = s3_response['Body'].read()

    #         # Load the template into python-docx
    #         doc = Document(io.BytesIO(file_stream))

    #         # Fill Acquirer (Buyer) data with funny Spanish names
    #         acquirer_data = {
    #             "[E.C_NOM_1]": "Juanito Pérez ",
    #             "[E.C_NOM_2]": "María López ",
    #             "[E.C_NACIONALIDAD_1]": "Mexicana",
    #             "[E.C_NACIONALIDAD_2]": "",
    #             "[E.C_TIP_DOC_1]": "DNI",
    #             "[E.C_TIP_DOC_2]": "",
    #             "[E.C_DOC_1]": "12345678",
    #             "[E.C_DOC_2]": "",
    #             "[E.C_OCUPACION_1]": "Panadero",
    #             "[E.C_OCUPACION_2]": "",
    #             "[E.C_ESTADO_CIVIL_1]": "Soltero",
    #             "[E.C_ESTADO_CIVIL_2]": "",
    #             "[E.C_DOMICILIO_1]": "Calle Falsa 123, Madrid",
    #             "[E.C_DOMICILIO_2]": "",
    #             "[E.C_CALIDAD_1]": "Comprador",
    #             "[E.C_CALIDAD_2]": "",
    #             "[E.C_IDE_1]": "",
    #             "[E.C_IDE_2]": "",
    #             "[E.C_FIRMA_1]": "Firma de Juanito",
    #             "[E.C_FIRMA_2]": "Firma de María",
    #             "[E.C_AMBOS_1]": "Ambos",
    #             "[E.C_AMBOS_2]": "Ambos",
    #         }

    #         # Replace placeholders in the document
    #         for paragraph in doc.paragraphs:
    #             for placeholder, value in acquirer_data.items():
    #                 if placeholder in paragraph.text:
    #                     paragraph.text = paragraph.text.replace(placeholder, value)

    #         # Save the modified document to a temporary file
    #         temp_file_path = f"/tmp/{template.filename}"
    #         doc.save(temp_file_path)

    #         # Return the modified document as a response
    #         with open(temp_file_path, "rb") as modified_file:
    #             response = HttpResponse(modified_file.read(), content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    #             response['Content-Disposition'] = f'attachment; filename="{template.filename}"'
    #             return response

    #     except Exception as e:
    #         return Response({"error": f"Failed to process document: {str(e)}"}, status=500)
    
    # @action(detail=False, methods=['get'], url_path='template-download')
    # def download_template(self, request):
    #     """
    #     Return the .docx file from R2 given a template_id.
    #     """
    #     template_id = request.query_params.get("template_id")
    #     if not template_id:
    #         return Response({"error": "Missing template_id parameter."}, status=400)

    #     try:
    #         template = TplTemplate.objects.get(pktemplate=template_id)
    #     except TplTemplate.DoesNotExist:
    #         return Response({"error": "Template not found."}, status=404)

    #     object_key = f"rodriguez-zea/PROTOCOLARES/ACTAS DE TRANSFERENCIA DE BIENES MUEBLES REGISTRABLES/{template.filename}"

    #     # Connect to R2 via boto3
    #     s3 = boto3.client(
    #         's3',
    #         endpoint_url=os.environ.get('CLOUDFLARE_R2_ENDPOINT'),
    #         aws_access_key_id=os.environ.get('CLOUDFLARE_R2_ACCESS_KEY'),
    #         aws_secret_access_key=os.environ.get('CLOUDFLARE_R2_SECRET_KEY'),
    #         config=Config(signature_version='s3v4'),
    #         region_name='auto',
    #     )

    #     try:
    #         s3_response = s3.get_object(
    #             Bucket=os.environ.get('CLOUDFLARE_R2_BUCKET'),
    #             Key=object_key,
    #         )
    #         file_stream = s3_response['Body'].read()
    #         response = HttpResponse(file_stream, content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    #         response['Content-Disposition'] = f'attachment; filename="{template.filename}"'
    #         return response
    #     except Exception as e:
    #         return Response({"error": f"Failed to download document: {str(e)}"}, status=500)
