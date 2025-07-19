"""
This module contains the document search service for the sisgen service.
"""

from typing import Dict, List, Tuple
import logging
from django.db import connection
from ..utils.exceptions import DocumentSearchException, ValidationException
from ..utils.validators import SearchFiltersValidator
from ..utils.constants import ESTADO_SISGEN_MAPPING, ERROR_MESSAGES

logger = logging.getLogger(__name__)

class DocumentSearchService:
    def __init__(self):
        self.logger = logger
        self.validator = SearchFiltersValidator()
    
    def search_documents(self, filters: Dict) -> Tuple[List[Dict], int, List[str]]:
        """
        Search for notarial documents
        Returns: (data, total_count, errors)
        """
        try:
            # Validate filters
            validated_filters = self.validator.validate(filters)
            
            # Build and execute query
            documents = self._execute_search_query(validated_filters)
            
            # Process results
            processed_data = self._process_documents(documents, validated_filters)
            
            self.logger.info(f"Found {len(processed_data)} documents")
            return processed_data, len(processed_data), []
            
        except ValidationException as e:
            self.logger.error(f"Validation error: {str(e)}")
            return [], 0, [str(e)]
        except DocumentSearchException as e:
            self.logger.error(f"Document search error: {str(e)}")
            return [], 0, [str(e)]
        except Exception as e:
            self.logger.error(f"Unexpected error in document search: {str(e)}")
            return [], 0, [ERROR_MESSAGES['DATABASE_ERROR'].format(error=str(e))]

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
        # Base query with proper date handling
        base_query = """
            SELECT k.idkardex, k.kardex, k.numescritura, k.fechaescritura,
                   IF(ta.cod_ancert IS NULL,'',ta.cod_ancert) AS cod_ancert,
                   k.estado_sisgen, k.idtipkar, k.fechaingreso, k.codactos,
                   k.contrato, k.folioini, k.foliofin, k.fechaconclusion,
                   ta.actouif, ta.actosunat
            FROM kardex k
            LEFT JOIN tiposdeacto ta ON SUBSTRING(k.codactos,1,3) = ta.idtipoacto
            WHERE 1=1
        """
        
        params = []
        conditions = []
        
        # Date range - use proper date formatting
        if filters.get('fechaDesde') and filters.get('fechaHasta'):
            conditions.append("DATE(k.fechaescritura) BETWEEN %s AND %s")
            params.extend([filters['fechaDesde'], filters['fechaHasta']])
        
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
        elif estado != 5 and estado is not None:
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
        
        # Add conditions to query
        if conditions:
            base_query += " AND " + " AND ".join(conditions)
        
        base_query += " ORDER BY CAST(k.numescritura AS UNSIGNED)"
        
        self.logger.debug(f"SQL Query: {base_query}")
        self.logger.debug(f"SQL Params: {params}")
        
        return base_query, params
    
    def _process_documents(self, documents: List[Dict], filters: Dict) -> List[Dict]:
        """Process and format document results"""
        processed = []
        
        for doc in documents:
            processed_doc = self._format_single_document(doc)
            processed.append(processed_doc)
        
        # Handle special case for estado = 5 (all documents)
        if filters.get('estado') == 5:
            processed = self._handle_all_documents_case(processed)
        
        return processed
    
    def _format_single_document(self, doc: Dict) -> Dict:
        """Format a single document"""
        # Format date safely
        fecha_escritura = doc['fechaescritura']
        fecha_formatted = self._format_date_safely(fecha_escritura)
        
        # Get estado display
        estado_display = self._get_estado_display(doc['estado_sisgen'])
        
        return {
            'idkardex': doc['idkardex'],
            'kardex': doc['kardex'],
            'numescritura': doc['numescritura'],
            'fechaescritura': fecha_formatted,
            'estado_sisgen': estado_display,
            'idtipkar': doc['idtipkar'],
            'fechaingreso': self._format_datetime_safely(doc['fechaingreso']),
            'codactos': doc['codactos'],
            'contrato': doc['contrato'],
            'folioini': doc['folioini'],
            'foliofin': doc['foliofin'],
            'fechaconclusion': self._format_date_safely(doc['fechaconclusion']),
            'cod_ancert': doc['cod_ancert'] or '',
            'actouif': doc['actouif'] or '',
            'actosunat': doc['actosunat'] or ''
        }
    
    def _format_date_safely(self, date_value) -> str:
        """Safely format date values"""
        if date_value is None:
            return ''
        
        try:
            if isinstance(date_value, str):
                # Try to parse the date string
                from datetime import datetime
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
    
    def _handle_all_documents_case(self, documents: List[Dict]) -> List[Dict]:
        """Handle special case for estado = 5"""
        if not documents:
            return documents
        
        processed = []
        prev_num = None
        
        for i, doc in enumerate(documents):
            current_num = doc['numescritura']
            
            if prev_num is not None and current_num != prev_num + 1:
                # Add gap document
                processed.append({
                    'numescritura': prev_num + 1,
                    'idkardex': '',
                    'kardex': '',
                    'idtipkar': '',
                    'fechaingreso': '',
                    'fechaescritura': '',
                    'cod_ancert': f'-10--{i}',
                    'folioini': '',
                    'fechaconclusion': '',
                    'codactos': '',
                    'contrato': '',
                    'estado_sisgen': '-1',
                    'actouif': '',
                    'actosunat': ''
                })
            
            processed.append(doc)
            prev_num = current_num
        
        return processed
    
    def _get_estado_display(self, estado: int) -> str:
        """Get display text for estado_sisgen"""
        return ESTADO_SISGEN_MAPPING.get(estado, 'Desconocido')