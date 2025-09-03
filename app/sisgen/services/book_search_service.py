"""
This module contains the book search service for the sisgen service.
"""

from typing import Dict, List, Tuple
import logging
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
            # Reset error tracking
            self.book_errors = {}
            self.book_observations = {}
            
            # Log incoming filters
            self.logger.info(f"Book search request with filters: {filters}")
            
            # Build and execute query
            books = self._execute_search_query(filters)
            
            # Process results
            processed_data = self._process_books(books)
            
            # Clear temporary table
            self._clear_temp_table()
            
            # Insert into temporary table
            self._insert_temp_records(processed_data)
            
            error_details = {
                'book_errors': self.book_errors,
                'observations': self.book_observations
            }
            
            return processed_data, len(processed_data), [], error_details
            
        except Exception as e:
            self.logger.error(f"Unexpected error in book search: {str(e)}")
            return [], 0, [str(e)], self._get_error_details()

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
        
        params = []
        conditions = []
        
        # Date range filter
        if filters.get('fechaDesde') and filters.get('fechaHasta'):
            conditions.append("l.fecing BETWEEN %s AND %s")
            params.extend([filters['fechaDesde'], filters['fechaHasta']])
        
        # Status filter
        estado = filters.get('estado')
        if estado == '0':
            conditions.append("(l.estadoSisgen = 0 OR l.estadoSisgen IS NULL)")
        elif estado in ('1', '3'):
            conditions.append("l.estadoSisgen = %s")
            params.append(estado)
        
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
            processed_book = self._format_single_book(book)
            processed.append(processed_book)
        
        return processed

    def _format_single_book(self, book: Dict) -> Dict:
        """Format a single book record"""
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
            'estadoSisgen': estado_display
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
            'observations': self.book_observations
        } 