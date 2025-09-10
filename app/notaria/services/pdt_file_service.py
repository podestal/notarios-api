from datetime import datetime
from typing import Dict, List, Any, Optional
from django.db import connection
from django.http import HttpResponse
import logging

class PdtFileService:
    """Service for generating PDT files (.lib, .act, .bie, etc.)"""

    # File type constants
    FILE_TYPE_ACT = 1  # Actos
    FILE_TYPE_BIE = 2  # Bienes
    FILE_TYPE_OTG = 3  # Otorgantes
    FILE_TYPE_MPA = 4  # Medio de Pago
    FILE_TYPE_FORM = 5  # Formulario
    FILE_TYPE_LIB = 6  # Libros

    def __init__(self, initial_date: str, final_date: str, file_type: int, type_kardex: Optional[int] = None):
        """Initialize PDT file service."""
        self.logger = logging.getLogger(__name__)
        self.initial_date = initial_date
        self.final_date = final_date
        self.file_type = file_type
        self.type_kardex = type_kardex
        self.data = []

    def generate_file(self) -> HttpResponse:
        """Generate PDT file based on file type."""
        try:
            # Load appropriate data based on file type
            if self.file_type == self.FILE_TYPE_ACT:
                self._load_data_act()
                return self._generate_file_act()
            elif self.file_type == self.FILE_TYPE_BIE:
                self._load_data_act()
                self._load_data_bien()
                return self._generate_file_bien()
            elif self.file_type == self.FILE_TYPE_OTG:
                self._load_data_act()
                self._load_data_bien()
                self._load_data_otorgante()
                return self._generate_file_otorgante()
            elif self.file_type == self.FILE_TYPE_MPA:
                self._load_data_act()
                self._load_data_bien()
                self._load_data_otorgante()
                self._load_data_medio_pago()
                return self._generate_file_medio()
            elif self.file_type == self.FILE_TYPE_FORM:
                self._load_data_act()
                self._load_data_bien()
                self._load_data_otorgante()
                self._load_data_medio_pago()
                self._load_data_formulario()
                return self._generate_file_form()
            elif self.file_type == self.FILE_TYPE_LIB:
                self._load_data_libro()
                return self._generate_file_libro()
            else:
                raise ValueError(f"Invalid file type: {self.file_type}")

        except Exception as e:
            self.logger.error(f"Error generating PDT file: {str(e)}")
            raise

    def _load_data_libro(self):
        """Load libro data for PDT file."""
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

            # Get libro data
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
                        l.numdoc_plantilla,
                        l.tipper,
                        l.prinom,
                        l.segnom,
                        l.apepat,
                        l.apemat,
                        l.domfiscal
                    FROM libros l
                    WHERE STR_TO_DATE(fecing, '%%Y-%%m-%%d') BETWEEN %s AND %s
                    ORDER BY numlibro
                """, [start_date, end_date])
                
                columns = [col[0] for col in cursor.description]
                self.data = [dict(zip(columns, row)) for row in cursor.fetchall()]

        except Exception as e:
            self.logger.error(f"Error loading libro data: {str(e)}")
            raise

    def _generate_file_libro(self) -> HttpResponse:
        """Generate .lib file for PDT."""
        try:
            # Initialize content list
            content_lines = []

            # Process each libro
            for libro in self.data:
                # Format data according to PDT specifications
                line = self._format_libro_line(libro)
                content_lines.append(line)

            # Join lines with newline
            content = '\n'.join(content_lines)

            # Create response with .lib file
            response = HttpResponse(content, content_type='text/plain')
            
            # Format dates for filename
            try:
                start_date = datetime.strptime(self.initial_date, '%d/%m/%Y')
                end_date = datetime.strptime(self.final_date, '%d/%m/%Y')
            except ValueError:
                start_date = datetime.strptime(self.initial_date, '%Y-%m-%d')
                end_date = datetime.strptime(self.final_date, '%Y-%m-%d')
                
            # Format filename: LE_YYYYMMDD_YYYYMMDD.lib
            filename = f"LE_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.lib"
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            
            return response

        except Exception as e:
            self.logger.error(f"Error generating .lib file: {str(e)}")
            raise

    def _format_libro_line(self, libro: Dict) -> str:
        """Format a single line for the .lib file according to PDT specifications."""
        try:
            # Get person name based on type
            if libro['tipper'] == 'N':  # Natural person
                nombre = f"{libro['prinom']} {libro['segnom']} {libro['apepat']} {libro['apemat']}".strip()
            else:  # Juridical person
                nombre = libro['empresa'] if libro['empresa'] else ''

            # Format date - handle both string and datetime.date objects
            fecha = ''
            if libro['fecing']:
                if isinstance(libro['fecing'], str):
                    fecha = datetime.strptime(libro['fecing'], '%Y-%m-%d').strftime('%d/%m/%Y')
                else:
                    fecha = libro['fecing'].strftime('%d/%m/%Y')

            # Build line with fixed width fields
            # Note: Adjust field widths according to actual PDT specifications
            fields = [
                str(libro['numlibro']).ljust(15),  # Numero de libro
                fecha.ljust(10),  # Fecha
                (libro['dni'] or '').ljust(8),  # DNI
                (libro['ruc'] or '').ljust(11),  # RUC
                nombre.ljust(100),  # Nombre/Razon social
                (libro['domfiscal'] or '').ljust(100),  # Domicilio fiscal
                (libro['descritiplib'] or '').ljust(50),  # Descripcion tipo libro
                str(libro['folio'] or '').ljust(10),  # Folio
            ]

            return '|'.join(fields)

        except Exception as e:
            self.logger.error(f"Error formatting libro line: {str(e)}")
            raise

    # Placeholder methods for other file types
    def _load_data_act(self): pass
    def _load_data_bien(self): pass
    def _load_data_otorgante(self): pass
    def _load_data_medio_pago(self): pass
    def _load_data_formulario(self): pass
    def _generate_file_act(self): pass
    def _generate_file_bien(self): pass
    def _generate_file_otorgante(self): pass
    def _generate_file_medio(self): pass
    def _generate_file_form(self): pass 