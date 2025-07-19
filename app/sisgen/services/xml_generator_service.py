"""
This module contains the XML generator service for the sisgen service.
"""

from typing import Dict, List
import xml.etree.ElementTree as ET
from xml.dom import minidom
import logging
from ..utils.constants import XML_NAMESPACES, APP_CONSTANTS

logger = logging.getLogger(__name__)

class SISGENXmlGenerator:
    def __init__(self):
        self.namespace = XML_NAMESPACES['SISGEN']
        self.schema_location = f"{XML_NAMESPACES['SISGEN']} documentos_notariales.xsd"
        self.logger = logger
    
    def generate_document_xml(self, documents: List[Dict]) -> str:
        """Generate XML for SISGEN service"""
        try:
            # Create root element
            root = ET.Element('DocumentosNotariales')
            root.set('xmlns', self.namespace)
            root.set('xmlns:xsi', XML_NAMESPACES['XSI'])
            root.set('xsi:schemaLocation', self.schema_location)
            
            # Add generator data
            self._add_generator_data(root)
            
            # Add documents
            for doc in documents:
                self._add_document(root, doc)
            
            # Convert to string
            xml_str = ET.tostring(root, encoding='unicode')
            return self._pretty_xml(xml_str)
            
        except Exception as e:
            self.logger.error(f"Error generating XML: {str(e)}")
            raise
    
    def _add_generator_data(self, root: ET.Element):
        """Add generator information"""
        generador = ET.SubElement(root, 'GeneradorDatos')
        
        nom_proveedor = ET.SubElement(generador, 'NomProveedor')
        nom_proveedor.text = APP_CONSTANTS['PROVIDER_NAME']
        
        nom_aplicacion = ET.SubElement(generador, 'NomAplicacion')
        nom_aplicacion.text = APP_CONSTANTS['APP_NAME']
        
        version = ET.SubElement(generador, 'VersionAplicacion')
        version.text = APP_CONSTANTS['APP_VERSION']
    
    def _add_document(self, root: ET.Element, doc: Dict):
        """Add a single document"""
        doc_notarial = ET.SubElement(root, 'DocumentoNotarial')
        
        # Document info
        documento = ET.SubElement(doc_notarial, 'Documento')
        
        num_kardex = ET.SubElement(documento, 'NumKardex')
        num_kardex.text = str(doc['kardex'])
        
        num_documento = ET.SubElement(documento, 'NumDocumento')
        num_documento.text = str(doc['numescritura'])
        
        tipo_instrumento = ET.SubElement(documento, 'TipoInstrumento')
        tipo_instrumento.text = self._get_tipo_kardex_sisgen(doc['idtipkar'])
        
        fecha_instrumento = ET.SubElement(documento, 'FechaInstrumento')
        fecha_instrumento.text = doc['fechaescritura']
        
        # Add masters (people) - this would be populated from related data
        maestros = ET.SubElement(doc_notarial, 'Maestros')
        # Implementation depends on your people data structure
    
    def _get_tipo_kardex_sisgen(self, idtipkar: int) -> str:
        """Convert idtipkar to SISGEN format"""
        from ..utils.constants import TIPO_KARDEX_SISGEN_MAPPING
        return TIPO_KARDEX_SISGEN_MAPPING.get(idtipkar, 'E')
    
    def _pretty_xml(self, xml_str: str) -> str:
        """Format XML with proper indentation"""
        dom = minidom.parseString(xml_str)
        return dom.toprettyxml(indent='\t')