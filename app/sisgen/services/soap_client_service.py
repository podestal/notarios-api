"""
This module contains the SOAP client service for the sisgen service.
"""

from typing import Dict, Optional

import requests
import logging
from ..utils.constants import SISGEN_URLS

logger = logging.getLogger(__name__)

class SoapClientService:
    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self._session = session or requests.Session()
        self._owns_session = session is None

    def close(self) -> None:
        if self._owns_session:
            self._session.close()

    def build_request(self, xml_content: str) -> Dict[str, object]:
        """
        Build the HTTP POST body and headers that would be sent to SISGEN
        (SOAP envelope wrapping DocumentosNotariales XML).
        """
        soap_envelope = f'''<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
    <SOAP-ENV:Body>
        <setDocumentosNotariales xmlns="http://cnlws.notarios.org.pe/">
            <arg0 xmlns=""><![CDATA[{xml_content}]]></arg0>
        </setDocumentosNotariales>
    </SOAP-ENV:Body>
</SOAP-ENV:Envelope>'''

        headers = {
            "Content-type": "text/xml;charset=\"utf-8\"",
            "Accept": "text/xml",
            "Accept-Encoding": "gzip",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "SOAPAction": '"http://cnlws.notarios.org.pe/DocumentosNotarialesSOAPService/setDocumentosNotariales"',
            "Content-length": str(len(soap_envelope.encode("utf-8"))),
        }

        return {
            "url": SISGEN_URLS["DOCUMENTS"],
            "soap_body": soap_envelope,
            "headers": headers,
        }

    def send_documents(self, xml_content: str) -> requests.Response:
        """
        Send documents to SISGEN service
        """
        try:
            req = self.build_request(xml_content)
            soap_envelope = req["soap_body"]
            headers = req["headers"]

            logger.debug(f"SOAP Request Headers: {headers}")
            logger.debug(f"SOAP Request Body: {soap_envelope}")

            response = self._session.post(
                req["url"],
                data=soap_envelope,
                headers=headers,
                verify=False,
            )

            logger.debug(f"SOAP Response Status: {response.status_code}")
            logger.debug(f"SOAP Response Headers: {dict(response.headers)}")
            logger.debug(f"SOAP Response Body: {response.text}")

            return response

        except Exception as e:
            logger.error(f"Error sending documents to SISGEN: {str(e)}")
            raise
