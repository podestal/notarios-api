"""
This module contains the XML generator service for the sisgen service.
"""

import logging
from typing import Dict, List, Optional, Tuple
from ..utils.constants import APP_CONSTANTS
from datetime import datetime
from django.db import connection

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

    def _safe_float(self, value: str, default: float = 0.0) -> float:
        """Safely convert string to float, returning default if conversion fails"""
        try:
            if not value or value.strip() == '':
                return default
            return float(value)
        except (ValueError, TypeError):
            return default

    def _format_date(self, date_str: str) -> str:
        """Format date to YYYY-MM-DD format"""
        if not date_str:
            return ""
        try:
            # Try parsing with different formats
            for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y']:
                try:
                    date_obj = datetime.strptime(date_str, fmt)
                    return date_obj.strftime('%Y-%m-%d')  # Always return in YYYY-MM-DD format
                except ValueError:
                    continue
            return date_str
        except Exception:
            return date_str

    def _get_notary_codes(self, notary_data: Dict) -> Tuple[str, str]:
        """Get notary codes from confinotario table"""
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT codnotario, ruc 
                    FROM confinotario 
                    LIMIT 1
                """)
                result = cursor.fetchone()
                if result:
                    cod_notario = str(result[0]).strip()
                    cod_notaria = str(result[1]).strip()
                    return cod_notario, cod_notaria
                
                return "00000000", "00000000000"  # Default values
        except Exception as e:
            self.logger.error(f"Error getting notary codes: {str(e)}")
            return "00000000", "00000000000"

    def _get_tipo_intervencion_desc(self, role: str, acto_juridico: str = None, participant_data: Dict = None) -> Tuple[str, str]:
        """Get intervention type and description from database"""
        try:
            # Get tipo_intervencion based on role
            tipo_int = '1' if role == 'O' else '2' if role == 'B' else '3'
            
            # For acto_juridico 0909 (ACLARACION), use specific mappings
            if acto_juridico == '0909':
                with connection.cursor() as cursor:
                    # Get the specific type of aclaracion from tiposdeacto
                    cursor.execute("""
                        SELECT idtipoacto, desacto 
                        FROM tiposdeacto 
                        WHERE cod_ancert = %s
                    """, [acto_juridico])
                    result = cursor.fetchone()
                    
                    if result:
                        idtipoacto = result[0]
                        # For ACLARACION DE DONACION (idtipoacto 991)
                        if idtipoacto == '991':
                            if role == 'O':
                                return tipo_int, '084'  # Otorgante in ACLARACION DE DONACION
                            elif role == 'B':
                                return tipo_int, '011'  # Beneficiario in ACLARACION DE DONACION
                        # For ACLARACION Y MODIFICACION PARCIAL DE CONSTITUCION E.I.R.L. (idtipoacto 934)
                        elif idtipoacto == '934':
                            if role == 'O':
                                return tipo_int, '005'  # Otorgante
                            elif role == 'R':
                                return tipo_int, '006'  # Representante
                        # For other types of ACLARACION
                        else:
                            if role == 'O':
                                return tipo_int, '084'  # Default for Otorgante in ACLARACION
                            elif role == 'B':
                                return tipo_int, '011'  # Default for Beneficiario in ACLARACION
                            elif role == 'R':
                                return tipo_int, '006'  # Default for Representante in ACLARACION
            
            # Default mappings for other acto_juridico types
            if role == 'O':
                return tipo_int, '001'
            elif role == 'B':
                return tipo_int, '017'
            elif role == 'R':
                return tipo_int, '003'
            
            return tipo_int, '001'  # default
        except Exception as e:
            self.logger.error(f"Error getting intervention description: {str(e)}")
            return '1', '001'  # default

    def _get_valid_profession_code(self, code: str) -> str:
        """Get valid SISGEN profession code from database"""
        if not code:
            return "001"  # Default code
        
        try:
            with connection.cursor() as cursor:
                # Try to find the matching profession code
                cursor.execute("""
                    SELECT codprof 
                    FROM profesiones 
                    WHERE idprofesion = %s
                """, [code])
                result = cursor.fetchone()
                if result and result[0]:
                    return str(result[0]).zfill(3)
        except Exception as e:
            self.logger.error(f"Error getting profession code: {str(e)}")
        
        return "001"  # Default if not found or error

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
            xml += '<DocumentosNotariales xmlns="http://sisgen.notarios.org.pe/SISGEN/XML" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://sisgen.notarios.org.pe/SISGEN/XML C:\\SISGEN\\SISGEN_V2_RO\\documentos_notariales.xsd">\n'
            
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
                
                # Add Documento section
                xml += '\t<Documento>\n'
                notary_data = doc.get('notary_data', {})
                # Format notary codes correctly
                cod_notario, cod_notaria = self._get_notary_codes(notary_data)
                xml += f'\t\t<CodNotario>{cod_notario}</CodNotario>\n'
                xml += f'\t\t<CodNotaria>{cod_notaria}</CodNotaria>\n'
                xml += f'\t\t<NumKardex>{doc.get("kardex", "")}</NumKardex>\n'
                xml += f'\t\t<FechaIngreso>{self._format_date(doc.get("fechaingreso", ""))}</FechaIngreso>\n'
                xml += f'\t\t<TipoInstrumento>E</TipoInstrumento>\n'
                xml += f'\t\t<NumDocumento>{doc.get("numescritura", "")}</NumDocumento>\n'
                xml += f'\t\t<FechaInstrumento>{doc.get("fechaescritura", "")}</FechaInstrumento>\n'
                xml += f'\t\t<NumFolios>{self._calculate_num_folios(doc)}</NumFolios>\n'
                if doc.get("fechaconclusion"):
                    xml += f'\t\t<FechaConclusion>{self._format_date(doc.get("fechaconclusion", ""))}</FechaConclusion>\n'
                xml += '\t</Documento>\n'

                # Add Maestros section
                xml += '\t<Maestros>\n'
                
                # Process participants
                natural_persons = []
                juridical_persons = []
                for participant in doc.get('participants', []):
                    if participant.get('tipper') == 'J':
                        juridical_persons.append(participant)
                    elif participant.get('tipper') == 'N':
                        natural_persons.append(participant)

                if natural_persons:
                    xml += '\t\t<PersonasNaturales>\n'
                    for person in natural_persons:
                        xml += f'\t\t\t<PersonaNatural id="{person.get("idcliente", "")}">\n'
                        xml += '\t\t\t<DocsIdentificativos>\n'
                        xml += '\t\t\t\t<DocIdentificativo>\n'
                        xml += f'\t\t\t\t\t<TipoDocIdentidad>{str(person.get("idtipdoc", "")).zfill(2)}</TipoDocIdentidad>\n'
                        if person.get("numdoc"):
                            xml += f'\t\t\t\t\t<NumDocIdentificativo>{person.get("numdoc", "")}</NumDocIdentificativo>\n'
                        xml += '\t\t\t\t</DocIdentificativo>\n'
                        xml += '\t\t\t</DocsIdentificativos>\n'
                        
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
                            xml += f'\t\t\t\t<PaisNacionalidad>PE</PaisNacionalidad>\n'
                        if person.get("cumpclie"):
                            xml += f'\t\t\t\t<FechaNacimiento>{self._format_date(person.get("cumpclie", ""))}</FechaNacimiento>\n'
                        if person.get("idprofesion"):
                            xml += f'\t\t\t\t<Profesion>{self._get_valid_profession_code(person.get("idprofesion", ""))}</Profesion>\n'
                        xml += '\t\t\t\t<Cargo>998</Cargo>\n'
                        
                        # Add address if all required fields are present
                        if person.get("idubigeo") and person.get("direccion"):
                            xml += '\t\t\t\t<Direccion>\n'
                            xml += '\t\t\t\t\t<ResidePeru>1</ResidePeru>\n'
                            xml += '\t\t\t\t\t<PaisResidencia>PE</PaisResidencia>\n'
                            xml += '\t\t\t\t<DireccionNacional>\n'
                            ubigeo = person.get("idubigeo", "")
                            if len(ubigeo) == 6:
                                xml += f'\t\t\t\t\t<CodDepartamento>{ubigeo[:2]}</CodDepartamento>\n'
                                xml += f'\t\t\t\t\t<CodProvincia>{ubigeo[2:4]}</CodProvincia>\n'
                                xml += f'\t\t\t\t\t<CodDistrito>{ubigeo[4:]}</CodDistrito>\n'
                            xml += f'\t\t\t\t\t<RestoDireccion>{person.get("direccion", "")}</RestoDireccion>\n'
                            xml += '\t\t\t\t</DireccionNacional>\n'
                            xml += '\t\t\t\t</Direccion>\n'
                        xml += '\t\t\t</PersonaNatural>\n'
                    xml += '\t\t</PersonasNaturales>\n'

                if juridical_persons:
                    xml += '\t\t<PersonasJuridicas>\n'
                    for person in juridical_persons:
                        xml += f'\t\t\t<PersonaJuridica id="{person.get("idcliente", "")}">\n'
                        xml += '\t\t\t<DocsIdentificativos>\n'
                        xml += '\t\t\t\t<DocIdentificativo>\n'
                        xml += f'\t\t\t\t\t<TipoDocIdentidad>{str(person.get("idtipdoc", "")).zfill(2)}</TipoDocIdentidad>\n'
                        if person.get("numdoc"):
                            xml += f'\t\t\t\t\t<NumDocIdentificativo>{person.get("numdoc", "")}</NumDocIdentificativo>\n'
                        xml += '\t\t\t\t</DocIdentificativo>\n'
                        xml += '\t\t\t</DocsIdentificativos>\n'
                        
                        xml += '\t\t\t\t<RegistroFacultades>\n'
                        if person.get("idsedereg"):
                            xml += f'\t\t\t\t\t<SedeRegistral>{person.get("idsedereg", "")}</SedeRegistral>\n'
                        if person.get("numpartida"):
                            xml += f'\t\t\t\t\t<PartidaRegistral>{person.get("numpartida", "")}</PartidaRegistral>\n'
                        xml += '\t\t\t\t</RegistroFacultades>\n'
                        
                        if person.get("razonsocial"):
                            xml += f'\t\t\t\t<RazonSocial>{person.get("razonsocial", "")}</RazonSocial>\n'
                        # SISGEN XSD expects OtraActividad (ObjetoSocial is not a valid tag here).
                        # Use actmunicipal as primary source, fallback to contacempresa.
                        otra_actividad = (person.get("actmunicipal") or person.get("contacempresa") or "").strip()
                        if otra_actividad:
                            xml += f'\t\t\t\t<OtraActividad>{otra_actividad}</OtraActividad>\n'
                        
                        # Add address if all required fields are present
                        if person.get("idubigeo") and person.get("domfiscal"):
                            xml += '\t\t\t\t<Direccion>\n'
                            xml += '\t\t\t\t\t<ResidePeru>1</ResidePeru>\n'
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
                        xml += '\t\t\t</PersonaJuridica>\n'
                    xml += '\t\t</PersonasJuridicas>\n'

                xml += '\t</Maestros>\n'

                # Add Operaciones section
                xml += '\t<Operaciones>\n'
                xml += f'\t\t<Operacion id="{doc.get("codactos", "")}">\n'
                xml += f'\t\t\t<CodActoJuridico>{doc.get("cod_ancert", "")}</CodActoJuridico>\n'
                xml += '\t\t<Operantes>\n'
                xml += '\t\t\t<Objetos>\n'
                xml += '\t\t\t</Objetos>\n'
                xml += '\t\t\t<Intervenciones>\n'
                
                # Group participants by role and condition
                participants_by_role = {}
                for participant in doc.get('participants', []):
                    role = participant.get('uif', 'O')
                    condition = participant.get('idcondicion', '')
                    key = f"{role}_{condition}"
                    if key not in participants_by_role:
                        participants_by_role[key] = []
                    participants_by_role[key].append(participant)
                
                # Process each role group
                for key, participants in participants_by_role.items():
                    if not participants:
                        continue
                    
                    role = key.split('_')[0]
                    tipo_int, desc_int = self._get_tipo_intervencion_desc(
                        role=role,
                        acto_juridico=doc.get('cod_ancert'),
                        participant_data=participants[0]  # Pass the first participant as data
                    )
                    
                    xml += '\t\t\t\t<Intervencion>\n'
                    xml += f'\t\t\t\t\t<TipoIntervencion>{tipo_int}</TipoIntervencion>\n'
                    xml += f'\t\t\t\t\t<DescripcionIntervencion>{desc_int}</DescripcionIntervencion>\n'
                    xml += f'\t\t\t\t\t<RolRepresentante>{role}</RolRepresentante>\n'
                    xml += '\t\t\t\t\t<Sujetos>\n'
                    
                    for participant in participants:
                        xml += '\t\t\t\t\t\t<Sujeto>\n'
                        xml += f'\t\t\t\t\t\t\t<IdMaestro>{participant.get("idcliente", "")}</IdMaestro>\n'
                        
                        # Add OrigenFondos
                        if participant.get("ofondo"):
                            xml += '\t\t\t\t\t\t\t<OrigenFondos>\n'
                            xml += '\t\t\t\t\t\t\t\t<OrigenFondo>\n'
                            xml += f'\t\t\t\t\t\t\t\t\t<Origen>{participant.get("ofondo", "").upper()}</Origen>\n'
                            xml += f'\t\t\t\t\t\t\t\t\t<CuantiaOrigen>{self._safe_float(participant.get("monto", "0.00")):.2f}</CuantiaOrigen>\n'
                            xml += '\t\t\t\t\t\t\t\t\t<TipoMonedaPago>01</TipoMonedaPago>\n'
                            xml += '\t\t\t\t\t\t\t\t</OrigenFondo>\n'
                            xml += '\t\t\t\t\t\t\t</OrigenFondos>\n'
                        
                        xml += '\t\t\t\t\t\t\t<Derecho>\n'
                        if participant.get("porcentaje"):
                            xml += f'\t\t\t\t\t\t\t\t<PorcentajeDerecho>{self._safe_float(participant.get("porcentaje", "100")):.2f}</PorcentajeDerecho>\n'
                        xml += '\t\t\t\t\t\t\t</Derecho>\n'
                        
                        # Add tax flags for otorgantes
                        if role == 'O':
                            xml += '\t\t\t\t\t\t\t<Renta3Cat>0</Renta3Cat>\n'
                            xml += '\t\t\t\t\t\t\t<CasaEnajenante>0</CasaEnajenante>\n'
                            xml += '\t\t\t\t\t\t\t<ImpuestoCero>0</ImpuestoCero>\n'
                        
                        # Add Representantes section
                        xml += '\t\t\t\t\t\t\t<Representantes>\n'
                        # Find representatives for this participant
                        reps = [p for p in doc.get('participants', []) if p.get('tiporepresentacion') == '1' and p.get('idcontratanterp') == participant.get('idcontratante')]
                        for rep in reps:
                            xml += '\t\t\t\t\t\t\t\t<Representante>\n'
                            xml += f'\t\t\t\t\t\t\t\t\t<IdMaestro>{rep.get("idcliente", "")}</IdMaestro>\n'
                            if rep.get("inscrito") == "1" and (rep.get("idsedereg") or rep.get("numpartida")):
                                xml += '\t\t\t\t\t\t\t\t\t<InscripcionRepresentacion>\n'
                                if rep.get("idsedereg"):
                                    xml += f'\t\t\t\t\t\t\t\t\t\t<SedeRegistral>{rep.get("idsedereg", "")}</SedeRegistral>\n'
                                if rep.get("numpartida"):
                                    xml += f'\t\t\t\t\t\t\t\t\t\t<PartidaRegistral>{rep.get("numpartida", "")}</PartidaRegistral>\n'
                                xml += '\t\t\t\t\t\t\t\t\t</InscripcionRepresentacion>\n'
                            if rep.get("fechafirma"):
                                xml += f'\t\t\t\t\t\t\t\t\t<FechaFirma>{self._format_date(rep.get("fechafirma", ""))}</FechaFirma>\n'
                            xml += '\t\t\t\t\t\t\t\t</Representante>\n'
                        xml += '\t\t\t\t\t\t\t</Representantes>\n'
                        
                        if participant.get("fechafirma"):
                            xml += f'\t\t\t\t\t\t\t<FechaFirma>{self._format_date(participant.get("fechafirma", ""))}</FechaFirma>\n'
                        xml += '\t\t\t\t\t\t</Sujeto>\n'
                    xml += '\t\t\t\t\t</Sujetos>\n'
                    xml += '\t\t\t\t</Intervencion>\n'

                xml += '\t\t\t</Intervenciones>\n'
                
                # Add NoIntervinientes section
                xml += '\t\t\t<NoIntervinientes>\n'
                xml += '\t\t\t</NoIntervinientes>\n'
                xml += '\t\t</Operantes>\n'
                
                # Add CuantiaOperacion section
                xml += '\t\t<CuantiaOperacion>\n'
                total_monto = sum(self._safe_float(p.get("monto", "0.00")) for p in doc.get('participants', []))
                xml += f'\t\t\t<Cuantia>{total_monto:.2f}</Cuantia>\n'
                xml += '\t\t\t<TipoMoneda>01</TipoMoneda>\n'
                xml += '\t\t</CuantiaOperacion>\n'
                
                # Add MediosPagos section
                xml += '\t\t<MediosPagos>\n'
                xml += '\t\t<MediosPago>\n'
                xml += '\t\t\t<MedioPago>001</MedioPago>\n'
                xml += '\t\t\t<FormaPago>C</FormaPago>\n'
                xml += '\t\t\t<MomentoPago>1</MomentoPago>\n'
                xml += f'\t\t\t<CuantiaPago>{total_monto:.2f}</CuantiaPago>\n'
                xml += '\t\t\t<TipoMonedaPago>01</TipoMonedaPago>\n'
                xml += '\t\t\t<JustificadoManifestado>1</JustificadoManifestado>\n'
                xml += f'\t\t\t<FechaPago>{doc.get("fechaescritura", "")}</FechaPago>\n'
                xml += '\t\t\t<IdPago>0746978</IdPago>\n'
                xml += '\t\t\t<EntidadFinanciera>00002</EntidadFinanciera>\n'
                xml += '\t\t</MediosPago>\n'
                xml += '\t\t</MediosPagos>\n'
                
                # Add contract details
                xml += f'\t\t\t<NombreContrato>{doc.get("contrato", "").strip(" /")}</NombreContrato>\n'
                xml += f'\t\t\t<FechaMinuta>{doc.get("fechaescritura", "")}</FechaMinuta>\n'
                
                xml += '\t\t</Operacion>\n'
                xml += '\t</Operaciones>\n'
                xml += '\t</DocumentoNotarial>\n'

            xml += '</DocumentosNotariales>'
            
            # Clean XML content like PHP
            xml = (xml
                .replace("&", "&amp;")
                .replace("Ã'", "Ñ")
                .replace("Ï¿½", "Ñ")
                .replace("Ï¿Ï¿½", "Ñ"))
            
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