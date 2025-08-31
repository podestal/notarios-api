"""
This module contains the SOAP client service for the sisgen service.
"""

import logging
import requests
import warnings
from urllib3.exceptions import InsecureRequestWarning
from typing import Dict
from datetime import datetime
from django.db import connection

# Suppress only the single warning from urllib3 needed.
warnings.simplefilter('ignore', InsecureRequestWarning)

logger = logging.getLogger(__name__)

def get_current_date():
    """Get current date in dd/mm/yyyy format"""
    now = datetime.now()
    return now.strftime("%d/%m/%Y")

def get_current_time():
    """Get current time in HH:MM:SS format"""
    now = datetime.now()
    return now.strftime("%H:%M:%S")

class SISGENSoapClient:
    def __init__(self, base_url: str, timeout: int = 500):
        """Initialize SISGEN SOAP client"""
        self.base_url = base_url
        self.timeout = timeout

    def send_documents(self, xml_content: str) -> Dict:
        """Send XML documents to SISGEN service"""
        try:
            # Wrap XML in SOAP envelope
            soap_envelope = f'''<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
    <SOAP-ENV:Body>
        <setDocumentosNotariales xmlns="http://cnlws.notarios.org.pe/">
            <arg0 xmlns=""><![CDATA[{xml_content}]]></arg0>
        </setDocumentosNotariales>
    </SOAP-ENV:Body>
</SOAP-ENV:Envelope>'''

            # Set up headers
            headers = {
                "Content-type": "text/xml;charset=\"utf-8\"",
                "Accept": "text/xml",
                "Accept-Encoding": "gzip",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
                "SOAPAction": '"http://cnlws.notarios.org.pe/DocumentosNotarialesSOAPService/setDocumentosNotariales"',
                "Content-length": str(len(soap_envelope)),
            }

            logger.debug(f"SOAP Request Headers: {headers}")
            logger.debug(f"SOAP Request Body: {soap_envelope}")

            # Make request with same options as PHP curl
            response = requests.post(
                self.base_url,
                data=soap_envelope,
                headers=headers,
                verify=False,
                timeout=self.timeout
            )

            logger.debug(f"SOAP Response Status: {response.status_code}")
            logger.debug(f"SOAP Response Headers: {dict(response.headers)}")
            logger.debug(f"SOAP Response Body: {response.text}")

            if response.status_code != 200:
                raise Exception(f"HTTP request failed: {response.status_code} {response.reason} for url: {self.base_url}")

            # Parse response like PHP
            xml2 = '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body><ns2:setDocumentosNotarialesResponse xmlns:ns2="http://cnlws.notarios.org.pe/" xmlns:ns3="http://sisgen.notarios.org.pe/SISGEN/XML">'
            xml3 = '</ns2:setDocumentosNotarialesResponse></soap:Body></soap:Envelope>'
            xml4 = '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body><ns2:setDocumentosNotarialesResponse xmlns:ns2="http://cnlws.notarios.org.pe/" xmlns:ns3="http://sisgen.notarios.org.pe/SISGEN/XML" xmlns:ns4="http://www.w3.org/2000/09/xmldsig#">'
            
            # Clean response like PHP
            clean_xml = response.text.replace('ns3:', '')
            clean_xml = clean_xml.replace(xml3, '')
            clean_xml = clean_xml.replace(xml2, '')
            clean_xml = clean_xml.replace(xml4, '')

            # Write response to file like PHP
            with open("response.xml", "w+") as f:
                f.write(clean_xml)

            # Extract status from response
            status_start = response.text.find('<status>') 
            status_end = response.text.find('</status>')
            status = response.text[status_start:status_end] if status_start >= 0 and status_end >= 0 else ''

            # Process response and update database
            if status == '<status>INTERNAL_SERVER_ERROR':
                return {
                    'success': False,
                    'error': 'Error interno del XML.',
                    'status': 'ERROR_SERVICE'
                }

            # Parse XML response
            from xml.etree import ElementTree
            try:
                root = ElementTree.fromstring(clean_xml)
                current_date = get_current_date()
                current_time = get_current_time()

                # Clear existing data
                with connection.cursor() as cursor:
                    cursor.execute("TRUNCATE TABLE sisgen_mensaje")
                    cursor.execute("TRUNCATE TABLE sisgen")

                # Process each DocumentoNotarial
                for doc_notarial in root.findall('.//DocumentoNotarial'):
                    status = doc_notarial.find('Status').text if doc_notarial.find('Status') is not None else ''
                    documento = doc_notarial.find('Documento')
                    if documento is not None:
                        num_kardex = documento.find('NumKardex').text if documento.find('NumKardex') is not None else ''
                        num_escritura = documento.find('NumDocumento').text if documento.find('NumDocumento') is not None else ''
                        tipo_instrumento = documento.find('TipoInstrumento').text if documento.find('TipoInstrumento') is not None else ''
                        fecha_instrumento = documento.find('FechaInstrumento').text if documento.find('FechaInstrumento') is not None else ''

                        # Insert into sisgen table
                        estado = '3' if status == 'FALLIDO' else '2' if status == 'CON OBSERVACIONES' else '1'
                        with connection.cursor() as cursor:
                            cursor.execute("""
                                INSERT INTO sisgen (tipo_kardex, kardex, num_escritura, fecha_instrumento, 
                                                  fech_envio, hora_envio, status, estado)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            """, [tipo_instrumento, num_kardex, num_escritura, fecha_instrumento,
                                 current_date, current_time, status, estado])

                            # Also insert into sisgen_report
                            cursor.execute("""
                                INSERT INTO sisgen_report (tipo_kardex, kardex, num_escritura, fecha_instrumento,
                                                         fech_envio, hora_envio, status, estado)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            """, [tipo_instrumento, num_kardex, num_escritura, fecha_instrumento,
                                 current_date, current_time, status, estado])

                            # Update kardex estado_sisgen
                            cursor.execute("UPDATE kardex SET estado_sisgen = %s WHERE kardex = %s",
                                         [estado, num_kardex])

                        # Process errors
                        for section in ['Documento', 'Maestros', 'Operaciones']:
                            errors = doc_notarial.findall(f'.//{section}/ERRORS/ERROR')
                            for error in errors:
                                mensaje = error.text
                                if mensaje:
                                    with connection.cursor() as cursor:
                                        cursor.execute("""
                                            INSERT INTO sisgen_mensaje (kardex, mensaje)
                                            VALUES (%s, %s)
                                        """, [num_kardex, mensaje])

                # Get response data
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT DISTINCT sisgen_mensaje.mensaje, tipo_kardex AS TIPKAR,
                               sisgen.kardex AS kardex, num_escritura AS NUM_ESC,
                               fech_envio AS FEC_ENVIO, hora_envio AS HORA_ENVIO,
                               estado AS estado, IF(mensaje IS NULL, '', mensaje) AS mensaje,
                               sisgen.status AS status, sisgen_temp.idkardex AS IDKARDEX,
                               sisgen_temp.contrato AS contrato
                        FROM sisgen
                        LEFT JOIN sisgen_mensaje ON sisgen.kardex = sisgen_mensaje.kardex
                        INNER JOIN sisgen_temp ON sisgen.kardex = sisgen_temp.kardex
                        ORDER BY sisgen.kardex ASC
                    """)
                    data_response = cursor.fetchall()

                    # Get counts
                    cursor.execute("""
                        SELECT COUNT(*) AS count FROM sisgen WHERE status = 'GUARDADO'
                        GROUP BY kardex
                    """)
                    guardados = cursor.fetchone()[0] if cursor.fetchone() else 0

                    cursor.execute("""
                        SELECT COUNT(*) AS count FROM sisgen WHERE status = 'FALLIDO'
                        GROUP BY kardex
                    """)
                    fallidos = cursor.fetchone()[0] if cursor.fetchone() else 0

                    cursor.execute("""
                        SELECT COUNT(*) AS count FROM sisgen WHERE status = 'CON OBSERVACIONES'
                        GROUP BY kardex
                    """)
                    observados = cursor.fetchone()[0] if cursor.fetchone() else 0

                return {
                    'success': True,
                    'data': data_response,
                    'guardados': guardados,
                    'fallidos': fallidos,
                    'observados': observados
                }

            except ElementTree.ParseError as e:
                logger.error(f"Error parsing XML response: {str(e)}")
                return {
                    'success': False,
                    'error': 'Error parsing XML response',
                    'status': 'ERROR_SERVICE'
                }

        except Exception as e:
            logger.error(f"Error sending documents to SISGEN: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'status': 'ERROR_SERVICE'
            }
