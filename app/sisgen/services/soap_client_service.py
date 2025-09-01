"""
This module contains the SOAP client service for the sisgen service.
"""

import requests
import logging
from ..utils.constants import SISGEN_URLS

logger = logging.getLogger(__name__)

class SoapClientService:
    def send_documents(self, xml_content: str) -> requests.Response:
        """
        Send documents to SISGEN service
        """
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

            # Send request to SISGEN
            response = requests.post(
                SISGEN_URLS['DOCUMENTS'],
                data=soap_envelope,
                headers=headers,
                verify=False
            )

            logger.debug(f"SOAP Response Status: {response.status_code}")
            logger.debug(f"SOAP Response Headers: {dict(response.headers)}")
            logger.debug(f"SOAP Response Body: {response.text}")

            return response

        except Exception as e:
            logger.error(f"Error sending documents to SISGEN: {str(e)}")
            raise
