"""
This module contains the book search service for the sisgen service.
"""

from typing import Dict, List, Tuple, Optional
import logging
import math
from datetime import datetime
from django.db import connection
from ..utils.exceptions import DocumentSearchException, ValidationException
from ..utils.constants import ESTADO_SISGEN_MAPPING

logger = logging.getLogger(__name__)

class BookSearchService:
    def __init__(self):
        self.logger = logger
        # Initialize error tracking
        self.book_errors = {}  # {book_id: [errors]}
        self.book_observations = {}  # {book_id: [observations]}
        self.pdt_errors = {}  # {book_id: [pdt_errors]}
        # Initialize batch processing state
        self.search_id = None
        self.all_book_ids = []  # Store all book IDs in order
        self.processed_book_ids = set()
        self.total_books = 0
        self.validated_filters = None
        self.current_page = 1
        self.batch_size = 10  # Fixed batch size
        
    @classmethod
    def from_session_data(cls, session_data: Dict) -> 'BookSearchService':
        """Create service instance from session data"""
        service = cls()
        service.search_id = session_data.get('search_id')
        service.all_book_ids = session_data.get('all_book_ids', [])
        service.processed_book_ids = set(session_data.get('processed_book_ids', []))
        service.total_books = session_data.get('total_books', 0)
        service.validated_filters = session_data.get('validated_filters')
        service.current_page = session_data.get('current_page', 1)
        return service

    def get_session_data(self) -> Dict:
        """Get serializable session data"""
        return {
            'search_id': self.search_id,
            'all_book_ids': self.all_book_ids,
            'processed_book_ids': list(self.processed_book_ids),
            'total_books': self.total_books,
            'validated_filters': self.validated_filters,
            'current_page': self.current_page
        }

    def initialize_search(self, filters: Dict) -> Dict:
        """Initialize a new search session"""
        try:
            # Reset error tracking lists and state
            self.book_errors = {}
            self.book_observations = {}
            self.pdt_errors = {} # Reset PDT errors
            self.current_page = 1
            
            # Log incoming filters
            self.logger.info(f"Book search request with filters: {filters}")
            
            # Store validated filters
            self.validated_filters = filters
            
            # Get initial book list (only IDs)
            with connection.cursor() as cursor:
                # First get the ID column name
                id_column = self._get_book_id_column()
                
                query = f"""
                    SELECT l.{id_column} as id
                    FROM libros l
                    LEFT JOIN tipolibro tl ON tl.idtiplib = l.idtiplib
                    WHERE 1=1
                """
                conditions, params = self._build_filter_conditions(filters)
                if conditions:
                    query += " AND " + " AND ".join(conditions)
                query += f" ORDER BY l.{id_column}"
                
                cursor.execute(query, params)
                books = cursor.fetchall()
            
            # Generate unique search ID and store state
            self.search_id = f"search_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(books)}"
            self.total_books = len(books)
            self.all_book_ids = [book[0] for book in books]  # Store all book IDs in order
            self.processed_book_ids = set()
            
            # Handle empty results case
            if self.total_books == 0:
                return {
                    'search_id': self.search_id,
                    'total_documents': 0,
                    'processed': 0,
                    'current_page': 1,
                    'total_pages': 1,  # At least one page even when empty
                    'has_next': False,
                    'has_previous': False,
                    'message': 'No se encontraron libros que coincidan con los criterios de búsqueda.'
                }
            
            return {
                'search_id': self.search_id,
                'total_documents': self.total_books,
                'processed': 0,
                'current_page': 1,
                'total_pages': math.ceil(self.total_books / self.batch_size),
                'has_next': self.total_books > self.batch_size,
                'has_previous': False
            }
            
        except Exception as e:
            self.logger.error(f"Error initializing search: {str(e)}")
            raise DocumentSearchException(f"Failed to initialize search: {str(e)}")

    def get_page(self, search_id: str, page: int = 1) -> Tuple[List[Dict], Dict, Dict]:
        """Get specific page of books"""
        if search_id != self.search_id:
            raise DocumentSearchException("Invalid search session")
            
        try:
            # Handle no results case
            if self.total_books == 0:
                return [], self._get_error_details(), {
                    'search_id': self.search_id,
                    'total_documents': 0,
                    'processed': 0,
                    'current_page': 1,
                    'total_pages': 1,  # At least one page even when empty
                    'has_next': False,
                    'has_previous': False,
                    'page_size': self.batch_size,
                    'message': 'No se encontraron libros que coincidan con los criterios de búsqueda.'
                }
            
            # Calculate page bounds
            total_pages = math.ceil(self.total_books / self.batch_size)
            if page < 1 or page > total_pages:
                raise DocumentSearchException(f"Invalid page number. Must be between 1 and {total_pages}")
            
            # Calculate slice indices
            start_idx = (page - 1) * self.batch_size
            end_idx = min(start_idx + self.batch_size, self.total_books)
            
            # Get book IDs for this page
            page_book_ids = self.all_book_ids[start_idx:end_idx]
            
            # Get full book data for this page
            books = self._execute_batch_query(page_book_ids)
            
            # Process books
            processed_data = self._process_books(books)
            
            # Update tracking
            self.processed_book_ids.update(page_book_ids)
            self.current_page = page
            
            # Get error details and status
            error_details = self._get_error_details()
            page_status = self._get_page_status()
            
            # Clear and update temporary table
            self._clear_temp_table()
            self._insert_temp_records(processed_data)
            
            return processed_data, error_details, page_status
            
        except Exception as e:
            self.logger.error(f"Error getting page {page}: {str(e)}")
            raise DocumentSearchException(f"Failed to get page: {str(e)}")

    def _get_page_status(self) -> Dict:
        """Get current page status"""
        total_pages = math.ceil(self.total_books / self.batch_size)
        return {
            'search_id': self.search_id,
            'total_documents': self.total_books,
            'processed': len(self.processed_book_ids),
            'current_page': self.current_page,
            'total_pages': total_pages,
            'has_next': self.current_page < total_pages,
            'has_previous': self.current_page > 1,
            'page_size': self.batch_size
        }

    def search_books(self, filters: Dict) -> Tuple[List[Dict], int, List[str], Dict]:
        """
        Search for books based on filters
        Returns: (data, total_count, errors, error_details)
        error_details contains: {
            'book_errors': List of book-level errors,
            'observations': List of observations/warnings
        }
        """
        try:
            # Initialize search
            status = self.initialize_search(filters)
            
            # Get first page
            data, error_details, page_status = self.get_page(status['search_id'], 1)
            
            return data, len(data), [], error_details
            
        except Exception as e:
            self.logger.error(f"Unexpected error in book search: {str(e)}")
            return [], 0, [str(e)], self._get_error_details()

    def _execute_batch_query(self, book_ids: List[str]) -> List[Dict]:
        """Execute query for a batch of book IDs"""
        # First get the ID column name
        id_column = self._get_book_id_column()
        
        query = f"""
            SELECT 
                l.{id_column} as id,
                CONCAT(l.numlibro, '-', l.ano) as libro,
                l.fecing AS fechaIngreso,
                l.tipper AS tipoPersona,
                IF(l.tipper = 'N', 
                   CONCAT(l.prinom, ' ', l.segnom, ' ', l.apepat, ' ', l.apemat),
                   l.empresa) AS empresa,
                l.ruc,
                l.domfiscal,
                l.idtiplib,
                l.descritiplib AS descripcionTipoLibro,
                IF(l.idtiplib = 99, l.descritiplib, tl.destiplib) as descripcionLibro,
                IF(l.estadoSisgen IS NULL, 0, l.estadoSisgen) as estadoSisgen
            FROM libros l
            LEFT JOIN tipolibro tl ON tl.idtiplib = l.idtiplib
            WHERE l.{id_column} IN %s
            ORDER BY l.{id_column}
        """
        
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, [tuple(book_ids)])
                columns = [col[0] for col in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except Exception as e:
            self.logger.error(f"Database query error: {str(e)}")
            raise DocumentSearchException(f"Database query failed: {str(e)}")

    def _execute_search_query(self, filters: Dict) -> List[Dict]:
        """Execute book search query"""
        query, params = self._build_sql_query(filters)
        
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                columns = [col[0] for col in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except Exception as e:
            self.logger.error(f"Database query error: {str(e)}")
            raise DocumentSearchException(f"Database query failed: {str(e)}")

    def _build_filter_conditions(self, filters: Dict) -> Tuple[List[str], List]:
        """Build filter conditions for book search"""
        conditions = []
        params = []
        
        # Date range filter
        if filters.get('fechaDesde') and filters.get('fechaHasta'):
            conditions.append("l.fecing BETWEEN %s AND %s")
            params.extend([filters['fechaDesde'], filters['fechaHasta']])
        
        # Status filter - handle -1 as special case for all books
        estado = filters.get('estado')
        if estado == 0:  # Changed from '0' to 0
            conditions.append("(l.estadoSisgen = 0 OR l.estadoSisgen IS NULL)")
        elif estado == 3:  # Changed from '3' to 3
            conditions.append("l.estadoSisgen = '3'")
        elif estado != -1 and estado is not None:  # Changed from '-1' to -1
            conditions.append("l.estadoSisgen = %s")
            params.append(estado)
        
        return conditions, params

    def _build_sql_query(self, filters: Dict) -> Tuple[str, List]:
        """Build SQL query for book search"""
        # First get the ID column name
        id_column = self._get_book_id_column()
        
        base_query = f"""
            SELECT 
                l.{id_column} as id,
                CONCAT(l.numlibro, '-', l.ano) as libro,
                l.fecing AS fechaIngreso,
                l.tipper AS tipoPersona,
                IF(l.tipper = 'N', 
                   CONCAT(l.prinom, ' ', l.segnom, ' ', l.apepat, ' ', l.apemat),
                   l.empresa) AS empresa,
                l.ruc,
                l.domfiscal,
                l.idtiplib,
                l.descritiplib AS descripcionTipoLibro,
                IF(l.idtiplib = 99, l.descritiplib, tl.destiplib) as descripcionLibro,
                IF(l.estadoSisgen IS NULL, 0, l.estadoSisgen) as estadoSisgen
            FROM libros l
            LEFT JOIN tipolibro tl ON tl.idtiplib = l.idtiplib
            WHERE 1=1
        """
        
        conditions, params = self._build_filter_conditions(filters)
        
        # Add conditions to query
        if conditions:
            base_query += " AND " + " AND ".join(conditions)
        
        # Add ordering
        base_query += f" ORDER BY l.{id_column}"
        
        return base_query, params

    def _get_book_id_column(self) -> str:
        """Determine the ID column name for the books table"""
        try:
            with connection.cursor() as cursor:
                cursor.execute("SHOW COLUMNS FROM libros")
                columns = cursor.fetchall()
                for column in columns:
                    if column[0] in ('id', 'idLibro', 'idLibros'):
                        return column[0]
                return 'id'  # Default to 'id' if no match found
        except Exception as e:
            self.logger.error(f"Error getting book ID column: {str(e)}")
            return 'id'

    def _process_books(self, books: List[Dict]) -> List[Dict]:
        """Process and format book results"""
        processed = []
        
        for book in books:
            # Reset error tracking for this book
            book_id = str(book['id'])
            self.book_errors[book_id] = []
            self.book_observations[book_id] = []
            self.pdt_errors[book_id] = [] # Reset PDT errors for each book
            
            # Validate book data
            self._validate_book_data(book)
            
            # Format and add to processed list
            processed_book = self._format_single_book(book)
            processed.append(processed_book)
        
        return processed
        
    def _validate_book_data(self, book: Dict):
        """Validate book data and track errors"""
        book_id = str(book['id'])
        
        # Reset PDT errors for this book
        if book_id not in self.pdt_errors:
            self.pdt_errors[book_id] = []
        
        # Validate required fields for all books
        required_fields = ['libro', 'fechaIngreso', 'idtiplib', 'descripcionTipoLibro']
        for field in required_fields:
            if not book.get(field):
                self._add_error(book_id, f"Falta campo requerido: {field}")
        
        # Validate based on person type
        if book['tipoPersona'] == 'N':  # Natural person
            if not book.get('empresa'):  # empresa contains the concatenated person name
                self._add_error(book_id, "Falta nombre de persona natural")
        else:  # Juridical person
            if not book.get('ruc'):
                self._add_error(book_id, "Falta RUC")
            elif len(str(book['ruc'])) != 11:
                self._add_error(book_id, "RUC inválido")
            if not book.get('empresa'):
                self._add_error(book_id, "Falta razón social")
        
        # Validate address
        if not book.get('domfiscal'):
            self._add_observation(book_id, "Falta domicilio fiscal")
        
        # Validate SISGEN status
        estado_sisgen = book.get('estadoSisgen')
        if estado_sisgen is None or estado_sisgen == 0:
            self._add_error(book_id, "Libro no enviado a SISGEN")
        elif estado_sisgen == 3:
            self._add_error(book_id, "Error en envío a SISGEN")

        # PDT Validation
        self._validate_pdt_data(book)

    def _validate_pdt_data(self, book: Dict):
        """Validate PDT-specific requirements"""
        book_id = str(book['id'])
        
        # Check for solicitante
        if not book.get('solicitante'):
            self._add_pdt_error(book_id, "Falta nombre del solicitante")
        
        # Check for document numbers
        dni = book.get('dni')
        ruc = book.get('ruc')
        numdoc_plantilla = book.get('numdoc_plantilla')
        if not dni and not ruc and not numdoc_plantilla:
            self._add_pdt_error(book_id, "Falta documento de identidad (DNI/RUC)")
        
        # Check for empresa name if RUC exists
        if ruc and not book.get('empresa'):
            self._add_pdt_error(book_id, "Falta nombre de empresa para RUC")

    def _add_error(self, book_id: str, error: str):
        """Add error for a specific book"""
        if book_id not in self.book_errors:
            self.book_errors[book_id] = []
        self.book_errors[book_id].append(error)
    
    def _add_observation(self, book_id: str, observation: str):
        """Add observation for a specific book"""
        if book_id not in self.book_observations:
            self.book_observations[book_id] = []
        self.book_observations[book_id].append(observation)

    def _add_pdt_error(self, book_id: str, error: str):
        """Add PDT error for a specific book"""
        if book_id not in self.pdt_errors:
            self.pdt_errors[book_id] = []
        self.pdt_errors[book_id].append(error)

    def _format_single_book(self, book: Dict) -> Dict:
        """Format a single book record"""
        book_id = str(book['id'])
        
        # Map estado_sisgen to display text
        estado_display = "NO ENVIADO"
        if book['estadoSisgen'] == 1:
            estado_display = "ENVIADO"
        elif book['estadoSisgen'] == 3:
            estado_display = "NO ENVIADO (FALLIDO)"
        
        return {
            'id': book['id'],
            'libro': book['libro'],
            'fechaIngreso': book['fechaIngreso'].strftime('%Y-%m-%d') if book['fechaIngreso'] else '',
            'tipoPersona': book['tipoPersona'],
            'empresa': book['empresa'],
            'ruc': book['ruc'],
            'domfiscal': book['domfiscal'],
            'idtiplib': book['idtiplib'],
            'descripcionTipoLibro': book['descripcionTipoLibro'],
            'descripcionLibro': book['descripcionLibro'],
            'estadoSisgen': estado_display,
            'errores': self.book_errors.get(book_id, []),
            'observaciones': self.book_observations.get(book_id, []),
            'pdt_validation': {
                'has_errors': bool(self.pdt_errors.get(book_id, [])),
                'errors': self.pdt_errors.get(book_id, [])
            }
        }

    def _clear_temp_table(self):
        """Clear the temporary books table"""
        try:
            with connection.cursor() as cursor:
                cursor.execute("TRUNCATE TABLE libros_temp")
        except Exception as e:
            self.logger.error(f"Error clearing temporary table: {str(e)}")

    def _insert_temp_records(self, books: List[Dict]):
        """Insert records into temporary table"""
        try:
            with connection.cursor() as cursor:
                for book in books:
                    cursor.execute("INSERT INTO libros_temp(idlibro) VALUES (%s)", [book['id']])
        except Exception as e:
            self.logger.error(f"Error inserting into temporary table: {str(e)}")

    def _get_error_details(self) -> Dict:
        """Return current error tracking details"""
        return {
            'book_errors': self.book_errors,
            'observations': self.book_observations,
            'pdt_errors': self.pdt_errors
        } 