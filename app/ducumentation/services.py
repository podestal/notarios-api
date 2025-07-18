import boto3
from botocore.client import Config
from django.conf import settings
import os
import io
from docx import Document
from docxtpl import DocxTemplate
from docxcompose.properties import CustomProperties
from docx.shared import RGBColor, Pt
from decimal import Decimal
from typing import Dict, Any
from .constants import ROLE_LABELS, TIPO_DOCUMENTO, CIVIL_STATUS
import re
from datetime import datetime
from django.http import HttpResponse, JsonResponse
from notaria.models import TplTemplate, Detallevehicular, Patrimonial, Contratantes, Actocondicion, Cliente2, Nacionalidades, Kardex, Usuarios, Sedesregistrales
from notaria.constants import MONEDAS, OPORTUNIDADES_PAGO, FORMAS_PAGO
from .utils import NumberToLetterConverter


class VehicleTransferDocumentService:
    """
    Django service to generate vehicle transfer documents based on the PHP logic
    """
    
    def __init__(self):
        self.letras = NumberToLetterConverter()
    
    def generate_vehicle_transfer_document(self, template_id: int, num_kardex: str, action: str = 'generate', mode: str = "download") -> HttpResponse:
        """
        Main method to generate vehicle transfer document
        """
        try:
            template = self._get_template_from_r2(template_id)
            document_data = self.get_document_data(num_kardex)
            doc = self._process_document(template, document_data)
            self.remove_unfilled_placeholders(doc)
            
            # Save the document to R2 before returning it
            upload_success = self.create_documento_in_r2(doc, num_kardex)
            if not upload_success:
                print(f"WARNING: Failed to upload document to R2 for kardex: {num_kardex}")
            
            return self._create_response(doc, f"__PROY__{num_kardex}.docx", num_kardex, mode)
        except FileNotFoundError as e:
            return HttpResponse(str(e), status=404)
        except Exception as e:
            return HttpResponse(f"Error generating document: {str(e)}", status=500)

    def create_documento_in_r2(self, doc, kardex):
        """
        Create a new document in R2 storage
        """
        try:
            # Save the document to a bytes buffer
            from io import BytesIO
            buffer = BytesIO()
            doc.save(buffer)
            buffer.seek(0)
            doc_content = buffer.read()
            
            # Define the object key for R2
            object_key = f"rodriguez-zea/documentos/__PROY__{kardex}.docx"
            
            # Upload to R2
            s3 = boto3.client(
                's3',
                endpoint_url=os.environ.get('CLOUDFLARE_R2_ENDPOINT'),
                aws_access_key_id=os.environ.get('CLOUDFLARE_R2_ACCESS_KEY'),
                aws_secret_access_key=os.environ.get('CLOUDFLARE_R2_SECRET_KEY'),
                config=Config(signature_version='s3v4'),
                region_name='auto',
            )
            
            s3.upload_fileobj(
                BytesIO(doc_content),
                os.environ.get('CLOUDFLARE_R2_BUCKET'),
                object_key
            )
            
            print(f"DEBUG: Document uploaded to R2: {object_key}")
            return True
            
        except Exception as e:
            print(f"ERROR: Failed to upload document to R2: {e}")
            return False


    def remove_unfilled_placeholders(self, doc):
        """
        Remove all [E.SOMETHING] placeholders and hide {{SOMETHING}} placeholders from user.
        Keep and hide: {{NRO_ESC}}, {{FI}}, {{FF}}, {{S_IN}}, {{S_FN}}, {{FECHA_ACT}}
        Remove all others: [E.P_NOM_2], [E.C_NOM_2], etc.
        """
        import re
        placeholder_pattern = re.compile(r'\[E\.[A-Z0-9_]+\]')
        curly_placeholder_pattern = re.compile(r'\{\{[A-Z0-9_]+\}\}')
        representation_pattern = re.compile(
            r'EN REPRESENTACION DE\s*Y[\s.·…‥⋯⋮⋱⋰⋯—–-]*', re.IGNORECASE
        )

        # List of placeholders to keep and hide
        keep_placeholders = ['{{NRO_ESC}}', '{{FI}}', '{{FF}}', '{{S_IN}}', '{{S_FN}}', '{{FECHA_ACT}}']

        def clean_runs(runs):
            # Remove [E.SOMETHING] placeholders and hide {{SOMETHING}} placeholders
            for run in runs:
                # Remove all [E.SOMETHING] placeholders
                run.text = placeholder_pattern.sub('', run.text)
                
                # Hide {{SOMETHING}} placeholders by making them white
                # BUT only if they are actually placeholders (not real values)
                if curly_placeholder_pattern.search(run.text):
                    # Check if this is actually a placeholder or a real value
                    should_hide = True
                    for placeholder in keep_placeholders:
                        if placeholder in run.text:
                            # If it's a placeholder we want to keep, check if it has a real value
                            # Real values would not be exactly the placeholder text
                            if run.text.strip() == placeholder:
                                # This is still a placeholder, hide it
                                run.font.color.rgb = RGBColor(255, 255, 255)  # White color
                                print(f"DEBUG: Hiding curly placeholder in run: '{run.text}'")
                            else:
                                # This has a real value, don't hide it
                                should_hide = False
                                print(f"DEBUG: Keeping visible value in run: '{run.text}'")
                            break
                    
                    # For other curly placeholders not in keep_placeholders, hide them
                    if should_hide and not any(placeholder in run.text for placeholder in keep_placeholders):
                        run.font.color.rgb = RGBColor(255, 255, 255)  # White color
                        print(f"DEBUG: Hiding other curly placeholder in run: '{run.text}'")
                
                # Remove unwanted phrase
                run.text = representation_pattern.sub('', run.text)

        # Clean paragraphs
        for paragraph in doc.paragraphs:
            clean_runs(paragraph.runs)
        # Clean tables
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        clean_runs(paragraph.runs)
    
    def clean_text(self, text):
        # Remove duplicate commas, semicolons, and spaces
        text = re.sub(r'[;,]{2,}', lambda m: m.group(0)[0], text)  # Replace multiple , or ; with one
        text = re.sub(r'([;,])\s*([;,])', r'\1', text)  # Remove space between ,; or ;,
        text = re.sub(r'\s{2,}', ' ', text)  # Replace multiple spaces with one
        text = re.sub(r'\s+,', ',', text)  # Remove space before comma
        text = re.sub(r'\s+;', ';', text)  # Remove space before semicolon
        text = re.sub(r',\s*;', ';', text)  # Replace ', ;' with ';'
        text = re.sub(r';\s*,', ',', text)  # Replace '; ,' with ','
        text = re.sub(r'([;,]){2,}', r'\1', text)  # Remove any remaining double punctuation
        text = re.sub(r'\s{2,}', ' ', text)  # Again, just in case
        text = re.sub(r'\s*([;,])\s*', r'\1 ', text)  # Normalize space after punctuation
        text = re.sub(r'\s{2,}', ' ', text)  # Final pass for spaces
        text = re.sub(r'\s+\.', '.', text)  # Remove space before period
        text = re.sub(r'\s+\,', ',', text)  # Remove space before comma
        text = re.sub(r'\s+\;', ';', text)  # Remove space before semicolon
        text = re.sub(r'\s+\:', ':', text)  # Remove space before colon
        text = re.sub(r'\s+\?', '?', text)  # Remove space before question mark
        text = re.sub(r'\s+\!', '!', text)  # Remove space before exclamation mark
        # Remove leading/trailing punctuation and spaces
        text = re.sub(r'^[,;\s]+', '', text)
        text = re.sub(r'[,;\s]+$', '', text)
        return text.strip()
    
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
        
        # Template path in simplified structure
        object_key = f"rodriguez-zea/plantillas/{template.filename}"
        
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
    
    def get_document_data(self, num_kardex: str) -> Dict[str, Any]:
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
        
        # Escrituración data 
        # escrituracion_data = self._get_escrituracion_data(num_kardex)

        # Merge all data
        final_data = {}
        final_data.update(document_data)
        final_data.update(vehicle_data)
        final_data.update(payment_data)
        final_data.update(contractors_data)
        # final_data.update(escrituracion_data)
        
        return final_data
    
    def _get_document_data(self, num_kardex: str, anio_kardex: str) -> Dict[str, str]:
        """
        Get document basic information from the database, matching the PHP logic.
        """

        kardex = Kardex.objects.filter(kardex=num_kardex).first()
        if not kardex:
            # Fallbacks if not found
            numero_escritura = ''
            fecha_escritura = ''
            usuario = ''
            usuario_dni = ''
            folioini = ''
            foliofin = ''
            papelini = ''
            papelfin = ''

        else:
            numero_escritura = kardex.numescritura or ''
            fecha_escritura = kardex.fechaescritura or ''
            usuario = kardex.responsable_new or ''
            folioini = kardex.folioini or ''
            foliofin = kardex.foliofin or ''
            papelini = kardex.papelini or ''
            papelfin = kardex.papelfin or ''
            # Get user DNI
            usuario_dni = ''
            if kardex.idusuario:
                usuario_obj = Usuarios.objects.filter(idusuario=kardex.idusuario).first()
                usuario_dni = usuario_obj.dni if usuario_obj else ''
        
        return {
            'K': num_kardex,
            'NRO_ESC': f"{numero_escritura}({self.letras.number_to_letters(numero_escritura)})" if numero_escritura else '{{NRO_ESC}}',
            'NUM_REG': '1',
            'FEC_LET': '',
            'F_IMPRESION': '',
            'USUARIO': usuario,
            'USUARIO_DNI': usuario_dni,
            'NRO_MIN': usuario_dni,
            'COMPROBANTE': 'sin',
            'O_S': num_kardex,
            'ORDEN_SERVICIO': num_kardex,
            'FECHA_ACT': fecha_escritura,
            'FECHA_MAX': '',
            'FI': folioini,
            'FF': foliofin,
            'S_IN': papelini,
            'S_FN': papelfin,
        }
    
    def _get_vehicle_data(self, kardex) -> Dict[str, str]:
        vehicle = Detallevehicular.objects.filter(kardex=kardex).first()
        sede = ''
        num_zona = ''
        zona_registral = ''
        if vehicle and vehicle.idsedereg:
            sede_obj = Sedesregistrales.objects.filter(idsedereg=vehicle.idsedereg).first()
            if sede_obj:
                sede = sede_obj.dessede or ''
                num_zona = sede_obj.num_zona or ''
                zona_registral = sede_obj.dessede or ''
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
            'ZONA_REGISTRAL': zona_registral,
            'NUM_ZONA_REG': num_zona,
            'SEDE': sede,
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

    def _get_contractors_data(self, kardex) -> Dict[str, str]:
        """
        Get contractors (transferor and acquirer) information, including both natural and legal persons.
        Robustly handles missing nacionalidad and fills all placeholders for both types.
        Handles EN REPRESENTACION DE for both persona natural and juridica.
        """
        TRANSFEROR_ROLES = {
            "VENDEDOR", "DONANTE", "PODERDANTE", "OTORGANTE", "REPRESENTANTE", "ANTICIPANTE",
            "ADJUDICANTE", "USUFRUCTUANTE", "TRANSFERENTE", "TITULAR", "MUTUANTE", "PROPIETARIO",
            "DEUDOR", "ASOCIANTE", "TRANSFERENTE / PROPIETARIO (VENDEDOR)", "APODERADO"
        }
        ACQUIRER_ROLES = {
            "COMPRADOR", "DONATARIO", "APODERADO", "ANTICIPADO", "ADJUDICATARIO", "USUFRUCTUARIO",
            "TESTIGO A RUEGO", "ADQUIRIENTE", "ACREEDOR", "OTORGADO", "MUTUATARIO", "BENEFICIARIA",
            "ASOCIADO", "ADQUIRENTE / BENEFICIARIO (COMPRADOR)", "REPRESENTANTE"
        }
        REPRESENTATIVE_ROLES = {"APODERADO", "REPRESENTANTE"}

        contratantes = list(Contratantes.objects.filter(kardex=kardex))
        id_to_contratante = {c.idcontratante: c for c in contratantes}
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
            # Robust nacionalidad handling
            if cliente2.tipper == 'J':
                nacionalidad = 'EMPRESA'
                sexo = ''
                ocupacion = ''
                estado_civil = ''
                direccion = cliente2.domfiscal or ''
            else:
                nacionalidad_obj = Nacionalidades.objects.filter(idnacionalidad=cliente2.nacionalidad).first()
                nacionalidad = nacionalidad_obj.descripcion if nacionalidad_obj else ''
                sexo = cliente2.sexo or ''
                ocupacion = re.split(r'[/,;]', cliente2.detaprofesion)[0].strip() if cliente2.detaprofesion else ''
                estado_civil = self.get_civil_status_by_gender(CIVIL_STATUS[cliente2.idestcivil]['label'].upper(), sexo) if cliente2.idestcivil in CIVIL_STATUS else ''
                direccion = cliente2.direccion or ''
            contratante_obj = {
                'idcontratante': contratante.idcontratante,
                'sexo': sexo,
                'condiciones': (', ').join(condiciones_list),
                'condicion_str': condiciones_list[0] if condiciones_list else '',
                'nombres': f'{cliente2.prinom} {cliente2.segnom} {cliente2.apepat} {cliente2.apemat}' if cliente2.tipper == 'N' else cliente2.razonsocial or '',
                'nacionalidad': self.get_nationality_by_gender(nacionalidad, sexo) if cliente2.tipper == 'N' else nacionalidad,
                'tipoDocumento': TIPO_DOCUMENTO[cliente2.idtipdoc]['destipdoc'] if cliente2.idtipdoc in TIPO_DOCUMENTO else '',
                'numeroDocumento': cliente2.numdoc or '',
                'ocupacion': ocupacion,
                'estadoCivil': estado_civil,
                'direccion': direccion,
                'idcontratanterp': getattr(contratante, 'idcontratanterp', None),
                'tipper': cliente2.tipper,  # 'N' for natural, 'J' for juridica
                'razonsocial': cliente2.razonsocial or '',
                'domfiscal': cliente2.domfiscal or '',
                'numpartida': cliente2.numpartida or '',
                'idubigeo': cliente2.idubigeo or '',
                'numdoc_empresa': cliente2.numdoc if cliente2.tipper == 'J' else '',
            }
            contratantes_list.append(contratante_obj)

        naturals = [c for c in contratantes_list if c['tipper'] == 'N']
        companies = [c for c in contratantes_list if c['tipper'] == 'J']

        transferors = []
        transferor_companies = []
        for c in naturals:
            if c['condicion_str'] in REPRESENTATIVE_ROLES and c.get('idcontratanterp'):
                principal_contratante = id_to_contratante.get(c['idcontratanterp'])
                if principal_contratante:
                    principal_cliente = Cliente2.objects.get(idcontratante=principal_contratante.idcontratante)
                    if principal_cliente.tipper == 'J':
                        principal_name = principal_cliente.razonsocial or ''
                    else:
                        principal_name = f'{principal_cliente.prinom} {principal_cliente.segnom} {principal_cliente.apepat} {principal_cliente.apemat}'
                    c = c.copy()
                    c['nombres'] = f"{c['nombres'].strip()}, EN REPRESENTACION DE {principal_name.strip()}"
                transferors.append(c)
            elif c['condicion_str'] in TRANSFEROR_ROLES:
                represented = any(
                    a['condicion_str'] in REPRESENTATIVE_ROLES and a.get('idcontratanterp') == c.get('idcontratante')
                    for a in naturals
                )
                if not represented:
                    transferors.append(c)
        for c in companies:
            if c['condicion_str'] in TRANSFEROR_ROLES:
                transferor_companies.append(c)

        acquirers = []
        acquirer_companies = []
        for c in naturals:
            if c['condicion_str'] in REPRESENTATIVE_ROLES and c.get('idcontratanterp'):
                principal_contratante = id_to_contratante.get(c['idcontratanterp'])
                if principal_contratante:
                    principal_cliente = Cliente2.objects.get(idcontratante=principal_contratante.idcontratante)
                    if principal_cliente.tipper == 'J':
                        principal_name = principal_cliente.razonsocial or ''
                    else:
                        principal_name = f'{principal_cliente.prinom} {principal_cliente.segnom} {principal_cliente.apepat} {principal_cliente.apemat}'
                    principal_condiciones = principal_contratante.condicion.split('/')
                    principal_condicion_str = Actocondicion.objects.get(idcondicion=principal_condiciones[0].split('.')[0]).condicion if principal_condiciones and principal_condiciones[0] else ''
                    if principal_condicion_str in ACQUIRER_ROLES:
                        c = c.copy()
                        c['nombres'] = f"{c['nombres'].strip()}, EN REPRESENTACION DE {principal_name.strip()}"
                        acquirers.append(c)
            elif c['condicion_str'] in ACQUIRER_ROLES:
                represented = any(
                    a['condicion_str'] in REPRESENTATIVE_ROLES and a.get('idcontratanterp') == c.get('idcontratante')
                    for a in naturals
                )
                if not represented:
                    acquirers.append(c)
        for c in companies:
            if c['condicion_str'] in ACQUIRER_ROLES:
                acquirer_companies.append(c)

        contractors_data = {}

        for idx, t in enumerate(transferors, 1):
            contractors_data[f'P_NOM_{idx}'] = t['nombres'] + ', '
            contractors_data[f'P_NACIONALIDAD_{idx}'] = t['nacionalidad'] + ', '
            contractors_data[f'P_TIP_DOC_{idx}'] = t['tipoDocumento']
            contractors_data[f'P_DOC_{idx}'] = self.get_identification_phrase(t['sexo'], t['tipoDocumento'], t['numeroDocumento'])
            contractors_data[f'P_OCUPACION_{idx}'] = t['ocupacion']
            contractors_data[f'P_ESTADO_CIVIL_{idx}'] = t['estadoCivil']
            contractors_data[f'P_DOMICILIO_{idx}'] = 'CON DOMICILIO EN ' + t['direccion']
            contractors_data[f'P_IDE_{idx}'] = ' '
            contractors_data[f'SEXO_P_{idx}'] = t['sexo']
            contractors_data[f'P_FIRMAN_{idx}'] = t['nombres'] + ', '
            contractors_data[f'P_IMPRIME_{idx}'] = f' FIRMA EN: {self.letras.date_to_letters(datetime.now())}'

        for idx, c in enumerate(acquirers, 1):
            contractors_data[f'C_NOM_{idx}'] = c['nombres'] + ', '
            contractors_data[f'C_NACIONALIDAD_{idx}'] = c['nacionalidad'] + ', '
            contractors_data[f'C_TIP_DOC_{idx}'] = c['tipoDocumento']
            contractors_data[f'C_DOC_{idx}'] = self.get_identification_phrase(c['sexo'], c['tipoDocumento'], c['numeroDocumento'])
            contractors_data[f'C_OCUPACION_{idx}'] = c['ocupacion']
            contractors_data[f'C_ESTADO_CIVIL_{idx}'] = c['estadoCivil']
            contractors_data[f'C_DOMICILIO_{idx}'] = 'CON DOMICILIO EN ' + c['direccion']
            contractors_data[f'C_IDE_{idx}'] = ' '
            contractors_data[f'SEXO_C_{idx}'] = c['sexo']
            contractors_data[f'C_FIRMAN_{idx}'] = c['nombres'] + ', '
            contractors_data[f'C_IMPRIME_{idx}'] = f' FIRMA EN: {self.letras.date_to_letters(datetime.now())}'

        for idx, t in enumerate(transferor_companies, 1):
            contractors_data[f'NOMBRE_EMPRESA_{idx}'] = t['razonsocial']
            contractors_data[f'INS_EMPRESA_{idx}'] = f'INSCRITA EN LA PARTIDA ELECTRONICA N° {t["numpartida"]}'
            contractors_data[f'RUC_{idx}'] = t['numdoc_empresa']
            contractors_data[f'DOMICILIO_EMPRESA_{idx}'] = f'CON DOMICILIO EN {t["domfiscal"]}'

        for idx, c in enumerate(acquirer_companies, 1):
            contractors_data[f'NOMBRE_EMPRESA_{idx+len(transferor_companies)}'] = c['razonsocial']
            contractors_data[f'INS_EMPRESA_{idx+len(transferor_companies)}'] = f'INSCRITA EN LA PARTIDA ELECTRONICA N° {c["numpartida"]}'
            contractors_data[f'RUC_{idx+len(transferor_companies)}'] = c['numdoc_empresa']
            contractors_data[f'DOMICILIO_EMPRESA_{idx+len(transferor_companies)}'] = f'CON DOMICILIO EN {c["domfiscal"]}'

        for idx in range(len(transferors) + 1, 11):
            contractors_data[f'P_NOM_{idx}'] = f'[E.P_NOM_{idx}]'
            contractors_data[f'P_NACIONALIDAD_{idx}'] = f'[E.P_NACIONALIDAD_{idx}]'
            contractors_data[f'P_TIP_DOC_{idx}'] = f'[E.P_TIP_DOC_{idx}]'
            contractors_data[f'P_DOC_{idx}'] = f'[E.P_DOC_{idx}]'
            contractors_data[f'P_OCUPACION_{idx}'] = f'[E.P_OCUPACION_{idx}]'
            contractors_data[f'P_ESTADO_CIVIL_{idx}'] = f'[E.P_ESTADO_CIVIL_{idx}]'
            contractors_data[f'P_DOMICILIO_{idx}'] = f'[E.P_DOMICILIO_{idx}]'
            contractors_data[f'P_IDE_{idx}'] = f'[E.P_IDE_{idx}]'
            contractors_data[f'SEXO_P_{idx}'] = f'[E.SEXO_P_{idx}]'
            contractors_data[f'P_FIRMAN_{idx}'] = f'[E.P_FIRMAN_{idx}]'
            contractors_data[f'P_IMPRIME_{idx}'] = f'[E.P_IMPRIME_{idx}]'

        for idx in range(len(acquirers) + 1, 11):
            contractors_data[f'C_NOM_{idx}'] = f'[E.C_NOM_{idx}]'
            contractors_data[f'C_NACIONALIDAD_{idx}'] = f'[E.C_NACIONALIDAD_{idx}]'
            contractors_data[f'C_TIP_DOC_{idx}'] = f'[E.C_TIP_DOC_{idx}]'
            contractors_data[f'C_DOC_{idx}'] = f'[E.C_DOC_{idx}]'
            contractors_data[f'C_OCUPACION_{idx}'] = f'[E.C_OCUPACION_{idx}]'
            contractors_data[f'C_ESTADO_CIVIL_{idx}'] = f'[E.C_ESTADO_CIVIL_{idx}]'
            contractors_data[f'C_DOMICILIO_{idx}'] = f'[E.C_DOMICILIO_{idx}]'
            contractors_data[f'C_IDE_{idx}'] = f'[E.C_IDE_{idx}]'
            contractors_data[f'SEXO_C_{idx}'] = f'[E.SEXO_C_{idx}]'
            contractors_data[f'C_FIRMAN_{idx}'] = f'[E.C_FIRMAN_{idx}]'
            contractors_data[f'C_IMPRIME_{idx}'] = f'[E.C_IMPRIME_{idx}]'

        for idx in range(len(transferor_companies) + len(acquirer_companies) + 1, 6):
            contractors_data[f'NOMBRE_EMPRESA_{idx}'] = f'[E.NOMBRE_EMPRESA_{idx}]'
            contractors_data[f'INS_EMPRESA_{idx}'] = f'[E.INS_EMPRESA_{idx}]'
            contractors_data[f'RUC_{idx}'] = f'[E.RUC_{idx}]'
            contractors_data[f'DOMICILIO_EMPRESA_{idx}'] = f'[E.DOMICILIO_EMPRESA_{idx}]'

        if transferors:
            contractors_data['P_NOM'] = contractors_data['P_NOM_1']
            contractors_data['P_NACIONALIDAD'] = contractors_data['P_NACIONALIDAD_1']
            contractors_data['P_TIP_DOC'] = contractors_data['P_TIP_DOC_1']
            contractors_data['P_DOC'] = contractors_data['P_DOC_1']
            contractors_data['P_OCUPACION'] = contractors_data['P_OCUPACION_1']
            contractors_data['P_ESTADO_CIVIL'] = contractors_data['P_ESTADO_CIVIL_1']
            contractors_data['P_DOMICILIO'] = contractors_data['P_DOMICILIO_1']
            contractors_data['P_IDE'] = contractors_data['P_IDE_1']
            contractors_data['SEXO_P'] = contractors_data['SEXO_P_1']
            contractors_data['P_FIRMAN'] = contractors_data['P_FIRMAN_1']
            contractors_data['P_IMPRIME'] = contractors_data['P_IMPRIME_1']

        if acquirers:
            contractors_data['C_NOM'] = contractors_data['C_NOM_1']
            contractors_data['C_NACIONALIDAD'] = contractors_data['C_NACIONALIDAD_1']
            contractors_data['C_TIP_DOC'] = contractors_data['C_TIP_DOC_1']
            contractors_data['C_DOC'] = contractors_data['C_DOC_1']
            contractors_data['C_OCUPACION'] = contractors_data['C_OCUPACION_1']
            contractors_data['C_ESTADO_CIVIL'] = contractors_data['C_ESTADO_CIVIL_1']
            contractors_data['C_DOMICILIO'] = contractors_data['C_DOMICILIO_1']
            contractors_data['C_IDE'] = contractors_data['C_IDE_1']
            contractors_data['SEXO_C'] = contractors_data['SEXO_C_1']
            contractors_data['C_FIRMAN'] = contractors_data['C_FIRMAN_1']
            contractors_data['C_IMPRIME'] = contractors_data['C_IMPRIME_1']

        contractors_data.update(self.get_articles_and_grammar(transferors, 'P'))
        contractors_data.update(self.get_articles_and_grammar(acquirers, 'C'))

        return contractors_data


    def get_identification_phrase(self, gender, doc_type, doc_number):
        if gender == 'F':
            return f'IDENTIFICADA CON {doc_type} N° {doc_number}, '
        else:
            return f'IDENTIFICADO CON {doc_type} N° {doc_number}, '

    def get_civil_status_by_gender(self, civil_status, gender):
        if not civil_status:
            return ''
        if gender == 'F':
            return civil_status[:-1] + 'A, '
        else:
            return civil_status + ', '

    def classify_contratantes(self, contratantes):
        TRANSFEROR_ROLES = {'VENDEDOR', 'DONANTE', 'APODERADO', 'CEDENTE', 'ARRENDADOR', 'MUTUANTE', 'ADJUDICANTE'}
        ACQUIRER_ROLES = {'COMPRADOR', 'DONATARIO', 'CESIONARIO', 'ARRENDATARIO', 'MUTUARIO', 'ADJUDICATARIO'}

        transferors = [c for c in contratantes if c['condiciones'] in TRANSFEROR_ROLES]
        acquirers = [c for c in contratantes if c['condiciones'] in ACQUIRER_ROLES]
        return transferors, acquirers

    def get_nationality_by_gender(self, nationality, gender):
        if not nationality:
            return ''
        base = nationality[:-1]  # Remove last character
        if gender == 'F':
            return base + 'A'
        else:
            return base + 'O'
    def get_articles_and_grammar(self, people, role_prefix):
        count = len(people)
        if count == 0:
            return {
                f'EL_{role_prefix}': '',
                f'{role_prefix}_CALIDAD': '',
                f'{role_prefix}_INICIO': '',
                f'{role_prefix}_AMBOS': '',
            }
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
            inicio = ' SEÑORA' if all_female else 'SEÑOR'
            el = 'LA' if all_female else 'EL'
        return {
            f'EL_{role_prefix}': el,
            f'{role_prefix}_CALIDAD': calidad,
            f'{role_prefix}_INICIO': inicio,
            f'{role_prefix}_AMBOS': ambos,
        }
    
    def _process_document(self, template_bytes: bytes, data: Dict[str, str]) -> Document:
        """
        Process the document template with data
        """
        buffer = io.BytesIO(template_bytes)
        doc = DocxTemplate(buffer)
        doc.render(data)
        return doc
    
    def _create_response(self, doc: Document, filename: str, kardex: str, mode: str = "download") -> HttpResponse:
        """
        Create HTTP response with the document
        """
        # Add the custom property
        custom_props = CustomProperties(doc)
        custom_props['documentoGeneradoId'] = kardex

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
                'kardex': kardex,
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
