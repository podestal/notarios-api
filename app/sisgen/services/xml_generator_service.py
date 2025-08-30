"""
This module contains the XML generator service for the sisgen service.
"""

import logging
from typing import Dict, List, Optional
from ..utils.constants import APP_CONSTANTS

logger = logging.getLogger(__name__)

class SISGENXmlGenerator:
    def __init__(self):
        self.logger = logger
    
    def _clean_folio(self, folio: str) -> str:
        """Clean folio number by removing non-numeric characters"""
        if not folio:
            return "0"
        return ''.join(c for c in folio if c.isdigit()) or "0"

    def _calculate_num_folios(self, doc: Dict) -> int:
        """Calculate number of folios handling non-numeric characters"""
        try:
            folio_ini = self._clean_folio(doc.get("folioini", "0"))
            folio_fin = self._clean_folio(doc.get("foliofin", "0"))
            
            num_folios = int(folio_fin) - int(folio_ini)
            return max(1, num_folios + 1)  # Ensure at least 1 folio
        except:
            return 1

    def _add_participant_condition(self, participant: Dict) -> str:
        """Add participant condition"""
        condition = ""
        if participant.get("idcondicion"):
            condition = f'{participant.get("idcondicion")}'
            if participant.get("item"):
                condition += f'.{participant.get("item")}/'
        return condition

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
            
            # Start XML document
            xml = '<?xml version="1.0" ?>\n'
            xml += '<DocumentosNotariales xmlns="http://ancert.notariado.org/SISGEN/XML" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://ancert.notariado.org/SISGEN/XML C:\\SISGEN\\SISGEN_V2_RO\\documentos_notariales.xsd">\n'
            
            # Add GeneradorDatos section
            xml += '\t<GeneradorDatos>\n'
            xml += f'\t\t<NomProveedor>{APP_CONSTANTS["PROVIDER_NAME"]}</NomProveedor>\n'
            xml += f'\t\t<NomAplicacion>{APP_CONSTANTS["APP_NAME"]}</NomAplicacion>\n'
            xml += f'\t\t<VersionAplicacion>{APP_CONSTANTS["APP_VERSION"]}</VersionAplicacion>\n'
            xml += '\t</GeneradorDatos>\n'

            # Process each document
            for doc in documents:
                if not self._validate_document(doc):
                    continue
                
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
                xml += f'\t\t\t<NumFolios>{self._calculate_num_folios(doc)}</NumFolios>\n'
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
                        
                        # Add condition
                        condition = self._add_participant_condition(otorgante)
                        if condition:
                            xml += f'\t\t\t\t\t\t\t\t\t<Condicion>{condition}</Condicion>\n'
                        
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
                        
                        # Add condition
                        condition = self._add_participant_condition(beneficiario)
                        if condition:
                            xml += f'\t\t\t\t\t\t\t\t\t<Condicion>{condition}</Condicion>\n'
                        
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
            
            # Write XML to file like PHP
            with open('textparaenviar-uno.xml', 'w') as f:
                f.write(xml)
            
            logger.debug("Generated XML content")
            return xml

        except Exception as e:
            logger.error(f"Error generating XML: {str(e)}")
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