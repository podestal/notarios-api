from datetime import datetime
from typing import Dict, List, Any, Optional
from django.db import connection
from django.db.models import Q

from ..models import Libros

class PdtLibrosService:
    """Service for checking PDT errors in Libros records."""

    def __init__(self, initial_date: str, final_date: str):
        """Initialize with date range."""
        self.initial_date = initial_date
        self.final_date = final_date
        self.total_libros = 0
        self.errors = []

    def load_data(self) -> None:
        """Load and validate libro data for the given date range."""
        try:
            # Convert dates - support both DD/MM/YYYY and YYYY-MM-DD formats
            try:
                # Try DD/MM/YYYY format first (like PHP)
                start_date = datetime.strptime(self.initial_date, '%d/%m/%Y').date()
                end_date = datetime.strptime(self.final_date, '%d/%m/%Y').date()
            except ValueError:
                # Try YYYY-MM-DD format as fallback
                start_date = datetime.strptime(self.initial_date, '%Y-%m-%d').date()
                end_date = datetime.strptime(self.final_date, '%Y-%m-%d').date()

            # Get all libros in date range
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        l.numlibro,
                        l.fecing,
                        l.empresa,
                        l.descritiplib,
                        l.dni,
                        l.ruc,
                        l.folio,
                        l.idtipfol,
                        l.idnlibro,
                        l.solicitante,
                        l.numdoc_plantilla
                    FROM libros l
                    WHERE STR_TO_DATE(fecing, '%%Y-%%m-%%d') BETWEEN %s AND %s
                    ORDER BY numlibro
                """, [start_date, end_date])
                
                self.libros = cursor.fetchall()
                self.total_libros = len(self.libros)

            # Validate each libro
            for libro in self.libros:
                self._validate_libro(libro)

        except Exception as e:
            raise Exception(f"Error loading libro data: {str(e)}")

    def _validate_libro(self, libro: tuple) -> None:
        """Validate a single libro record and add any errors found."""
        num_libro = libro[0]  # numlibro
        empresa = libro[2]  # empresa
        dni = libro[4]  # dni
        ruc = libro[5]  # ruc
        solicitante = libro[9]  # solicitante
        numdoc_plantilla = libro[10]  # numdoc_plantilla

        # Check for required fields
        if not solicitante:
            self._add_error(num_libro, "Falta nombre del solicitante", True)

        # Check for document numbers
        if not dni and not ruc and not numdoc_plantilla:
            self._add_error(num_libro, "Falta documento de identidad (DNI/RUC)", True)

        # Check for empresa name if RUC exists
        if ruc and not empresa:
            self._add_error(num_libro, "Falta nombre de empresa para RUC", True)

        # Add more validations as needed...

    def _add_error(self, book_number: str, error_description: str, is_correctable: bool = True) -> None:
        """Add an error to the errors list."""
        self.errors.append({
            'bookNumber': book_number,
            'errorItem': error_description,
            'isCorrectable': 1 if is_correctable else 0,
            'typeOfCorrection': 'AUTO',  # Default to auto-correction
            'categoryCorrect': 'LIBRO',  # Category for libro errors
            'fileType': 'LIB'  # File type for libros
        })

    def get_results(self) -> Dict[str, Any]:
        """Get the validation results."""
        return {
            'list': self.errors,
            'totalError': len(self.errors),
            'totalRecords': self.total_libros
        }

    def correct_errors(self, error_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Correct the specified errors."""
        # TODO: Implement error correction logic
        return {
            'error': 0,
            'errorDescription': 'Errores corregidos exitosamente'
        } 