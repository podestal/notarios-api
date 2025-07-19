"""
This module contains the SOAP client service for the sisgen service.
"""

import requests
import logging
from typing import Dict, Optional
from xml.etree import ElementTree as ET
from ..utils.exceptions import SISGENServiceException

logger = logging.getLogger(__name__)

class SISGENSoapClient:
    def __init__(self, base_url: str, timeout: int = 500):
        self.base_url = base_url
        self.timeout = timeout
        self.logger = logger
    
    def send_documents(self, xml_content: str) -> Dict:
        """Send documents to SISGEN service"""
        try:
            # Create SOAP envelope
            soap_request = self._create_soap_envelope(xml_content)
            
            # Send request
            response = self._send_request(soap_request)
            
            # Parse response
            return self._parse_response(response)
            
        except SISGENServiceException as e:
            self.logger.error(f"SISGEN service error: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'status': 'ERROR'
            }
        except Exception as e:
            self.logger.error(f"Unexpected error sending documents: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'status': 'ERROR'
            }
    
    def _create_soap_envelope(self, xml_content: str) -> str:
        """Create SOAP envelope"""
        return f"""<SOAP-ENV:Envelope xmlns:SOAP-ENV='http://schemas.xmlsoap.org/soap/envelope/'>
    <SOAP-ENV:Body>
        <setDocumentosNotariales xmlns='http://ws.sisgen.ancert.notariado.org/'>
            <arg0 xmlns=''><![CDATA[{xml_content}]]></arg0>
        </setDocumentosNotariales>
    </SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
    
    def _send_request(self, soap_request: str) -> str:
        """Send SOAP request"""
        headers = {
            'Content-Type': 'text/xml;charset=utf-8',
            'Accept': 'text/xml',
            'Accept-Encoding': 'gzip',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'SOAPAction': 'http://ws.sisgen.ancert.notariado.org/DocumentosNotarialesSOAPService/setDocumentosNotariales',
            'Content-Length': str(len(soap_request))
        }
        
        try:
            response = requests.post(
                self.base_url,
                data=soap_request,
                headers=headers,
                timeout=self.timeout,
                verify=False  # Note: In production, use proper SSL verification
            )
            
            response.raise_for_status()
            return response.text
            
        except requests.exceptions.RequestException as e:
            raise SISGENServiceException(f"HTTP request failed: {str(e)}")
    
    def _parse_response(self, response_xml: str) -> Dict:
        """Parse SOAP response"""
        try:
            # Remove SOAP envelope
            clean_xml = self._extract_response_content(response_xml)
            
            # Parse XML
            root = ET.fromstring(clean_xml)
            
            # Extract status and messages
            status = root.find('.//status')
            message = root.find('.//message')
            
            return {
                'success': status.text == 'OK' if status is not None else False,
                'status': status.text if status is not None else 'UNKNOWN',
                'message': message.text if message is not None else '',
                'raw_response': response_xml
            }
            
        except Exception as e:
            self.logger.error(f"Error parsing response: {str(e)}")
            return {
                'success': False,
                'error': f"Parse error: {str(e)}",
                'status': 'PARSE_ERROR'
            }
    
    def _extract_response_content(self, response_xml: str) -> str:
        """Extract content from SOAP response"""
        start_marker = '<return>'
        end_marker = '</return>'
        
        start_pos = response_xml.find(start_marker)
        end_pos = response_xml.find(end_marker)
        
        if start_pos != -1 and end_pos != -1:
            return response_xml[start_pos + len(start_marker):end_pos]
        
        return response_xml