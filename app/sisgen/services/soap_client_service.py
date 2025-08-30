"""
This module contains the SOAP client service for the sisgen service.
"""

import requests
import logging
from requests.auth import HTTPBasicAuth
import warnings
from urllib3.exceptions import InsecureRequestWarning
import xml.etree.ElementTree as ET
from datetime import datetime
from ..utils.constants import SOAP_HEADERS, XML_NAMESPACES
from typing import Dict

# Suppress only the single warning from urllib3 needed.
warnings.simplefilter('ignore', InsecureRequestWarning)

logger = logging.getLogger(__name__)

class SISGENSoapClient:
    def __init__(self, base_url, timeout=500):
        self.base_url = base_url
        self.timeout = timeout
        
    def send_documents(self, xml_content: str) -> Dict:
        """Send XML documents to SISGEN service"""
        try:
            # Wrap XML in SOAP envelope
            soap_envelope = f'''<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ws="http://ws.sisgen.ancert.notariado.org/">
    <soapenv:Header/>
    <soapenv:Body>
        <ws:setDocumentosNotariales>
            <ws:arg0><![CDATA[{xml_content}]]></ws:arg0>
        </ws:setDocumentosNotariales>
    </soapenv:Body>
</soapenv:Envelope>'''

            # Set up headers
            headers = SOAP_HEADERS.copy()
            headers['Content-Length'] = str(len(soap_envelope))

            logger.debug(f"SOAP Request Headers: {headers}")
            logger.debug(f"SOAP Request Body: {soap_envelope}")

            # Make request
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
            xml2 = '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body><ns2:setDocumentosNotarialesResponse xmlns:ns2="http://ws.sisgen.ancert.notariado.org/" xmlns:ns3="http://ancert.notariado.org/SISGEN/XML">'
            xml3 = '</ns2:setDocumentosNotarialesResponse></soap:Body></soap:Envelope>'
            xml4 = '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body><ns2:setDocumentosNotarialesResponse xmlns:ns2="http://ws.sisgen.ancert.notariado.org/" xmlns:ns3="http://ancert.notariado.org/SISGEN/XML" xmlns:ns4="http://www.w3.org/2000/09/xmldsig#">'
            
            # Clean response like PHP
            clean_xml = response.text.replace('ns3:', '')
            clean_xml = clean_xml.replace(xml3, '')
            clean_xml = clean_xml.replace(xml2, '')
            clean_xml = clean_xml.replace(xml4, '')

            # Parse response
            return {
                'success': True,
                'response': clean_xml
            }

        except Exception as e:
            logger.error(f"Error sending documents to SISGEN: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'status': 'ERROR_SERVICE'
            }

    def generate_xml(self, data):
        """
        Generate XML for SISGEN from data
        """
        try:
            # Start XML document
            xml = '<?xml version="1.0" ?>\n'
            xml += '<DocumentosNotariales xmlns="http://ancert.notariado.org/SISGEN/XML" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://ancert.notariado.org/SISGEN/XML documentos_notariales.xsd">\n'
            
            # Add GeneradorDatos section
            xml += '\t<GeneradorDatos>\n'
            xml += '\t\t<NomProveedor>CNL</NomProveedor>\n'
            xml += '\t\t<NomAplicacion>SISNOT</NomAplicacion>\n'
            xml += '\t\t<VersionAplicacion>2.7</VersionAplicacion>\n'
            xml += '\t</GeneradorDatos>\n'

            # Process each document
            for doc in data.get('documents', []):
                xml += '\t<DocumentoNotarial>\n'
                
                # Add DatosNotario section
                notary_data = doc.get('notary_data', {})
                xml += '\t\t<DatosNotario>\n'
                xml += f'\t\t\t<CodNotario>{notary_data.get("codnotario", "")}</CodNotario>\n'
                xml += f'\t\t\t<CodOficial>{notary_data.get("codoficial", "")}</CodOficial>\n'
                xml += f'\t\t\t<NombreNotario>{notary_data.get("nombre_notario", "")}</NombreNotario>\n'
                xml += '\t\t\t<Ubicacion>\n'
                xml += f'\t\t\t\t<Direccion>{notary_data.get("direccion", "")}</Direccion>\n'
                xml += f'\t\t\t\t<Distrito>{notary_data.get("distrito", "")}</Distrito>\n'
                xml += '\t\t\t</Ubicacion>\n'
                xml += '\t\t</DatosNotario>\n'

                # Add Documento section
                xml += '\t\t<Documento>\n'
                xml += f'\t\t\t<NumKardex>{doc.get("kardex", "")}</NumKardex>\n'
                xml += f'\t\t\t<FechaIngreso>{doc.get("fechaingreso", "")}</FechaIngreso>\n'
                xml += f'\t\t\t<TipoInstrumento>{doc.get("idtipkar", "")}</TipoInstrumento>\n'
                xml += f'\t\t\t<NumDocumento>{doc.get("numescritura", "")}</NumDocumento>\n'
                xml += f'\t\t\t<FechaInstrumento>{doc.get("fechaescritura", "")}</FechaInstrumento>\n'
                xml += f'\t\t\t<NumFolios>{int(doc.get("foliofin", 0)) - int(doc.get("folioini", 0)) + 1}</NumFolios>\n'
                if doc.get("fechaconclusion"):
                    xml += f'\t\t\t<FechaConclusion>{doc.get("fechaconclusion", "")}</FechaConclusion>\n'
                xml += '\t\t</Documento>\n'

                # Add Maestros section
                xml += '\t\t<Maestros>\n'
                
                # Process participants
                natural_persons = []
                juridical_persons = []
                for participant in doc.get('participants', []):
                    if participant.get('tipper') == 'J':
                        juridical_persons.append(participant)
                    elif participant.get('tipper') == 'N':
                        natural_persons.append(participant)

                if natural_persons:
                    xml += '\t\t\t<PersonasNaturales>\n'
                    for person in natural_persons:
                        xml += f'\t\t\t\t<PersonaNatural id="{person.get("id", "")}">\n'
                        xml += '\t\t\t\t<DocsIdentificativos>\n'
                        xml += '\t\t\t\t\t<DocIdentificativo>\n'
                        xml += f'\t\t\t\t\t\t<TipoDocIdentidad>{person.get("idtipdoc", "")}</TipoDocIdentidad>\n'
                        if person.get("numdoc"):
                            xml += f'\t\t\t\t\t\t<NumDocIdentificativo>{person.get("numdoc", "")}</NumDocIdentificativo>\n'
                        xml += '\t\t\t\t\t</DocIdentificativo>\n'
                        xml += '\t\t\t\t</DocsIdentificativos>\n'
                        
                        if person.get("prinom"):
                            xml += f'\t\t\t\t<Nombre>{person.get("prinom", "")}</Nombre>\n'
                        if person.get("apepat"):
                            xml += f'\t\t\t\t<PrimerApellido>{person.get("apepat", "")}</PrimerApellido>\n'
                        if person.get("apemat"):
                            xml += f'\t\t\t\t<SegundoApellido>{person.get("apemat", "")}</SegundoApellido>\n'
                        if person.get("sexo"):
                            xml += f'\t\t\t\t<Genero>{"V" if person.get("sexo") == "M" else "M"}</Genero>\n'
                        if person.get("idestcivil"):
                            xml += f'\t\t\t\t<EstadoCivil>{person.get("idestcivil", "")}</EstadoCivil>\n'
                        if person.get("nacionalidad"):
                            xml += f'\t\t\t\t<PaisNacionalidad>{person.get("nacionalidad", "")}</PaisNacionalidad>\n'
                        if person.get("cumpclie"):
                            xml += f'\t\t\t\t<FechaNacimiento>{person.get("cumpclie", "")}</FechaNacimiento>\n'
                        if person.get("profesion_plantilla"):
                            xml += f'\t\t\t\t<Profesion>{person.get("profesion_plantilla", "")}</Profesion>\n'
                        if person.get("profocupa"):
                            xml += f'\t\t\t\t<Ocupacion>{person.get("profocupa", "")}</Ocupacion>\n'
                        if person.get("email") and '@' in person.get("email", ""):
                            xml += f'\t\t\t\t<Correo>{person.get("email", "")}</Correo>\n'
                        if person.get("telcel"):
                            xml += f'\t\t\t\t<Telefono>{person.get("telcel", "")}</Telefono>\n'
                        
                        # Add address if all required fields are present
                        if all([person.get(f) for f in ["idubigeo"]]) and person.get("direccion"):
                            xml += '\t\t\t\t<Direccion>\n'
                            if person.get("residente"):
                                xml += f'\t\t\t\t\t<ResidePeru>{person.get("residente", "")}</ResidePeru>\n'
                            if person.get("nacionalidad"):
                                xml += f'\t\t\t\t\t<PaisResidencia>{person.get("nacionalidad", "")}</PaisResidencia>\n'
                            xml += '\t\t\t\t<DireccionNacional>\n'
                            ubigeo = person.get("idubigeo", "")
                            if len(ubigeo) == 6:
                                xml += f'\t\t\t\t\t<CodDepartamento>{ubigeo[:2]}</CodDepartamento>\n'
                                xml += f'\t\t\t\t\t<CodProvincia>{ubigeo[2:4]}</CodProvincia>\n'
                                xml += f'\t\t\t\t\t<CodDistrito>{ubigeo[4:]}</CodDistrito>\n'
                            xml += f'\t\t\t\t\t<RestoDireccion>{person.get("direccion", "")}</RestoDireccion>\n'
                            xml += '\t\t\t\t</DireccionNacional>\n'
                            xml += '\t\t\t\t</Direccion>\n'
                        xml += '\t\t\t\t</PersonaNatural>\n'
                    xml += '\t\t\t</PersonasNaturales>\n'

                if juridical_persons:
                    xml += '\t\t\t<PersonasJuridicas>\n'
                    for person in juridical_persons:
                        xml += f'\t\t\t\t<PersonaJuridica id="{person.get("id", "")}">\n'
                        xml += '\t\t\t\t<DocsIdentificativos>\n'
                        xml += '\t\t\t\t\t<DocIdentificativo>\n'
                        xml += f'\t\t\t\t\t\t<TipoDocIdentidad>{person.get("idtipdoc", "")}</TipoDocIdentidad>\n'
                        if person.get("numdoc"):
                            xml += f'\t\t\t\t\t\t<NumDocIdentificativo>{person.get("numdoc", "")}</NumDocIdentificativo>\n'
                        xml += '\t\t\t\t\t</DocIdentificativo>\n'
                        xml += '\t\t\t\t</DocsIdentificativos>\n'
                        
                        if person.get("idsedereg") or person.get("numpartida"):
                            xml += '\t\t\t\t<RegistroFacultades>\n'
                            if person.get("idsedereg"):
                                xml += f'\t\t\t\t\t<SedeRegistral>{person.get("idsedereg", "")}</SedeRegistral>\n'
                            if person.get("numpartida"):
                                xml += f'\t\t\t\t\t<PartidaRegistral>{person.get("numpartida", "")}</PartidaRegistral>\n'
                            xml += '\t\t\t\t</RegistroFacultades>\n'
                        
                        if person.get("razonsocial"):
                            xml += f'\t\t\t\t<RazonSocial>{person.get("razonsocial", "")}</RazonSocial>\n'
                        if person.get("contacempresa"):
                            xml += f'\t\t\t\t<OtraActividad>{person.get("contacempresa", "")}</OtraActividad>\n'
                        if person.get("mailempresa") and '@' in person.get("mailempresa", ""):
                            xml += f'\t\t\t\t<Correo>{person.get("mailempresa", "")}</Correo>\n'
                        if person.get("telempresa"):
                            xml += f'\t\t\t\t<Telefono>{person.get("telempresa", "")}</Telefono>\n'

                        # Add address if all required fields are present
                        if person.get("idubigeo") != "999999" and person.get("domfiscal"):
                            xml += '\t\t\t\t<Direccion>\n'
                            xml += '\t\t\t\t\t<PaisResidencia>PE</PaisResidencia>\n'
                            xml += '\t\t\t\t<DireccionNacional>\n'
                            ubigeo = person.get("idubigeo", "")
                            if len(ubigeo) == 6:
                                xml += f'\t\t\t\t\t<CodDepartamento>{ubigeo[:2]}</CodDepartamento>\n'
                                xml += f'\t\t\t\t\t<CodProvincia>{ubigeo[2:4]}</CodProvincia>\n'
                                xml += f'\t\t\t\t\t<CodDistrito>{ubigeo[4:]}</CodDistrito>\n'
                            xml += f'\t\t\t\t\t<RestoDireccion>{person.get("domfiscal", "")}</RestoDireccion>\n'
                            xml += '\t\t\t\t</DireccionNacional>\n'
                            xml += '\t\t\t\t</Direccion>\n'
                        xml += '\t\t\t\t</PersonaJuridica>\n'
                    xml += '\t\t\t</PersonasJuridicas>\n'

                xml += '\t\t</Maestros>\n'

                # Add Operaciones section
                xml += '\t\t<Operaciones>\n'
                xml += '\t\t\t<Operacion>\n'
                xml += f'\t\t\t\t<CodActoJuridico>{doc.get("cod_ancert", "")}</CodActoJuridico>\n'
                xml += '\t\t\t\t<Operantes>\n'
                xml += '\t\t\t\t\t<Objetos>\n'
                xml += '\t\t\t\t\t</Objetos>\n'
                xml += '\t\t\t\t\t<Intervenciones>\n'
                
                # Group participants by role
                otorgantes = [p for p in doc.get('participants', []) if p.get('uif') == 'O']
                beneficiarios = [p for p in doc.get('participants', []) if p.get('uif') == 'B']
                
                # Create a map of participants by idcontratante for easy lookup
                participant_map = {p.get('idcontratante'): p for p in doc.get('participants', [])}
                
                if otorgantes:
                    xml += '\t\t\t\t\t\t<Intervencion>\n'
                    xml += '\t\t\t\t\t\t\t<TipoIntervencion>1</TipoIntervencion>\n'
                    xml += '\t\t\t\t\t\t\t<DescripcionIntervencion>OTORGANTE</DescripcionIntervencion>\n'
                    xml += '\t\t\t\t\t\t\t<RolRepresentante>O</RolRepresentante>\n'
                    xml += '\t\t\t\t\t\t\t<Sujetos>\n'
                    for otorgante in otorgantes:
                        xml += '\t\t\t\t\t\t\t\t<Sujeto>\n'
                        xml += f'\t\t\t\t\t\t\t\t\t<IdMaestro>{otorgante.get("idcliente", "")}</IdMaestro>\n'
                        xml += '\t\t\t\t\t\t\t\t\t<Derecho>\n'
                        if otorgante.get("porcentaje"):
                            xml += f'\t\t\t\t\t\t\t\t\t\t<PorcentajeDerecho>{otorgante.get("porcentaje", "")}</PorcentajeDerecho>\n'
                        xml += '\t\t\t\t\t\t\t\t\t</Derecho>\n'
                        
                        # Find representatives for this otorgante
                        reps = [p for p in doc.get('participants', []) if p.get('tiporepresentacion') == '1' and p.get('idcontratanterp') == otorgante.get('idcontratante')]
                        if reps:
                            xml += '\t\t\t\t\t\t\t\t\t<Representantes>\n'
                            for rep in reps:
                                xml += '\t\t\t\t\t\t\t\t\t\t<Representante>\n'
                                xml += f'\t\t\t\t\t\t\t\t\t\t\t<IdMaestro>{rep.get("idcliente", "")}</IdMaestro>\n'
                                if rep.get("inscrito") == "1" and (rep.get("idsedereg") or rep.get("numpartida")):
                                    xml += '\t\t\t\t\t\t\t\t\t\t\t<InscripcionRepresentacion>\n'
                                    if rep.get("idsedereg"):
                                        xml += f'\t\t\t\t\t\t\t\t\t\t\t\t<SedeRegistral>{rep.get("idsedereg", "")}</SedeRegistral>\n'
                                    if rep.get("numpartida"):
                                        xml += f'\t\t\t\t\t\t\t\t\t\t\t\t<PartidaRegistral>{rep.get("numpartida", "")}</PartidaRegistral>\n'
                                    xml += '\t\t\t\t\t\t\t\t\t\t\t</InscripcionRepresentacion>\n'
                                if rep.get("facultades"):
                                    xml += f'\t\t\t\t\t\t\t\t\t\t\t<Facultades>{rep.get("facultades", "")}</Facultades>\n'
                                if rep.get("fechafirma"):
                                    xml += f'\t\t\t\t\t\t\t\t\t\t\t<FechaFirma>{rep.get("fechafirma", "")}</FechaFirma>\n'
                                xml += '\t\t\t\t\t\t\t\t\t\t</Representante>\n'
                            xml += '\t\t\t\t\t\t\t\t\t</Representantes>\n'
                        
                        if otorgante.get("fechafirma"):
                            xml += f'\t\t\t\t\t\t\t\t\t<FechaFirma>{otorgante.get("fechafirma", "")}</FechaFirma>\n'
                        xml += '\t\t\t\t\t\t\t\t</Sujeto>\n'
                    xml += '\t\t\t\t\t\t\t</Sujetos>\n'
                    xml += '\t\t\t\t\t\t</Intervencion>\n'

                if beneficiarios:
                    xml += '\t\t\t\t\t\t<Intervencion>\n'
                    xml += '\t\t\t\t\t\t\t<TipoIntervencion>2</TipoIntervencion>\n'
                    xml += '\t\t\t\t\t\t\t<DescripcionIntervencion>BENEFICIARIO</DescripcionIntervencion>\n'
                    xml += '\t\t\t\t\t\t\t<RolRepresentante>B</RolRepresentante>\n'
                    xml += '\t\t\t\t\t\t\t<Sujetos>\n'
                    for beneficiario in beneficiarios:
                        xml += '\t\t\t\t\t\t\t\t<Sujeto>\n'
                        xml += f'\t\t\t\t\t\t\t\t\t<IdMaestro>{beneficiario.get("idcliente", "")}</IdMaestro>\n'
                        xml += '\t\t\t\t\t\t\t\t\t<Derecho>\n'
                        if beneficiario.get("porcentaje"):
                            xml += f'\t\t\t\t\t\t\t\t\t\t<PorcentajeDerecho>{beneficiario.get("porcentaje", "")}</PorcentajeDerecho>\n'
                        xml += '\t\t\t\t\t\t\t\t\t</Derecho>\n'
                        
                        # Find representatives for this beneficiario
                        reps = [p for p in doc.get('participants', []) if p.get('tiporepresentacion') == '1' and p.get('idcontratanterp') == beneficiario.get('idcontratante')]
                        if reps:
                            xml += '\t\t\t\t\t\t\t\t\t<Representantes>\n'
                            for rep in reps:
                                xml += '\t\t\t\t\t\t\t\t\t\t<Representante>\n'
                                xml += f'\t\t\t\t\t\t\t\t\t\t\t<IdMaestro>{rep.get("idcliente", "")}</IdMaestro>\n'
                                if rep.get("inscrito") == "1" and (rep.get("idsedereg") or rep.get("numpartida")):
                                    xml += '\t\t\t\t\t\t\t\t\t\t\t<InscripcionRepresentacion>\n'
                                    if rep.get("idsedereg"):
                                        xml += f'\t\t\t\t\t\t\t\t\t\t\t\t<SedeRegistral>{rep.get("idsedereg", "")}</SedeRegistral>\n'
                                    if rep.get("numpartida"):
                                        xml += f'\t\t\t\t\t\t\t\t\t\t\t\t<PartidaRegistral>{rep.get("numpartida", "")}</PartidaRegistral>\n'
                                    xml += '\t\t\t\t\t\t\t\t\t\t\t</InscripcionRepresentacion>\n'
                                if rep.get("facultades"):
                                    xml += f'\t\t\t\t\t\t\t\t\t\t\t<Facultades>{rep.get("facultades", "")}</Facultades>\n'
                                if rep.get("fechafirma"):
                                    xml += f'\t\t\t\t\t\t\t\t\t\t\t<FechaFirma>{rep.get("fechafirma", "")}</FechaFirma>\n'
                                xml += '\t\t\t\t\t\t\t\t\t\t</Representante>\n'
                            xml += '\t\t\t\t\t\t\t\t\t</Representantes>\n'
                        
                        if beneficiario.get("fechafirma"):
                            xml += f'\t\t\t\t\t\t\t\t\t<FechaFirma>{beneficiario.get("fechafirma", "")}</FechaFirma>\n'
                        xml += '\t\t\t\t\t\t\t\t</Sujeto>\n'
                    xml += '\t\t\t\t\t\t\t</Sujetos>\n'
                    xml += '\t\t\t\t\t\t</Intervencion>\n'

                xml += '\t\t\t\t\t</Intervenciones>\n'
                xml += '\t\t\t\t</Operantes>\n'
                xml += '\t\t\t</Operacion>\n'
                xml += '\t\t</Operaciones>\n'
                xml += '\t</DocumentoNotarial>\n'

            xml += '</DocumentosNotariales>'
            
            logger.debug("Generated XML content")
            return xml

        except Exception as e:
            logger.error(f"Error generating XML: {str(e)}")
            raise