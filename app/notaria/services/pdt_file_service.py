from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Any, Optional
from django.db import connection
from django.http import HttpResponse
import logging

class BasePdtFormatter(ABC):
    """Base class for PDT file formatters."""
    
    def __init__(self, initial_date: str, final_date: str, type_kardex: Optional[int] = None):
        self.initial_date = initial_date
        self.final_date = final_date
        self.type_kardex = type_kardex
        self.logger = logging.getLogger(__name__)
        self.data = []
        self.extension = ''  # Will be set by child classes
        self.prefix = '3520'  # Common prefix for all PDT files

    @abstractmethod
    def load_data(self):
        """Load data from database."""
        pass

    @abstractmethod
    def format_line(self, record: Dict) -> str:
        """Format a single line according to PDT specifications."""
        pass

    def get_formatted_dates(self) -> tuple:
        """Convert and validate dates."""
        try:
            start_date = datetime.strptime(self.initial_date, '%d/%m/%Y').date()
            end_date = datetime.strptime(self.final_date, '%d/%m/%Y').date()
        except ValueError:
            start_date = datetime.strptime(self.initial_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(self.final_date, '%Y-%m-%d').date()
        return start_date, end_date

    def get_notary_data(self) -> Dict:
        """Get notary configuration data."""
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    idnotar AS idNotario,
                    nombre AS nombreNotario, 
                    apellido AS apellidosNotario,
                    CONCAT(nombre,' ',apellido) AS notario,
                    telefono AS telefonoNotario,
                    correo AS correoNotario, 
                    ruc AS rucNotario, 
                    direccion AS direccionNotario, 
                    distrito AS distritoNotario, 
                    codnotario AS codigoNotario,
                    codoficial AS codigoOficial, 
                    coduif AS codigoUif 
                FROM confinotario
            """)
            columns = [col[0] for col in cursor.description]
            result = cursor.fetchone()
            
            if not result:
                raise ValueError("No notary configuration found")
                
            return dict(zip(columns, result))

    def generate_file(self) -> HttpResponse:
        """Generate PDT file."""
        try:
            self.load_data()
            
            # Format lines
            content_lines = []
            for record in self.data:
                line = self.format_line(record)
                content_lines.append(line)

            # Join lines with newline and carriage return
            content = '\r\n'.join(content_lines)

            # Create response
            response = HttpResponse(content, content_type='text/plain')
            
            # Generate filename
            notary_data = self.get_notary_data()
            year = self.initial_date.split('/')[-1] if '/' in self.initial_date else self.initial_date.split('-')[0]
            filename = f"{self.prefix}{year[2:]}{notary_data['rucNotario']}.{self.extension}"
            
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            response['Content-Transfer-Encoding'] = 'binary'
            
            return response

        except Exception as e:
            self.logger.error(f"Error generating {self.extension} file: {str(e)}")
            raise

    def replace_string_pdt(self, text: str) -> str:
        """Clean text according to PDT specifications."""
        if not text:
            return ''
            
        replacements = {
            '?': ' ', '*': ' ', 'QQ11QQ': ' ',
            'Ñ': 'N', 'ñ': 'n', '°': ' ',
            '#': ' ', 'é': 'e', 'á': 'a',
            'í': 'i', 'ó': 'o', 'ú': 'u',
            "'": ' ', '&': ' ', 'É': 'E',
            'Á': 'A', 'Ó': 'O', 'Ú': 'U',
            'Í': 'I', ',': ' ', 'QQ22KK': ' '
        }
        
        for old, new in replacements.items():
            text = text.replace(old, new)
        
        return text

class ActosFormatter(BasePdtFormatter):
    """Formatter for .act files."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.extension = 'act'

    def load_data(self):
        """Load actos data efficiently without temporary tables."""
        start_date, end_date = self.get_formatted_dates()

        with connection.cursor() as cursor:
            # Get all required data in a single query
            cursor.execute("""
                WITH kardex_actos AS (
                    SELECT 
                        k.idkardex,
                        k.kardex,
                        k.idtipkar,
                        k.numescritura,
                        k.fechaescritura,
                        k.fechaconclusion,
                        SUBSTRING(codactos, n.n, 3) as acto_code
                    FROM kardex k
                    CROSS JOIN (
                        SELECT 1 + (3 * (a.n-1)) as n
                        FROM (
                            SELECT 1 as n UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 
                            UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8
                        ) a
                        WHERE 1 + (3 * (a.n-1)) <= (
                            SELECT MAX(LENGTH(codactos)) FROM kardex
                        )
                    ) n
                    WHERE k.idtipkar = %s
                    AND STR_TO_DATE(k.fechaconclusion, '%%d/%%m/%%Y') 
                    BETWEEN %s AND %s
                    AND SUBSTRING(codactos, n.n, 3) != ''
                )
                SELECT 
                    ka.idkardex,
                    ka.kardex,
                    ka.idtipkar,
                    ka.numescritura,
                    ka.fechaescritura,
                    ka.fechaconclusion,
                    t.idtipoacto,
                    t.actosunat,
                    t.desacto,
                    p.itemmp,
                    p.idmon,
                    p.nminuta,
                    p.importetrans,
                    p.exhibiomp,
                    p.tipocambio
                FROM kardex_actos ka
                INNER JOIN tiposdeacto t ON t.idtipoacto = ka.acto_code
                LEFT JOIN patrimonial p ON p.kardex = ka.kardex AND p.idtipoacto = ka.acto_code
                WHERE t.actosunat != ''
                AND t.actosunat IN (
                    '01', '02', '03', '04', '06', '07', '08', '09', '10',
                    '11', '12', '13', '14', '15', '16', '17', '18', '19',
                    '20', '21', '22', '23', '24', '25', '26'
                )
                ORDER BY CAST(ka.numescritura AS UNSIGNED) ASC
            """, [self.type_kardex, start_date, end_date])
            
            columns = [col[0] for col in cursor.description]
            self.data = [dict(zip(columns, row)) for row in cursor.fetchall()]

    def format_line(self, record: Dict) -> str:
        """Format a single line for the .act file."""
        try:
            # Get tipo kardex code
            tipo_kardex = {
                1: '1',  # Escritura
                3: '2',  # Transferencia
                4: '5',  # Otros
            }.get(record['idtipkar'], '')

            # Format dates
            fecha_escritura = datetime.strptime(record['fechaescritura'], '%Y-%m-%d').strftime('%d/%m/%Y')
            fecha_conclusion = record['fechaconclusion']  # Already in DD/MM/YYYY format
            fecha_legalizacion = ''  # Empty for actos

            # Format moneda and importe
            if record['idmon'] == 1:
                codigo_moneda = '2'  # Soles
            elif record['idmon'] == 2:
                codigo_moneda = '1'  # Dólares
            elif record['idmon'] == 3:
                # Handle foreign currency with exchange rate
                codigo_moneda = '1'
                record['importetrans'] = float(record['importetrans']) * float(record['tipocambio'])
            else:
                codigo_moneda = ''

            # Format fields
            fields = [
                str(tipo_kardex).ljust(1),  # Tipo kardex
                str(record['numescritura']).ljust(5),  # Numero escritura
                fecha_escritura.ljust(10),  # Fecha escritura
                fecha_conclusion.ljust(10),  # Fecha conclusion
                fecha_legalizacion.ljust(10),  # Fecha legalizacion
                str(record['actosunat']).ljust(2),  # Acto sunat
                str(record.get('secuencial', 1)).rjust(5),  # Secuencial
                codigo_moneda.ljust(1),  # Moneda
                str(record['importetrans']).rjust(15),  # Importe
                ''.ljust(10),  # Plazo inicial
                ''.ljust(11),  # Plazo final
                self.replace_string_pdt(record['desacto'] if record['actosunat'] == '14' else '').ljust(30),  # Nombre contrato
                (record.get('nminuta', '') or '').ljust(10),  # Fecha inscripcion minuta
                ('1' if record['exhibiomp'] == 'SI' else '0').ljust(1)  # Exhibio medio pago
            ]

            return '|'.join(fields)

        except Exception as e:
            self.logger.error(f"Error formatting act line: {str(e)}")
            raise

class BienesFormatter(BasePdtFormatter):
    """Formatter for .bie files."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.extension = 'bie'

    def load_data(self):
        """Load bienes data efficiently without temporary tables."""
        start_date, end_date = self.get_formatted_dates()

        with connection.cursor() as cursor:
            # First get all kardex records with their acts
            cursor.execute("""
                WITH kardex_actos AS (
                    -- Same CTE as ActosFormatter to get kardex records
                    SELECT 
                        k.idkardex,
                        k.kardex,
                        k.idtipkar,
                        k.numescritura,
                        k.fechaescritura,
                        k.fechaconclusion,
                        SUBSTRING(codactos, n.n, 3) as acto_code
                    FROM kardex k
                    CROSS JOIN (
                        SELECT 1 + (3 * (a.n-1)) as n
                        FROM (
                            SELECT 1 as n UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 
                            UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8
                        ) a
                        WHERE 1 + (3 * (a.n-1)) <= (
                            SELECT MAX(LENGTH(codactos)) FROM kardex
                        )
                    ) n
                    WHERE k.idtipkar = %s
                    AND STR_TO_DATE(k.fechaconclusion, '%%d/%%m/%%Y') 
                    BETWEEN %s AND %s
                    AND SUBSTRING(codactos, n.n, 3) != ''
                ),
                actos_data AS (
                    -- Get base actos data
                    SELECT 
                        ka.*,
                        t.actosunat,
                        t.desacto,
                        p.itemmp,
                        ROW_NUMBER() OVER (PARTITION BY ka.kardex ORDER BY ka.numescritura) as secuencial_acto
                    FROM kardex_actos ka
                    INNER JOIN tiposdeacto t ON t.idtipoacto = ka.acto_code
                    LEFT JOIN patrimonial p ON p.kardex = ka.kardex AND p.idtipoacto = ka.acto_code
                    WHERE t.actosunat != ''
                    AND t.actosunat NOT IN ('10')  -- Exclude actos without bienes
                )
                SELECT 
                    -- Common fields
                    a.idkardex,
                    a.kardex,
                    a.idtipkar,
                    a.numescritura,
                    a.fechaescritura,
                    a.actosunat,
                    a.secuencial_acto,
                    -- Vehicle specific fields
                    v.detveh,
                    v.numplaca,
                    v.numserie as serie_vehiculo,
                    v.motor,
                    v.fecinsc as fecha_adquisicion_vehiculo,
                    -- Regular property fields
                    b.detbien,
                    b.itemmp,
                    b.tipob,
                    b.idtipbien,
                    b.coddis,
                    b.fechaconst as fecha_adquisicion,
                    b.oespecific,
                    b.smaquiequipo,
                    b.tpsm,
                    b.npsm,
                    -- Tipo bien data
                    tb.codbien,
                    -- Row number for bien secuencial
                    ROW_NUMBER() OVER (
                        PARTITION BY a.kardex, a.acto_code 
                        ORDER BY COALESCE(v.detveh, b.detbien)
                    ) as secuencial_bien
                FROM actos_data a
                -- Left join both vehicle and regular property data
                LEFT JOIN detallevehicular v ON 
                    v.kardex = a.kardex AND 
                    a.idtipkar = 3  -- Only for vehicle type
                LEFT JOIN detallebienes b ON 
                    b.itemmp = a.itemmp AND
                    a.idtipkar != 3  -- For non-vehicle types
                LEFT JOIN tipobien tb ON tb.idtipbien = COALESCE(b.idtipbien, '8')  -- 8 for vehicles
                WHERE (v.detveh IS NOT NULL OR b.detbien IS NOT NULL)  -- Only records with bienes
                ORDER BY 
                    CAST(a.numescritura AS UNSIGNED),
                    a.secuencial_acto,
                    COALESCE(v.detveh, b.detbien)
            """, [self.type_kardex, start_date, end_date])
            
            columns = [col[0] for col in cursor.description]
            self.data = [dict(zip(columns, row)) for row in cursor.fetchall()]

    def format_line(self, record: Dict) -> str:
        """Format a single line for the .bie file."""
        try:
            # Get tipo kardex code
            tipo_kardex = {
                1: '1',  # Escritura
                3: '2',  # Transferencia
                4: '5',  # Otros
            }.get(record['idtipkar'], '')

            # Format date
            fecha_escritura = datetime.strptime(record['fechaescritura'], '%Y-%m-%d').strftime('%d/%m/%Y')

            # Determine tipo bien and related fields
            if record['idtipkar'] == 3:  # Vehicle
                tipo_bien = 'B'
                codigo_bien = '08'  # Fixed for vehicles
                
                # Determine placa/serie/motor option and value
                if record['numplaca']:
                    opcion_psm = '1'
                    numero_psm = record['numplaca']
                elif record['serie_vehiculo']:
                    opcion_psm = '2'
                    numero_psm = record['serie_vehiculo']
                else:
                    opcion_psm = '3'
                    numero_psm = record['motor']
                
                numero_serie = ''
                origen_bien = ''
                codigo_ubicacion = ''
                fecha_adquisicion = record['fecha_adquisicion_vehiculo'] or ''
                descripcion_otros = ''
                
            else:  # Regular property
                tipo_bien = 'B' if record['tipob'] == 'BIENES' else 'A'
                codigo_bien = record['codbien']
                
                # Handle placa/serie/motor based on tpsm
                opcion_psm = {
                    'P': '1',
                    'S': '2',
                    'M': '3',
                    '': ''
                }.get(record['tpsm'], '')
                
                numero_psm = record['npsm'] or ''
                numero_serie = record['smaquiequipo'] or ''
                
                # Handle special cases
                if codigo_bien in ['04', '99']:
                    origen_bien = '1' if record['coddis'] else ''
                else:
                    origen_bien = ''
                
                codigo_ubicacion = record['coddis'] if codigo_bien == '04' else ''
                fecha_adquisicion = record['fecha_adquisicion'] or ''
                descripcion_otros = record['oespecific'] if codigo_bien == '99' else ''

            # Format fields
            fields = [
                str(tipo_kardex).ljust(1),  # Tipo kardex
                str(record['numescritura']).ljust(5),  # Numero escritura
                fecha_escritura.ljust(10),  # Fecha escritura
                str(record['secuencial_acto']).rjust(5),  # Secuencial acto
                str(record['secuencial_bien']).rjust(5),  # Secuencial bien
                tipo_bien.ljust(1),  # Tipo bien (B/A)
                str(codigo_bien).ljust(2),  # Codigo bien
                str(opcion_psm).ljust(1),  # Opcion placa/serie/motor
                self.replace_string_pdt(numero_psm).ljust(20),  # Numero placa/serie/motor
                self.replace_string_pdt(numero_serie).ljust(20),  # Numero serie
                str(origen_bien).ljust(1),  # Origen bien
                str(codigo_ubicacion).ljust(6),  # Codigo ubicacion
                str(fecha_adquisicion).ljust(10),  # Fecha adquisicion
                self.replace_string_pdt(descripcion_otros).ljust(30)  # Descripcion otros
            ]

            return '|'.join(fields)

        except Exception as e:
            self.logger.error(f"Error formatting bien line: {str(e)}")
            raise

class PdtFileService:
    """Service for generating PDT files."""
    
    # File type constants
    FILE_TYPE_ACT = 1  # Actos
    FILE_TYPE_BIE = 2  # Bienes
    FILE_TYPE_OTG = 3  # Otorgantes
    FILE_TYPE_MPA = 4  # Medio de Pago
    FILE_TYPE_FORM = 5  # Formulario
    FILE_TYPE_LIB = 6  # Libros

    FILE_TYPE_FORMATTERS = {
        FILE_TYPE_ACT: ActosFormatter,
        FILE_TYPE_BIE: BienesFormatter,  # Add the new formatter
        # Other formatters will be added as we implement them
    }

    def __init__(self, initial_date: str, final_date: str, file_type: int, type_kardex: Optional[int] = None):
        self.formatter_class = self.FILE_TYPE_FORMATTERS.get(file_type)
        if not self.formatter_class:
            raise ValueError(f"Invalid file type: {file_type}")
            
        self.formatter = self.formatter_class(initial_date, final_date, type_kardex)

    def generate_file(self) -> HttpResponse:
        """Generate PDT file."""
        return self.formatter.generate_file()
