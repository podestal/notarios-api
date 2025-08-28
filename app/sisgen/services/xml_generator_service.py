"""
This module contains the XML generator service for the sisgen service.
"""

from typing import Dict, List, Optional
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
    
    def generate_document_xml(self, documents: List[Dict]) -> Optional[str]:
        """
        Generate XML for SISGEN service.
        Returns None if required data is missing.
        """
        try:
            # Validate documents have required data
            if not documents:
                self.logger.error("No documents provided")
                return None
            
            # Create root element
            root = ET.Element('DocumentosNotariales')
            root.set('xmlns', self.namespace)
            root.set('xmlns:xsi', XML_NAMESPACES['XSI'])
            root.set('xsi:schemaLocation', self.schema_location)
            
            # Add generator data
            self._add_generator_data(root)
            
            # Add documents
            valid_docs = 0
            for doc in documents:
                if self._validate_document(doc):
                    self._add_document(root, doc)
                    valid_docs += 1
            
            if valid_docs == 0:
                self.logger.error("No valid documents to process")
                return None
            
            # Convert to string
            xml_str = ET.tostring(root, encoding='unicode')
            return self._pretty_xml(xml_str)
            
        except Exception as e:
            self.logger.error(f"Error generating XML: {str(e)}")
            return None
    
    def _validate_document(self, doc: Dict) -> bool:
        """Validate document has all required data"""
        # Validate basic document data
        required_fields = ['kardex', 'numescritura', 'idtipkar', 'fechaescritura']
        if not all(doc.get(field) for field in required_fields):
            self.logger.warning(f"Document missing required fields: {doc.get('kardex', 'Unknown')}")
            return False
            
        # Validate notary data
        notary_data = doc.get('notary_data', {})
        required_notary_fields = [
            'codnotario', 'codoficial', 'coduif', 
            'nombre_notario', 'direccion', 'distrito'
        ]
        if not all(notary_data.get(field) for field in required_notary_fields):
            self.logger.warning(f"Document missing required notary data: {doc.get('kardex', 'Unknown')}")
            return False
            
        return True
    
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
        """Add a single document with complete notary data"""
        doc_notarial = ET.SubElement(root, 'DocumentoNotarial')
        
        # Add notary data
        datos_notario = ET.SubElement(doc_notarial, 'DatosNotario')
        notary_data = doc['notary_data']
        
        cod_notario = ET.SubElement(datos_notario, 'CodNotario')
        cod_notario.text = str(notary_data['codnotario'])
        
        cod_oficial = ET.SubElement(datos_notario, 'CodOficial')
        cod_oficial.text = str(notary_data['codoficial'])
        
        nombre = ET.SubElement(datos_notario, 'NombreNotario')
        nombre.text = notary_data['nombre_notario']
        
        ubicacion = ET.SubElement(datos_notario, 'Ubicacion')
        direccion = ET.SubElement(ubicacion, 'Direccion')
        direccion.text = notary_data['direccion']
        distrito = ET.SubElement(ubicacion, 'Distrito')
        distrito.text = notary_data['distrito']
        
        if notary_data.get('provincia'):
            provincia = ET.SubElement(ubicacion, 'Provincia')
            provincia.text = notary_data['provincia']
        
        if notary_data.get('departamento'):
            departamento = ET.SubElement(ubicacion, 'Departamento')
            departamento.text = notary_data['departamento']
        
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