"""
This module contains the document search service for the sisgen service.
"""

from typing import Dict, List, Tuple, Optional
import logging
import json
from decimal import Decimal
from datetime import datetime
from django.db import connection
from ..utils.exceptions import DocumentSearchException, ValidationException
from ..utils.validators import SearchFiltersValidator
from ..utils.constants import ESTADO_SISGEN_MAPPING, ERROR_MESSAGES
from .uif_validation_service import UIFValidationService
from notaria.services.pdt_escrituras_service import PdtEscriturasService
from notaria.services.pdt_vehiculares_service import PdtVehicularesService
from notaria.services.pdt_garantias_service import PdtGarantiasService
import math

logger = logging.getLogger(__name__)

class DocumentSearchService:
    def __init__(self):
        self.logger = logger
        self.validator = SearchFiltersValidator()
        # Initialize error tracking dictionaries by kardex
        self.kardex_errors = {}  # {kardex: [errors]}
        self.kardex_observations = {}  # {kardex: [observations]}
        self.person_errors = {}  # {kardex: [person_errors]}
        self.pdt_errors = {}  # {kardex: [pdt_errors]}
        # Initialize UIF validation service
        self.uif_validator = UIFValidationService()
        # Initialize batch processing state
        self.search_id = None
        self.all_kardex = []  # Store all kardex numbers in order
        self.processed_kardex = set()
        self.total_documents = 0
        self.validated_filters = None
        self.current_page = 1
        self.batch_size = 10  # Fixed batch size
        # Initialize PDT services
        self._init_pdt_services()

    def _init_pdt_services(self):
        """Initialize PDT services with None dates - will be set during validation"""
        self.pdt_escrituras = PdtEscriturasService('', '')
        self.pdt_vehiculares = PdtVehicularesService('', '')
        self.pdt_garantias = PdtGarantiasService('', '')

    @classmethod
    def from_session_data(cls, session_data: Dict) -> 'DocumentSearchService':
        """Create service instance from session data"""
        service = cls()
        service.search_id = session_data.get('search_id')
        service.all_kardex = session_data.get('all_kardex', [])
        service.processed_kardex = set(session_data.get('processed_kardex', []))
        service.total_documents = session_data.get('total_documents', 0)
        service.validated_filters = session_data.get('validated_filters')
        service.current_page = session_data.get('current_page', 1)
        return service

    def get_session_data(self) -> Dict:
        """Get serializable session data"""
        return {
            'search_id': self.search_id,
            'all_kardex': self.all_kardex,
            'processed_kardex': list(self.processed_kardex),
            'total_documents': self.total_documents,
            'validated_filters': self.validated_filters,
            'current_page': self.current_page
        }

    def _add_error(self, kardex: str, error: str):
        """Add error for a specific kardex"""
        if kardex not in self.kardex_errors:
            self.kardex_errors[kardex] = []
        self.kardex_errors[kardex].append(error)
    
    def _add_observation(self, kardex: str, observation: str):
        """Add observation for a specific kardex"""
        if kardex not in self.kardex_observations:
            self.kardex_observations[kardex] = []
        self.kardex_observations[kardex].append(observation)
    
    def _add_person_error(self, kardex: str, error: str):
        """Add person error for a specific kardex"""
        if kardex not in self.person_errors:
            self.person_errors[kardex] = []
        self.person_errors[kardex].append(error)

    def initialize_search(self, filters: Dict) -> Dict:
        """Initialize a new search session"""
        try:
            # Reset error tracking lists and state
            self.kardex_errors = {}
            self.kardex_observations = {}
            self.person_errors = {}
            self.current_page = 1
            
            # Log incoming filters
            self.logger.info(f"Search request with filters: {json.dumps(filters, indent=2)}")
            
            # Validate filters
            self.validated_filters = self.validator.validate(filters)
            
            # Get initial document list (only basic info)
            with connection.cursor() as cursor:
                query = """
                    SELECT k.kardex, k.numescritura
                    FROM kardex k
                    LEFT JOIN tiposdeacto ta ON SUBSTRING(k.codactos,1,3) = ta.idtipoacto
                    WHERE 1=1
                """
                conditions, params = self._build_filter_conditions(self.validated_filters)
                if conditions:
                    query += " AND " + " AND ".join(conditions)
                query += (
                    " ORDER BY CAST(NULLIF(TRIM(k.numescritura), '') AS UNSIGNED), k.kardex"
                )
                
                cursor.execute(query, params)
                documents = cursor.fetchall()
            
            # Generate unique search ID and store state
            self.search_id = f"search_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(documents)}"
            self.total_documents = len(documents)
            self.all_kardex = [doc[0] for doc in documents]  # Store all kardex numbers in order
            self.processed_kardex = set()
            
            # Handle empty results case
            if self.total_documents == 0:
                return {
                    'search_id': self.search_id,
                    'total_documents': 0,
                    'processed': 0,
                    'current_page': 1,
                    'total_pages': 1,  # At least one page even when empty
                    'has_next': False,
                    'has_previous': False,
                    'message': 'No se encontraron documentos que coincidan con los criterios de búsqueda.'
                }
            
            return {
                'search_id': self.search_id,
                'total_documents': self.total_documents,
                'processed': 0,
                'current_page': 1,
                'total_pages': math.ceil(self.total_documents / self.batch_size),
                'has_next': self.total_documents > self.batch_size,
                'has_previous': False
            }
            
        except Exception as e:
            self.logger.error(f"Error initializing search: {str(e)}")
            raise DocumentSearchException(f"Failed to initialize search: {str(e)}")

    def get_page(self, search_id: str, page: int = 1) -> Tuple[List[Dict], Dict, Dict]:
        """Get specific page of documents"""
        if search_id != self.search_id:
            raise DocumentSearchException("Invalid search session")
            
        try:
            # Handle no results case
            if self.total_documents == 0:
                return [], self._get_error_details(), {
                    'search_id': self.search_id,
                    'total_documents': 0,
                    'processed': 0,
                    'current_page': 1,
                    'total_pages': 1,  # At least one page even when empty
                    'has_next': False,
                    'has_previous': False,
                    'page_size': self.batch_size,
                    'message': 'No se encontraron documentos que coincidan con los criterios de búsqueda.'
                }
            
            # Calculate page bounds
            total_pages = math.ceil(self.total_documents / self.batch_size)
            if page < 1 or page > total_pages:
                raise DocumentSearchException(f"Invalid page number. Must be between 1 and {total_pages}")
            
            # Calculate slice indices
            start_idx = (page - 1) * self.batch_size
            end_idx = min(start_idx + self.batch_size, self.total_documents)
            
            # Get kardex numbers for this page
            page_kardex = self.all_kardex[start_idx:end_idx]
            
            # Reset error tracking for this page
            self.kardex_errors = {}
            self.kardex_observations = {}
            self.person_errors = {}
            self.pdt_errors = {}
            
            # Get full document data for this page
            documents = self._execute_batch_query(page_kardex)
            
            # Run validations but don't block on errors
            try:
                self._validate_document_data(documents)
            except Exception as e:
                self.logger.warning(f"Document validation warning: {str(e)}")
                
            try:
                self._validate_person_data(documents)
            except Exception as e:
                self.logger.warning(f"Person validation warning: {str(e)}")
                
            try:
                self._validate_pdt_data(documents)
            except Exception as e:
                self.logger.warning(f"PDT validation warning: {str(e)}")
            
            # Process documents
            processed_data = self._process_documents(documents, self.validated_filters)
            
            # Update tracking
            self.processed_kardex.update(page_kardex)
            self.current_page = page
            
            # Get error details and status
            error_details = self._get_error_details()
            page_status = self._get_page_status()
            
            return processed_data, error_details, page_status
            
        except Exception as e:
            self.logger.error(f"Error getting page {page}: {str(e)}")
            raise DocumentSearchException(f"Failed to get page: {str(e)}")

    def _get_page_status(self) -> Dict:
        """Get current page status"""
        total_pages = math.ceil(self.total_documents / self.batch_size)
        return {
            'search_id': self.search_id,
            'total_documents': self.total_documents,
            'processed': len(self.processed_kardex),
            'current_page': self.current_page,
            'total_pages': total_pages,
            'has_next': self.current_page < total_pages,
            'has_previous': self.current_page > 1,
            'page_size': self.batch_size
        }

    def _execute_batch_query(self, kardex_list: List[str]) -> List[Dict]:
        """Execute query for a batch of kardex numbers"""
        query = """
            SELECT k.idkardex, k.kardex, k.numescritura, k.fechaescritura,
                   IF(ta.cod_ancert IS NULL,'',ta.cod_ancert) AS cod_ancert,
                   k.estado_sisgen, k.idtipkar, k.fechaingreso, k.codactos,
                   k.contrato, k.folioini, k.foliofin, k.fechaconclusion,
                   ta.actouif, ta.actosunat,
                   ta.mediospago, ta.cuantia, ta.origenfondo, ta.impuestorenta,
                   IFNULL(ta.desacto, '') AS desacto,
                   cn.codnotario, cn.codoficial, cn.coduif,
                   CONCAT(cn.nombre, ' ', cn.apellido) as nombre_notario,
                   cn.direccion as direccion_notario,
                   cn.distrito as distrito_notario,
                   cn.provincia as provincia_notario,
                   cn.departamento as departamento_notario
            FROM kardex k
            LEFT JOIN tiposdeacto ta ON SUBSTRING(k.codactos,1,3) = ta.idtipoacto
            LEFT JOIN confinotario cn ON 1=1
            WHERE k.kardex IN %s
        """
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, [tuple(kardex_list)])
                columns = [col[0] for col in cursor.description]
                rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
                # IN (...) does not preserve order; keep same order as initialize_search
                # (numeric numescritura, then kardex).
                order = {kx: i for i, kx in enumerate(kardex_list)}
                tail = len(kardex_list)
                rows.sort(key=lambda r: order.get(r.get("kardex"), tail))
                return rows
        except Exception as e:
            self.logger.error(f"Database query error: {str(e)}")
            raise DocumentSearchException(f"Database query failed: {str(e)}")

    @staticmethod
    def _reference_date_in_range_sql(fecha_desde: str, fecha_hasta: str) -> Tuple[str, List]:
        """
        Rango por fecha de referencia del expediente.

        ``k.fechaescritura`` es VARCHAR y en legado viene en ISO (YYYY-MM-DD) o DD/MM/YYYY;
        un ``BETWEEN`` lexicográfico sobre strings excluye filas válidas. En vehículos a veces
        ``fechaescritura`` viene vacío y la fecha útil está en ``fechaconclusion`` / ``fechainstrumento``.
        """
        sql = """(
            COALESCE(
                STR_TO_DATE(NULLIF(TRIM(k.fechaescritura), ''), '%%Y-%%m-%%d'),
                STR_TO_DATE(NULLIF(TRIM(k.fechaescritura), ''), '%%d/%%m/%%Y'),
                STR_TO_DATE(NULLIF(TRIM(k.fechaconclusion), ''), '%%d/%%m/%%Y'),
                STR_TO_DATE(NULLIF(TRIM(k.fechainstrumento), ''), '%%d/%%m/%%Y'),
                STR_TO_DATE(NULLIF(TRIM(k.fechainstrumento), ''), '%%Y-%%m-%%d')
            ) BETWEEN CAST(%s AS DATE) AND CAST(%s AS DATE)
        )"""
        return sql, [fecha_desde, fecha_hasta]

    def _build_filter_conditions(self, filters: Dict) -> Tuple[List[str], List]:
        """Extract filter conditions from _build_sql_query"""
        conditions = []
        params = []
        
        # Date range
        if filters.get('fechaDesde') and filters.get('fechaHasta'):
            ds, ps = self._reference_date_in_range_sql(
                filters["fechaDesde"], filters["fechaHasta"]
            )
            conditions.append(ds)
            params.extend(ps)
        
        # Instrument type
        if filters.get('tipoInstrumento'):
            conditions.append("k.idtipkar = %s")
            params.append(filters['tipoInstrumento'])
        
        # Status filter
        estado = filters.get('estado')
        if estado == 4:
            conditions.append("(ta.cod_ancert = '' OR ta.cod_ancert IS NULL)")
        elif estado == 0:
            conditions.append("k.estado_sisgen = %s")
            params.append(estado)
        elif estado == 3:
            conditions.append("k.estado_sisgen = '3'")
        elif estado != 5 and estado != -1 and estado is not None:
            conditions.append("k.estado_sisgen = %s")
            params.append(estado)
        
        # Act code
        if filters.get('codigoActo') and filters['codigoActo'] != 0:
            conditions.append("ta.idtipoacto = %s")
            params.append(filters['codigoActo'])
        
        # Basic filters
        conditions.extend([
            "k.numescritura <> ''",
            "k.kardex <> ''"
        ])
        
        return conditions, params

    def search_documents(self, filters: Dict) -> Tuple[List[Dict], int, List[str], Dict]:
        """
        Search for notarial documents
        Returns: (data, total_count, errors, error_details)
        error_details contains: {
            'kardex_errors': List of kardex-level errors,
            'observations': List of observations/warnings,
            'person_errors': List of person-related errors
        }
        """
        try:
            # Reset error tracking lists
            self.kardex_errors = {}
            self.kardex_observations = {}
            self.person_errors = {}
            
            # Log incoming filters
            self.logger.info(f"Search request with filters: {json.dumps(filters, indent=2)}")
            
            # Validate filters
            validated_filters = self.validator.validate(filters)
            
            # Build and execute query
            documents = self._execute_search_query(validated_filters)
            
            # Process results
            processed_data = self._process_documents(documents, validated_filters)
            
            # Run validations but don't block on errors
            try:
                self._validate_document_data(processed_data)
            except Exception as e:
                self.logger.warning(f"Document validation warning: {str(e)}")
                
            try:
                self._validate_person_data(processed_data)
            except Exception as e:
                self.logger.warning(f"Person validation warning: {str(e)}")
            
            self.logger.info(f"Found {len(processed_data)} documents")
            
            # Debug log error tracking state
            self.logger.debug(f"Error tracking state before formatting:")
            self.logger.debug(f"Kardex errors: {self.kardex_errors}")
            self.logger.debug(f"Kardex observations: {self.kardex_observations}")
            self.logger.debug(f"Person errors: {self.person_errors}")
            
            # Process results again to include error data
            processed_data = self._process_documents(documents, validated_filters)
            
            error_details = {
                'kardex_errors': self.kardex_errors,
                'observations': self.kardex_observations,
                'person_errors': self.person_errors
            }
            
            # Generate response XML for debugging
            try:
                self._generate_debug_xml(processed_data, error_details, filters)
            except Exception as e:
                self.logger.warning(f"Error generating debug XML: {str(e)}")
            
            # Always return data even if there are validation warnings
            return processed_data, len(processed_data), [], error_details
            
        except ValidationException as e:
            # Only fail on filter validation errors
            self.logger.error(f"Filter validation error: {str(e)}")
            self._generate_error_xml("Validation Error", str(e), filters)
            return [], 0, [str(e)], self._get_error_details()
        except DocumentSearchException as e:
            self.logger.error(f"Document search error: {str(e)}")
            self._generate_error_xml("Document Search Error", str(e), filters)
            return [], 0, [str(e)], self._get_error_details()
        except Exception as e:
            self.logger.error(f"Unexpected error in document search: {str(e)}")
            self._generate_error_xml("Unexpected Error", str(e), filters)
            return [], 0, [ERROR_MESSAGES['DATABASE_ERROR'].format(error=str(e))], self._get_error_details()

    def _get_error_details(self) -> Dict:
        """Return current error tracking details"""
        return {
            'kardex_errors': self.kardex_errors,
            'observations': self.kardex_observations,
            'person_errors': self.person_errors,
            'pdt_errors': self.pdt_errors
        }

    def _validate_document_data(self, documents: List[Dict]):
        """Validate document data and track errors"""
        for doc in documents:
            kardex = doc.get('kardex', '')
            self.logger.debug(f"Validating document data for kardex: {kardex}")
            
            # Validate required fields
            required_fields = ['numescritura', 'fechaescritura', 'idtipkar', 'codactos']
            for field in required_fields:
                if not doc.get(field):
                    self._add_error(kardex, f"Falta campo requerido: {field}")
            
            # Validate date formats
            if doc.get('fechaescritura'):
                try:
                    self._format_date_safely(doc['fechaescritura'])
                except ValueError:
                    self._add_error(kardex, "Formato de fecha de escritura inválido")
            
            # Validate numeric fields
            if doc.get('numescritura') and not str(doc['numescritura']).strip().isdigit():
                self._add_observation(kardex, "El número de escritura debe ser numérico")
            
            # Check for ANCERT code
            if not doc.get('cod_ancert'):
                self._add_observation(kardex, "Falta código ANCERT")
            
            # Validate UIF data
            self._validate_uif_data(doc)
            self._validate_detalle_mediopago_moneda(kardex)
            
            self.logger.debug(f"After validation for kardex {kardex}:")
            self.logger.debug(f"Errors: {self.kardex_errors.get(kardex, [])}")
            self.logger.debug(f"Observations: {self.kardex_observations.get(kardex, [])}")

    def _sisgen_skip_uif_money_checks(self, doc: Dict) -> bool:
        """
        PHP validarUIFSUNAT: actos en actosNOUIFSUNAT (p. ej. 0604) no exigen
        montos ni origen de fondos en contratantesxacto.
        """
        from sisgen.sisgen_acto_xml_rules import doc_requires_uif_sunat_xml

        return not doc_requires_uif_sunat_xml(doc)

    def _validate_detalle_mediopago_moneda(self, kardex: str):
        """ValidarMoneda-style: moneda en detallemediopago requiere importemp > 0."""
        if not kardex:
            return
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT importemp, idmon FROM detallemediopago
                    WHERE kardex = %s
                    """,
                    [kardex],
                )
                for importemp, idmon in cursor.fetchall():
                    ims = str(idmon).strip() if idmon is not None else ""
                    if ims in ("", "0", "None"):
                        continue
                    try:
                        amt = float(importemp or 0)
                    except (TypeError, ValueError):
                        amt = 0.0
                    if amt <= 0:
                        self._add_error(
                            kardex,
                            "detallemediopago: moneda informada sin importe válido",
                        )
        except Exception as e:
            self.logger.warning(
                "No se pudo validar detallemediopago para kardex %s: %s",
                kardex,
                e,
            )

    def _validate_uif_data(self, doc: Dict):
        """Validate UIF-related data"""
        kardex = doc.get('kardex', '')
        self.logger.debug(f"Validating UIF data for kardex: {kardex}")

        if self._sisgen_skip_uif_money_checks(doc):
            self.logger.debug(
                "Saltando validaciones UIF monetarias (actouif no aplica) kardex=%s",
                kardex,
            )
            return
        
        try:
            # Get UIF data for the kardex
            with connection.cursor() as cursor:
                query = """
                    SELECT 
                        cx.uif, cx.monto, cx.ofondo,
                        CASE 
                            WHEN c.tipper = 'N' THEN CONCAT(COALESCE(c.prinom, ''), ' ', COALESCE(c.segnom, ''), ' ', COALESCE(c.apepat, ''), ' ', COALESCE(c.apemat, ''))
                            WHEN c.tipper = 'J' THEN c.razonsocial
                            ELSE 'Desconocido'
                        END as nombre_completo,
                        c.tipper,
                        c.numdoc
                    FROM contratantesxacto cx
                    LEFT JOIN cliente2 c ON cx.idcontratante = c.idcontratante
                    WHERE cx.kardex = %s
                    AND (cx.uif IN ('O', 'B', 'G', 'N', 'R'))
                """
                cursor.execute(query, [kardex])
                uif_records = cursor.fetchall()
                
                if not uif_records:
                    self._add_observation(kardex, "No se encontraron registros UIF")
                    return
                
                for uif_record in uif_records:
                    uif, monto, ofondo, nombre_completo, tipper, numdoc = uif_record
                    role_name = 'Otorgante' if uif == 'O' else 'Beneficiario'
                    
                    # Format person identifier
                    person_id = f"{nombre_completo.strip()} ({numdoc})" if numdoc else nombre_completo.strip()
                    
                    # Validate monto for operations
                    if uif in ('O', 'B') and (not monto or float(monto or 0) <= 0):
                        self._add_error(kardex, f"Monto inválido para {role_name}: {person_id}")
                    
                    # Validate origen de fondos
                    if uif in ('O', 'B') and not ofondo:
                        self._add_error(kardex, f"Falta origen de fondos para {role_name}: {person_id}")
                
        except Exception as e:
            self.logger.error(f"Error validating UIF data for kardex {kardex}: {str(e)}")
            self._add_error(kardex, "Error al validar datos UIF")
            
        self.logger.debug(f"After UIF validation for kardex {kardex}:")
        self.logger.debug(f"Errors: {self.kardex_errors.get(kardex, [])}")
        self.logger.debug(f"Observations: {self.kardex_observations.get(kardex, [])}")

    def _validate_person_data(self, documents: List[Dict]):
        """Validate person data and track errors"""
        for doc in documents:
            kardex = doc.get('kardex', '')
            self.logger.debug(f"Validating person data for kardex: {kardex}")
            skip_uif_strict = self._sisgen_skip_uif_money_checks(doc)
            
            # Get participants data using the kardex
            participants = self._get_participants_for_kardex(kardex)
            
            for participant in participants:
                person_id = participant.get('idcontratante', 'Unknown')
                
                # Format person name based on type
                if participant.get('tipper') == 'N':
                    nombre = f"{participant.get('prinom', '')} {participant.get('segnom', '')} {participant.get('apepat', '')} {participant.get('apemat', '')}".strip()
                    person_id = f"{nombre} ({participant.get('numdoc', '')})" if participant.get('numdoc') else nombre
                    
                    # Validate natural person data
                    if not participant.get('numdoc'):
                        self._add_person_error(kardex, f"{person_id}: Falta número de documento")
                    if not participant.get('apepat'):
                        self._add_person_error(kardex, f"{person_id}: Falta apellido paterno")
                    if not participant.get('prinom'):
                        self._add_person_error(kardex, f"{person_id}: Falta primer nombre")
                    
                    # Additional validations for natural persons
                    self._validate_natural_person(
                        kardex, participant, skip_uif_strict=skip_uif_strict
                    )
                
                # Validate juridical person data
                elif participant.get('tipper') == 'J':
                    razon_social = participant.get('razonsocial', '').strip()
                    person_id = f"{razon_social} (RUC: {participant.get('numdoc', '')})" if participant.get('numdoc') else razon_social
                    
                    if not participant.get('numdoc'):
                        self._add_person_error(kardex, f"{person_id}: Falta RUC")
                    if not participant.get('razonsocial'):
                        self._add_person_error(kardex, f"{person_id}: Falta razón social")
                    
                    # Additional validations for juridical persons
                    self._validate_juridical_person(
                        kardex, participant, skip_uif_strict=skip_uif_strict
                    )
            
            self.logger.debug(f"After person validation for kardex {kardex}:")
            self.logger.debug(f"Person errors: {self.person_errors.get(kardex, [])}")

    def _validate_natural_person(
        self, kardex: str, person: Dict, skip_uif_strict: bool = False
    ):
        """Additional validations for natural persons"""
        # Format person name
        nombre = f"{person.get('prinom', '')} {person.get('segnom', '')} {person.get('apepat', '')} {person.get('apemat', '')}".strip()
        person_id = f"{nombre} ({person.get('numdoc', '')})" if person.get('numdoc') else nombre
        
        # Validate document type and number format
        doc_type = person.get('idtipdoc')
        doc_number = person.get('numdoc')
        
        if doc_type == '1':  # DNI
            if doc_number and (len(doc_number) != 8 or not doc_number.isdigit()):
                self._add_person_error(kardex, f"{person_id}: Formato de DNI inválido")
        elif doc_type == '4':  # CE
            if doc_number and len(doc_number) > 12:
                self._add_person_error(kardex, f"{person_id}: Formato de CE inválido")
        
        # Contacto (PHP lo condiciona a actos con UIF / SUNAT según validarUIFSUNAT)
        if not skip_uif_strict and not any(
            [person.get('telfijo'), person.get('telcel'), person.get('email')]
        ):
            self._add_person_error(
                kardex,
                f"{person_id}: Falta información de contacto (registre al menos uno: telfijo, telcel o email)",
            )
        
        # Validate address
        if not person.get('direccion') or not person.get('idubigeo'):
            self._add_person_error(kardex, f"{person_id}: Información de dirección incompleta")

    def _validate_juridical_person(
        self, kardex: str, person: Dict, skip_uif_strict: bool = False
    ):
        """Additional validations for juridical persons"""
        # Format company name
        razon_social = person.get('razonsocial', '').strip()
        person_id = f"{razon_social} (RUC: {person.get('numdoc', '')})" if person.get('numdoc') else razon_social
        
        # Validate RUC format
        ruc = person.get('numdoc')
        if ruc and (len(ruc) != 11 or not ruc.isdigit() or not ruc.startswith('20')):
            self._add_person_error(kardex, f"{person_id}: Formato de RUC inválido")
        
        # Validate required registration data
        if not person.get('fechaconstitu'):
            self._add_person_error(kardex, f"{person_id}: Falta fecha de constitución")
        
        num_part = person.get('numpartidareg') or person.get('numpartida')
        if not person.get('idsedereg') or not num_part:
            self._add_person_error(kardex, f"{person_id}: Falta información registral")
        
        if not skip_uif_strict and not person.get('telempresa') and not person.get(
            'mailempresa'
        ):
            self._add_person_error(
                kardex,
                f"{person_id}: Falta información de contacto de la empresa (registre al menos uno: telempresa o mailempresa)",
            )

    def _get_participants_for_kardex(self, kardex: str) -> List[Dict]:
        """Get participants data for a kardex"""
        try:
            with connection.cursor() as cursor:
                # Query similar to PHP's natural and juridical person queries
                query = """
                    SELECT 
                        cl.idcontratante, cl.idcliente AS id, cl.tipper,
                        cl.apepat, cl.apemat, cl.prinom, cl.segnom,
                        cl.nombre, cl.direccion, cl.idtipdoc, cl.numdoc,
                        cl.email, cl.telfijo, cl.telcel, cl.telofi,
                        cl.sexo AS gen, cl.idestcivil AS estc,
                        cl.natper, cl.conyuge, cl.nacionalidad,
                        cl.idprofesion, cl.detaprofesion,
                        cl.idcargoprofe, cl.profocupa, cl.dirfer,
                        cl.idubigeo, cl.cumpclie AS fechanaci,
                        cl.razonsocial, cl.domfiscal,
                        cl.fechaconstitu, cl.idsedereg, cl.numpartida,
                        cl.telempresa, cl.mailempresa
                    FROM contratantesxacto cx
                    LEFT JOIN cliente2 cl ON cx.idcontratante = cl.idcontratante
                    WHERE cx.kardex = %s
                """
                cursor.execute(query, [kardex])
                columns = [col[0] for col in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except Exception as e:
            self.logger.error(f"Error getting participants for kardex {kardex}: {str(e)}")
            return []
    
    def _execute_search_query(self, filters: Dict) -> List[Dict]:
        """Execute raw SQL query with proper parameterization"""
        query, params = self._build_sql_query(filters)
        
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                columns = [col[0] for col in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except Exception as e:
            self.logger.error(f"Database query error: {str(e)}")
            raise DocumentSearchException(f"Database query failed: {str(e)}")
    
    def _build_sql_query(self, filters: Dict) -> Tuple[str, List]:
        """Build parameterized SQL query"""
        # Base query with proper date handling and notary data
        base_query = """
            SELECT k.idkardex, k.kardex, k.numescritura, k.fechaescritura,
                   IF(ta.cod_ancert IS NULL,'',ta.cod_ancert) AS cod_ancert,
                   k.estado_sisgen, k.idtipkar, k.fechaingreso, k.codactos,
                   k.contrato, k.folioini, k.foliofin, k.fechaconclusion,
                   ta.actouif, ta.actosunat,
                   ta.mediospago, ta.cuantia, ta.origenfondo, ta.impuestorenta,
                   IFNULL(ta.desacto, '') AS desacto,
                   -- Add notary data
                   cn.codnotario, cn.codoficial, cn.coduif,
                   CONCAT(cn.nombre, ' ', cn.apellido) as nombre_notario,
                   cn.direccion as direccion_notario,
                   cn.distrito as distrito_notario,
                   cn.provincia as provincia_notario,
                   cn.departamento as departamento_notario
            FROM kardex k
            LEFT JOIN tiposdeacto ta ON SUBSTRING(k.codactos,1,3) = ta.idtipoacto
            -- Join with confinotario to get notary data
            LEFT JOIN confinotario cn ON 1=1
            WHERE 1=1
        """
        
        params = []
        conditions = []
        
        # Debug incoming filters
        self.logger.debug(f"Building query with filters: {filters}")
        
        # Date range (ver _reference_date_in_range_sql)
        if filters.get('fechaDesde') and filters.get('fechaHasta'):
            ds, ps = self._reference_date_in_range_sql(
                filters["fechaDesde"], filters["fechaHasta"]
            )
            conditions.append(ds)
            params.extend(ps)
            self.logger.debug(f"Date range: {filters['fechaDesde']} to {filters['fechaHasta']}")
        
        # Instrument type
        if filters.get('tipoInstrumento'):
            conditions.append("k.idtipkar = %s")
            params.append(filters['tipoInstrumento'])
            self.logger.debug(f"Instrument type: {filters['tipoInstrumento']}")
        
        # Status filter - handle -1 as special case for all documents
        estado = filters.get('estado')
        self.logger.debug(f"Estado filter: {estado}")
        
        if estado == 4:
            conditions.append("(ta.cod_ancert = '' OR ta.cod_ancert IS NULL)")
        elif estado == 0:
            conditions.append("k.estado_sisgen = %s")
            params.append(estado)
        elif estado == 3:
            conditions.append("k.estado_sisgen = '3'")
        elif estado != 5 and estado != -1 and estado is not None:  # Modified to handle -1
            conditions.append("k.estado_sisgen = %s")
            params.append(estado)
        # Note: estado = -1 means no filter, similar to estado = 5
        
        # Act code
        if filters.get('codigoActo') and filters['codigoActo'] != 0:
            conditions.append("ta.idtipoacto = %s")
            params.append(filters['codigoActo'])
            self.logger.debug(f"Act code: {filters['codigoActo']}")
        
        # Basic filters
        conditions.extend([
            "k.numescritura <> ''",
            "k.kardex <> ''",
            # Ensure notary data is complete
            "cn.codnotario IS NOT NULL",
            "cn.codoficial IS NOT NULL",
            "cn.coduif IS NOT NULL",
            "cn.nombre IS NOT NULL",
            "cn.apellido IS NOT NULL",
            "cn.direccion IS NOT NULL",
            "cn.distrito IS NOT NULL"
        ])
        
        # Add conditions to query
        if conditions:
            base_query += " AND " + " AND ".join(conditions)
        
        base_query += (
            " ORDER BY CAST(NULLIF(TRIM(k.numescritura), '') AS UNSIGNED), k.kardex"
        )
        
        self.logger.debug(f"Final SQL Query: {base_query}")
        self.logger.debug(f"SQL Params: {params}")
        
        return base_query, params
    
    def _validate_pdt_data(self, documents: List[Dict]):
        """Validate PDT data for documents based on their tipkar"""
        try:
            # Group documents by tipkar
            docs_by_tipkar = {
                1: [],  # escrituras
                3: [],  # vehiculares
                4: []   # garantias
            }
            
            # Reset PDT errors
            self.pdt_errors = {}
            
            # Group documents and get date range
            min_date = None
            max_date = None
            for doc in documents:
                kardex = doc.get('kardex', '')
                self.pdt_errors[kardex] = []
                
                tipkar = doc.get('idtipkar')
                if tipkar in docs_by_tipkar:
                    docs_by_tipkar[tipkar].append(doc)
                    
                    # Track date range
                    fecha_concl = doc.get('fechaconclusion')
                    if fecha_concl:
                        try:
                            fecha_dt = datetime.strptime(fecha_concl, '%d/%m/%Y')
                            if min_date is None or fecha_dt < min_date:
                                min_date = fecha_dt
                            if max_date is None or fecha_dt > max_date:
                                max_date = fecha_dt
                        except ValueError:
                            self.logger.warning(f"Invalid date format for kardex {kardex}: {fecha_concl}")
            
            if not min_date or not max_date:
                self.logger.warning("No valid dates found for PDT validation")
                return
                
            # Format dates for PDT services
            start_date = min_date.strftime('%d/%m/%Y')
            end_date = max_date.strftime('%d/%m/%Y')
            
            # Validate escrituras
            if docs_by_tipkar[1]:
                self.pdt_escrituras = PdtEscriturasService(start_date, end_date)
                self.pdt_escrituras.load_data()
                escrituras_results = self.pdt_escrituras.get_results()
                self._process_pdt_results(escrituras_results, docs_by_tipkar[1])
            
            # Validate vehiculares
            if docs_by_tipkar[3]:
                self.pdt_vehiculares = PdtVehicularesService(start_date, end_date)
                self.pdt_vehiculares.load_data()
                vehiculares_results = self.pdt_vehiculares.get_results()
                self._process_pdt_results(vehiculares_results, docs_by_tipkar[3])
            
            # Validate garantias
            if docs_by_tipkar[4]:
                self.pdt_garantias = PdtGarantiasService(start_date, end_date)
                self.pdt_garantias.load_data()
                garantias_results = self.pdt_garantias.get_results()
                self._process_pdt_results(garantias_results, docs_by_tipkar[4])
                
        except Exception as e:
            self.logger.error(f"Error in PDT validation: {str(e)}")
            
    def _process_pdt_results(self, results: Dict, documents: List[Dict]):
        """Process PDT validation results and add errors to documents"""
        if not results or 'list' not in results:
            return
            
        # Create lookup of errors by kardex
        errors_by_kardex = {}
        for error in results['list']:
            kardex = error.get('kardex')
            if kardex:
                if kardex not in errors_by_kardex:
                    errors_by_kardex[kardex] = []
                errors_by_kardex[kardex].append(error['errorItem'])
        
        # Add errors to documents
        for doc in documents:
            kardex = doc.get('kardex')
            if kardex in errors_by_kardex:
                self.pdt_errors[kardex].extend(errors_by_kardex[kardex])

    def _process_documents(self, documents: List[Dict], filters: Dict) -> List[Dict]:
        """Process and format document results"""
        processed = []
        
        # Debug log before processing
        self.logger.debug(f"Processing {len(documents)} documents")
        self.logger.debug(f"Current error state:")
        self.logger.debug(f"Kardex errors: {self.kardex_errors}")
        self.logger.debug(f"Kardex observations: {self.kardex_observations}")
        self.logger.debug(f"Person errors: {self.person_errors}")
        
        # Get all kardex numbers for bulk validation
        kardex_numbers = [doc.get('kardex', '') for doc in documents]
        
        # Bulk validate UIF data
        uif_validation_results = self.uif_validator.bulk_validate_kardex(kardex_numbers)
        
        for doc in documents:
            kardex = doc.get('kardex', '')
            processed_doc = self._format_single_document(doc, uif_validation_results.get(kardex))
            processed.append(processed_doc)
        
        # Handle special case for estado = 5 (all documents)
        if filters.get('estado') == 5:
            processed = self._handle_all_documents_case(processed)
        
        return processed

    def _format_single_document(self, doc: Dict, uif_validation: Optional[Dict] = None) -> Dict:
        """Format a single document"""
        kardex = doc.get('kardex', '')
        
        # Debug log for this specific kardex
        self.logger.debug(f"Formatting document for kardex: {kardex}")
        self.logger.debug(f"Available errors for this kardex: {self.kardex_errors.get(kardex, [])}")
        self.logger.debug(f"Available observations for this kardex: {self.kardex_observations.get(kardex, [])}")
        self.logger.debug(f"Available person errors for this kardex: {self.person_errors.get(kardex, [])}")
        self.logger.debug(f"Available PDT errors for this kardex: {self.pdt_errors.get(kardex, [])}")
        
        # Format date safely
        fecha_escritura = doc['fechaescritura']
        fecha_formatted = self._format_date_safely(fecha_escritura)
        
        # Get estado display
        estado_code = self._normalize_estado_sisgen_code(doc["estado_sisgen"])
        estado_display = self._get_estado_display(doc["estado_sisgen"])
        
        # Use provided UIF validation or get empty result
        if uif_validation is None:
            uif_validation = {
                'has_uif_errors': False,
                'uif_errors': [],
                'uif_observations': [],
                'patrimonial_data': {}
            }
        
        # Format document data
        formatted_doc = {
            'idkardex': doc['idkardex'],
            'kardex': kardex,
            'numescritura': doc['numescritura'],
            'fechaescritura': fecha_formatted,
            'estado_sisgen': estado_display,
            'estado_sisgen_code': estado_code if estado_code is not None else 0,
            'idtipkar': doc['idtipkar'],
            'fechaingreso': self._format_datetime_safely(doc['fechaingreso']),
            'codactos': doc['codactos'],
            'contrato': doc['contrato'],
            'folioini': doc['folioini'],
            'foliofin': doc['foliofin'],
            'fechaconclusion': self._format_date_safely(doc['fechaconclusion']),
            'cod_ancert': doc['cod_ancert'] or '',
            'actouif': doc['actouif'] or '',
            'actosunat': doc['actosunat'] or '',
            'desacto': doc.get('desacto') or '',
            'notary_data': {
                'codnotario': doc['codnotario'],
                'codoficial': doc['codoficial'],
                'coduif': doc['coduif'],
                'nombre_notario': doc['nombre_notario'],
                'direccion': doc['direccion_notario'],
                'distrito': doc['distrito_notario'],
                'provincia': doc.get('provincia_notario', ''),
                'departamento': doc.get('departamento_notario', '')
            },
            # Add SISGEN error tracking for this kardex
            'errores': self.kardex_errors.get(kardex, []),
            'observaciones': self.kardex_observations.get(kardex, []),
            'personas': self.person_errors.get(kardex, []),
            # Add UIF validation results
            'uif_validation': {
                'has_errors': uif_validation['has_uif_errors'],
                'errors': uif_validation['uif_errors'],
                'observations': uif_validation['uif_observations'],
                'patrimonial_data': uif_validation['patrimonial_data']
            },
            # Add PDT validation results
            'pdt_validation': {
                'has_errors': bool(self.pdt_errors.get(kardex, [])),
                'errors': self.pdt_errors.get(kardex, [])
            }
        }
        
        return formatted_doc
    
    def _format_date_safely(self, date_value) -> str:
        """Safely format date values"""
        if date_value is None:
            return ''
        
        try:
            if isinstance(date_value, str):
                # Try to parse the date string
                for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y']:
                    try:
                        date_obj = datetime.strptime(date_value, fmt)
                        return date_obj.strftime('%d/%m/%Y')
                    except ValueError:
                        continue
                return date_value
            elif hasattr(date_value, 'strftime'):
                return date_value.strftime('%d/%m/%Y')
            else:
                return str(date_value)
        except Exception:
            return str(date_value)
    
    def _format_datetime_safely(self, datetime_value) -> str:
        """Safely format datetime values"""
        if datetime_value is None:
            return ''
        
        try:
            if hasattr(datetime_value, 'isoformat'):
                return datetime_value.isoformat()
            else:
                return str(datetime_value)
        except Exception:
            return str(datetime_value)
    
    @staticmethod
    def _numescritura_int(val) -> Optional[int]:
        """DB suele devolver numescritura como str ('03'); necesario para huecos en estado=5."""
        if val is None:
            return None
        s = "".join(c for c in str(val).strip() if c.isdigit())
        if not s:
            return None
        try:
            return int(s)
        except ValueError:
            return None

    def _handle_all_documents_case(self, documents: List[Dict]) -> List[Dict]:
        """Handle special case for estado = 5 (huecos entre números de escritura)."""
        if not documents:
            return documents

        processed: List[Dict] = []
        prev_int: Optional[int] = None

        for i, doc in enumerate(documents):
            cur_int = self._numescritura_int(doc.get("numescritura"))

            if (
                prev_int is not None
                and cur_int is not None
                and cur_int != prev_int + 1
            ):
                gap = prev_int + 1
                processed.append(
                    {
                        "numescritura": str(gap),
                        "idkardex": "",
                        "kardex": "",
                        "idtipkar": "",
                        "fechaingreso": "",
                        "fechaescritura": "",
                        "cod_ancert": f"-10--{i}",
                        "folioini": "",
                        "fechaconclusion": "",
                        "codactos": "",
                        "contrato": "",
                        "estado_sisgen": "-1",
                        "actouif": "",
                        "actosunat": "",
                        "notary_data": {},
                    }
                )

            processed.append(doc)
            if cur_int is not None:
                prev_int = cur_int

        return processed
    
    @staticmethod
    def _normalize_estado_sisgen_code(estado) -> Optional[int]:
        """
        Unifica tipos que vienen de MySQL/cursors: '', Decimal, str '0', bytes, etc.

        Cadena vacía: en muchos legados el campo queda '' pero el filtro SQL
        ``estado_sisgen = 0`` igual los devuelve por coerción MySQL; en Python
        ``int('')`` fallaba y la UI mostraba «Desconocido».
        """
        if estado is None:
            return None
        if isinstance(estado, bytes):
            estado = estado.decode("utf-8", errors="ignore").strip()
        if isinstance(estado, Decimal):
            try:
                return int(estado)
            except (ValueError, OverflowError, ArithmeticError):
                return None
        if isinstance(estado, float):
            if estado != estado:  # NaN
                return None
            try:
                return int(estado)
            except ValueError:
                return None
        if isinstance(estado, str):
            s = estado.strip()
            if s == "":
                return 0
            if s.upper() in {"NULL", "NONE", "-"}:
                return None
            try:
                return int(float(s)) if "." in s else int(s)
            except ValueError:
                return None
        try:
            return int(estado)
        except (TypeError, ValueError):
            return None

    def _get_estado_display(self, estado) -> str:
        """Etiqueta para UI según código numérico en kardex.estado_sisgen."""
        key = self._normalize_estado_sisgen_code(estado)
        if key is None:
            return "Sin estado SISGEN"
        label = ESTADO_SISGEN_MAPPING.get(key)
        if label is not None:
            return label
        return f"Código {key} (sin etiqueta)"

    def _generate_debug_xml(self, data: List[Dict], error_details: Dict, filters: Dict):
        """Generate XML file for debugging"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            xml = ['<?xml version="1.0" encoding="UTF-8"?>']
            xml.append('<SISGENResponse>')
            
            # Add request info
            xml.append('  <RequestInfo>')
            xml.append(f'    <Timestamp>{datetime.now().isoformat()}</Timestamp>')
            xml.append('    <Filters>')
            for key, value in filters.items():
                xml.append(f'      <Filter name="{key}">{value}</Filter>')
            xml.append('    </Filters>')
            xml.append('  </RequestInfo>')
            
            # Add error details
            xml.append('  <ErrorDetails>')
            for kardex, errors in error_details.items():
                xml.append(f'    <Kardex id="{kardex}">')
                for error_type, errors_list in errors.items():
                    for error in errors_list:
                        xml.append(f'      <{error_type}>{error}</{error_type}>')
                xml.append('    </Kardex>')
            xml.append('  </ErrorDetails>')
            
            # Add document data
            xml.append('  <Documents>')
            for doc in data:
                xml.append('    <Document>')
                self._add_xml_element(doc, xml, indent=6)
                xml.append('    </Document>')
            xml.append('  </Documents>')
            
            xml.append('</SISGENResponse>')
            
            # Write to file
            with open('response-search.xml', 'w', encoding='utf-8') as f:
                f.write('\n'.join(xml))
            
            self.logger.info("Generated debug XML response file: response-search.xml")
            
        except Exception as e:
            self.logger.error(f"Error generating debug XML: {str(e)}")

    def _generate_error_xml(self, error_type: str, error_message: str, filters: Dict):
        """Generate XML file for errors"""
        try:
            xml = ['<?xml version="1.0" encoding="UTF-8"?>']
            xml.append('<SISGENError>')
            
            # Add error info
            xml.append('  <ErrorInfo>')
            xml.append(f'    <Timestamp>{datetime.now().isoformat()}</Timestamp>')
            xml.append(f'    <Type>{error_type}</Type>')
            xml.append(f'    <Message>{error_message}</Message>')
            xml.append('  </ErrorInfo>')
            
            # Add request info
            xml.append('  <RequestInfo>')
            xml.append('    <Filters>')
            for key, value in filters.items():
                xml.append(f'      <Filter name="{key}">{value}</Filter>')
            xml.append('    </Filters>')
            xml.append('  </RequestInfo>')
            
            # Add error tracking details
            xml.append('  <ErrorTracking>')
            for kardex, errors in self.kardex_errors.items():
                for error in errors:
                    xml.append(f'    <KardexError kardex="{kardex}">{error}</KardexError>')
            for kardex, observations in self.kardex_observations.items():
                for obs in observations:
                    xml.append(f'    <Observation kardex="{kardex}">{obs}</Observation>')
            for kardex, person_errors in self.person_errors.items():
                for error in person_errors:
                    xml.append(f'    <PersonError kardex="{kardex}">{error}</PersonError>')
            xml.append('  </ErrorTracking>')
            
            xml.append('</SISGENError>')
            
            # Write to file
            with open('response-search.xml', 'w', encoding='utf-8') as f:
                f.write('\n'.join(xml))
            
            self.logger.info("Generated error XML response file: response-search.xml")
            
        except Exception as e:
            self.logger.error(f"Error generating error XML: {str(e)}")

    def _add_xml_element(self, data: Dict, xml: List[str], indent: int = 0):
        """Helper to add nested XML elements"""
        spaces = ' ' * indent
        for key, value in data.items():
            if isinstance(value, dict):
                xml.append(f'{spaces}<{key}>')
                self._add_xml_element(value, xml, indent + 2)
                xml.append(f'{spaces}</{key}>')
            else:
                if value is not None:
                    # Escape special characters
                    if isinstance(value, str):
                        value = value.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                    xml.append(f'{spaces}<{key}>{value}</{key}>')