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
            # First try DD/MM/YYYY format
            start_date = datetime.strptime(self.initial_date, '%d/%m/%Y')
            end_date = datetime.strptime(self.final_date, '%d/%m/%Y')
        except ValueError:
            try:
                # Then try YYYY-MM-DD format
                start_date = datetime.strptime(self.initial_date, '%Y-%m-%d')
                end_date = datetime.strptime(self.final_date, '%Y-%m-%d')
            except ValueError as e:
                raise ValueError(f"Invalid date format. Dates must be in DD/MM/YYYY or YYYY-MM-DD format")

        # Return dates in the format they were provided
        return self.initial_date, self.final_date

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

    def get_base_kardex_query(self) -> str:
        """Get the base kardex query that all formatters should use."""
        return """
            WITH kardex_actos AS (
                SELECT 
                    k.idkardex,
                    k.kardex,
                    k.idtipkar,
                    k.numescritura,
                    k.fechaescritura,
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
                AND k.fechaescritura BETWEEN %s AND %s
                AND SUBSTRING(codactos, n.n, 3) != ''
            )
        """

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
                    AND CASE 
                        WHEN k.fechaconclusion = '0000-00-00' OR k.fechaconclusion IS NULL OR k.fechaconclusion = ''
                        THEN STR_TO_DATE(k.fechaescritura, '%%Y-%%m-%%d') BETWEEN STR_TO_DATE(%s, '%%d/%%m/%%Y') AND STR_TO_DATE(%s, '%%d/%%m/%%Y')
                        ELSE STR_TO_DATE(k.fechaconclusion, '%%d/%%m/%%Y') BETWEEN STR_TO_DATE(%s, '%%d/%%m/%%Y') AND STR_TO_DATE(%s, '%%d/%%m/%%Y')
                    END
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
            """, [self.type_kardex, start_date, end_date, start_date, end_date])
            
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

            # Format dates safely
            try:
                fecha_escritura = datetime.strptime(record['fechaescritura'], '%Y-%m-%d').strftime('%d/%m/%Y') if record['fechaescritura'] else ''
            except (ValueError, TypeError):
                fecha_escritura = ''

            # Use fechaconclusion as is since it's already in DD/MM/YYYY format
            fecha_conclusion = record['fechaconclusion'] if record['fechaconclusion'] and record['fechaconclusion'] != '0000-00-00' else ''
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
        """Load bienes data following the PHP implementation."""
        start_date, end_date = self.get_formatted_dates()
        
        # Convert dates to YYYY-MM-DD format for comparison
        try:
            start_date_db = datetime.strptime(start_date, '%d/%m/%Y').strftime('%Y-%m-%d')
            end_date_db = datetime.strptime(end_date, '%d/%m/%Y').strftime('%Y-%m-%d')
        except ValueError:
            start_date_db = start_date
            end_date_db = end_date

        print(f"\n=== BienesFormatter Debug ===")
        print(f"Initial date: {self.initial_date}")
        print(f"Final date: {self.final_date}")
        print(f"Type kardex: {self.type_kardex}")
        print(f"DB dates: start={start_date_db}, end={end_date_db}")

        with connection.cursor() as cursor:
            # Combined query for both vehicles and properties
            query = """
                -- Vehicle records
                (
                    SELECT 
                        k.idkardex,
                        k.kardex,
                        k.idtipkar,
                        k.numescritura,
                        k.fechaescritura,
                        t.actosunat,
                        1 as secuencial_acto,
                        v.detveh as detalle,
                        v.numplaca,
                        v.numserie,
                        v.motor,
                        v.fecinsc as fecha_adquisicion,
                        'B' as tipob,
                        '08' as codbien,
                        NULL as tpsm,
                        NULL as npsm,
                        NULL as smaquiequipo,
                        NULL as coddis,
                        NULL as oespecific,
                        @rn1 := IF(@prev1 = k.kardex, @rn1 + 1, 1) as secuencial_bien,
                        @prev1 := k.kardex
                    FROM (SELECT @rn1 := 0, @prev1 := NULL) as vars,
                        kardex k
                        INNER JOIN detallevehicular v ON v.kardex = k.kardex
                        INNER JOIN tiposdeacto t ON t.idtipoacto = v.idtipacto
                    WHERE k.idtipkar = %s
                    AND k.fechaescritura != ''
                    AND k.fechaescritura != '0000-00-00'
                    AND k.fechaescritura BETWEEN %s AND %s
                    AND t.actosunat != ''
                )
                UNION ALL
                -- Property records
                (
                    SELECT 
                        k.idkardex,
                        k.kardex,
                        k.idtipkar,
                        k.numescritura,
                        k.fechaescritura,
                        t.actosunat,
                        1 as secuencial_acto,
                        b.detbien as detalle,
                        NULL as numplaca,
                        NULL as numserie,
                        NULL as motor,
                        b.fechaconst as fecha_adquisicion,
                        b.tipob,
                        tb.codbien,
                        b.tpsm,
                        b.npsm,
                        b.smaquiequipo,
                        b.coddis,
                        b.oespecific,
                        @rn2 := IF(@prev2 = k.kardex, @rn2 + 1, 1) as secuencial_bien,
                        @prev2 := k.kardex
                    FROM (SELECT @rn2 := 0, @prev2 := NULL) as vars,
                        kardex k
                        INNER JOIN patrimonial p ON p.kardex = k.kardex
                        INNER JOIN detallebienes b ON b.itemmp = p.itemmp
                        INNER JOIN tiposdeacto t ON t.idtipoacto = p.idtipoacto
                        INNER JOIN tipobien tb ON tb.idtipbien = b.idtipbien
                    WHERE k.idtipkar = %s
                    AND k.fechaescritura != ''
                    AND k.fechaescritura != '0000-00-00'
                    AND k.fechaescritura BETWEEN %s AND %s
                    AND t.actosunat != ''
                )
                ORDER BY kardex, secuencial_bien
            """

            print("\nExecuting combined query...")
            cursor.execute(query, [
                self.type_kardex, start_date_db, end_date_db,  # For vehicles
                self.type_kardex, start_date_db, end_date_db   # For properties
            ])
            
            columns = [col[0] for col in cursor.description]
            self.data = [dict(zip(columns, row)) for row in cursor.fetchall()]
            print(f"Found {len(self.data)} total records")
            print("=== End BienesFormatter Debug ===\n")

    def format_line(self, record: Dict) -> str:
        """Format a single line for the .bie file."""
        try:
            print(f"\nFormatting line for record: {record['kardex']}")
            
            # Get tipo kardex code
            tipo_kardex = {
                1: '1',  # Escritura
                3: '2',  # Transferencia
                4: '5',  # Otros
            }.get(record['idtipkar'], '')
            print(f"Tipo kardex: {tipo_kardex}")

            # Format date safely
            try:
                fecha_escritura = datetime.strptime(record['fechaescritura'], '%Y-%m-%d').strftime('%d/%m/%Y') if record['fechaescritura'] else ''
                print(f"Fecha escritura: {fecha_escritura}")
            except (ValueError, TypeError) as e:
                print(f"Error formatting fecha_escritura: {e}")
                fecha_escritura = ''

            # Handle vehicle records
            if record.get('codbien') == '08':
                print("Processing vehicle record")
                tipo_bien = 'B'
                codigo_bien = '08'
                
                if record.get('numplaca'):
                    opcion_psm = '1'
                    numero_psm = record['numplaca']
                elif record.get('numserie'):
                    opcion_psm = '2'
                    numero_psm = record['numserie']
                else:
                    opcion_psm = '3'
                    numero_psm = record.get('motor', '')
                
                numero_serie = ''
                origen_bien = ''
                codigo_ubicacion = ''
                fecha_adquisicion = record.get('fecha_adquisicion', '')
                descripcion_otros = ''
                
            # Handle property records
            else:
                print("Processing property record")
                tipo_bien = 'B' if record.get('tipob') == 'BIENES' else 'A'
                codigo_bien = record.get('codbien', '')
                
                opcion_psm = {
                    'P': '1',
                    'S': '2',
                    'M': '3',
                    '': ''
                }.get(record.get('tpsm', ''), '')
                
                numero_psm = record.get('npsm', '')
                numero_serie = record.get('smaquiequipo', '')
                
                if codigo_bien in ['04', '99']:
                    origen_bien = '1' if record.get('coddis') else ''
                else:
                    origen_bien = ''
                
                codigo_ubicacion = record['coddis'] if codigo_bien == '04' else ''
                fecha_adquisicion = record.get('fecha_adquisicion', '')
                descripcion_otros = record['oespecific'] if codigo_bien == '99' else ''

            print(f"Final field values:")
            print(f"tipo_bien: {tipo_bien}")
            print(f"codigo_bien: {codigo_bien}")
            print(f"opcion_psm: {opcion_psm}")
            print(f"numero_psm: {numero_psm}")
            print(f"numero_serie: {numero_serie}")
            print(f"origen_bien: {origen_bien}")
            print(f"codigo_ubicacion: {codigo_ubicacion}")
            print(f"fecha_adquisicion: {fecha_adquisicion}")
            print(f"descripcion_otros: {descripcion_otros}")

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

            result = '|'.join(fields)
            print(f"Formatted line: {result}")
            return result

        except Exception as e:
            print(f"Error formatting line: {str(e)}")
            raise

class OtorgantesFormatter(BasePdtFormatter):
    """Formatter for .otg files."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.extension = 'otg'

    def load_data(self):
        """Load otorgantes data efficiently."""
        start_date, end_date = self.get_formatted_dates()
        print(f"\n=== OtorgantesFormatter Debug ===")
        print(f"Loading data for dates: {start_date} to {end_date}")

        # Convert dates to YYYY-MM-DD format for comparison
        try:
            start_date_db = datetime.strptime(start_date, '%d/%m/%Y').strftime('%Y-%m-%d')
            end_date_db = datetime.strptime(end_date, '%d/%m/%Y').strftime('%Y-%m-%d')
        except ValueError:
            start_date_db = start_date
            end_date_db = end_date

        print(f"DB dates: start={start_date_db}, end={end_date_db}")

        with connection.cursor() as cursor:
            # First get valid kardex records to improve performance
            cursor.execute("""
                WITH filtered_kardex AS (
                    SELECT 
                        k.idkardex,
                        k.kardex,
                        k.idtipkar,
                        k.numescritura,
                        k.fechaescritura
                    FROM kardex k
                    WHERE k.idtipkar = %s
                    AND k.fechaescritura BETWEEN %s AND %s
                    AND k.fechaescritura != '0000-00-00'
                ),
                otorgantes AS (
                    SELECT 
                        k.*,
                        ca.idtipoacto,
                        t.actosunat,
                        c.idcontratante,
                        c.condicion,
                        c2.idtipdoc,
                        c2.numdoc,
                        c2.apepat,
                        c2.apemat,
                        c2.prinom,
                        c2.razonsocial,
                        c2.tipper,
                        DENSE_RANK() OVER (
                            PARTITION BY k.kardex
                            ORDER BY c.idcontratante
                        ) as secuencial_otorgante
                    FROM filtered_kardex k
                    INNER JOIN contratantesxacto ca ON ca.kardex = k.kardex
                    INNER JOIN tiposdeacto t ON t.idtipoacto = ca.idtipoacto
                    INNER JOIN contratantes c ON c.idcontratante = ca.idcontratante
                    INNER JOIN cliente2 c2 ON c2.idcontratante = c.idcontratante
                    WHERE t.actosunat != ''
                )
                SELECT *
                FROM otorgantes
                ORDER BY 
                    CAST(numescritura AS UNSIGNED),
                    idcontratante
            """, [self.type_kardex, start_date_db, end_date_db])
            
            columns = [col[0] for col in cursor.description]
            self.data = [dict(zip(columns, row)) for row in cursor.fetchall()]
            print(f"Found {len(self.data)} records")
            print("=== End OtorgantesFormatter Debug ===\n")

    def format_line(self, record: Dict) -> str:
        """Format a single line for the .otg file."""
        try:
            # Get tipo kardex code
            tipo_kardex = {
                1: '1',  # Escritura
                3: '2',  # Transferencia
                4: '5',  # Otros
            }.get(record['idtipkar'], '')

            # Format date safely
            try:
                fecha_escritura = datetime.strptime(record['fechaescritura'], '%Y-%m-%d').strftime('%d/%m/%Y') if record['fechaescritura'] else ''
            except (ValueError, TypeError):
                fecha_escritura = ''

            # Format tipo documento based on idtipdoc
            tipo_documento = {
                1: '1',  # DNI
                4: '4',  # Carnet de Extranjeria
                6: '6',  # RUC
                7: '7',  # Pasaporte
            }.get(record['idtipdoc'], '9')  # Default to '9' (OTROS)

            # Format condicion
            condicion = {
                'COMPRADOR': '1',
                'VENDEDOR': '2',
                'REPRESENTANTE': '3',
                'TESTIGO': '4',
                'INTERPRETE': '5',
                'OTROS': '9'
            }.get(record['condicion'], '9')

            # Handle name/razon social based on tipo persona
            if record['tipper'] == 'N':  # Natural
                nombres = record['prinom'] or ''
                apellido_paterno = record['apepat'] or ''
                apellido_materno = record['apemat'] or ''
                razon_social = ''
            else:  # Juridica
                nombres = ''
                apellido_paterno = ''
                apellido_materno = ''
                razon_social = record['razonsocial'] or ''

            # Format fields
            fields = [
                str(tipo_kardex).ljust(1),  # Tipo kardex
                str(record['numescritura']).ljust(5),  # Numero escritura
                fecha_escritura.ljust(10),  # Fecha escritura
                str(1).rjust(5),  # Secuencial acto (always 1 in PHP)
                str(record['secuencial_otorgante']).rjust(5),  # Secuencial otorgante
                str(tipo_documento).ljust(1),  # Tipo documento
                self.replace_string_pdt(record['numdoc']).ljust(12),  # Numero documento
                self.replace_string_pdt(apellido_paterno).ljust(40),  # Apellido paterno
                self.replace_string_pdt(apellido_materno).ljust(40),  # Apellido materno
                self.replace_string_pdt(nombres).ljust(40),  # Nombres
                self.replace_string_pdt(razon_social).ljust(100),  # Razon social
                str(condicion).ljust(1)  # Condicion
            ]

            return '|'.join(fields)

        except Exception as e:
            self.logger.error(f"Error formatting otorgante line: {str(e)}")
            raise

class MediosPagoFormatter(BasePdtFormatter):
    """Formatter for .mpa files (Medios de Pago)."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.extension = 'mpa'

    def load_data(self):
        """Load medios de pago data efficiently."""
        start_date, end_date = self.get_formatted_dates()
        print(f"\n=== MediosPagoFormatter Debug ===")
        print(f"Loading data for dates: {start_date} to {end_date}")

        # Convert dates to YYYY-MM-DD format for comparison
        try:
            start_date_db = datetime.strptime(start_date, '%d/%m/%Y').strftime('%Y-%m-%d')
            end_date_db = datetime.strptime(end_date, '%d/%m/%Y').strftime('%Y-%m-%d')
        except ValueError:
            start_date_db = start_date
            end_date_db = end_date

        print(f"DB dates: start={start_date_db}, end={end_date_db}")

        with connection.cursor() as cursor:
            cursor.execute("""
                WITH filtered_kardex AS (
                    SELECT 
                        k.idkardex,
                        k.kardex,
                        k.idtipkar,
                        k.numescritura,
                        k.fechaescritura
                    FROM kardex k
                    WHERE k.idtipkar = %s
                    AND k.fechaescritura BETWEEN %s AND %s
                    AND k.fechaescritura != '0000-00-00'
                ),
                medios_pago AS (
                    SELECT 
                        k.*,
                        p.itemmp,
                        p.idmon,
                        p.importetrans,
                        mp.codmepag,
                        mp.fpago,
                        mp.idbancos,
                        mp.importemp,
                        mp.foperacion,
                        mp.documentos,
                        DENSE_RANK() OVER (
                            PARTITION BY k.kardex
                            ORDER BY mp.detmp
                        ) as secuencial_pago
                    FROM filtered_kardex k
                    INNER JOIN patrimonial p ON p.kardex = k.kardex
                    INNER JOIN detallemediopago mp ON mp.itemmp = p.itemmp
                )
                SELECT *
                FROM medios_pago
                ORDER BY 
                    CAST(numescritura AS UNSIGNED),
                    itemmp,
                    secuencial_pago
            """, [self.type_kardex, start_date_db, end_date_db])
            
            columns = [col[0] for col in cursor.description]
            self.data = [dict(zip(columns, row)) for row in cursor.fetchall()]
            print(f"Found {len(self.data)} records")
            print("=== End MediosPagoFormatter Debug ===\n")

    def format_line(self, record: Dict) -> str:
        """Format a single line for the .mpa file."""
        try:
            # Get tipo kardex code
            tipo_kardex = {
                1: '1',  # Escritura
                3: '2',  # Transferencia
                4: '5',  # Otros
            }.get(record['idtipkar'], '')

            # Format date safely
            try:
                fecha_escritura = datetime.strptime(record['fechaescritura'], '%Y-%m-%d').strftime('%d/%m/%Y') if record['fechaescritura'] else ''
            except (ValueError, TypeError):
                fecha_escritura = ''

            # Format date safely
            try:
                fecha_operacion = datetime.strptime(record['foperacion'], '%Y-%m-%d').strftime('%d/%m/%Y') if record['foperacion'] else ''
            except (ValueError, TypeError):
                fecha_operacion = ''

            # Format moneda
            moneda = {
                1: '2',  # Soles
                2: '1',  # Dólares
            }.get(record['idmon'], '')

            # Format medio de pago
            medio_pago = {
                1: '01',  # Depósito en cuenta
                2: '02',  # Giro
                3: '03',  # Transferencia de fondos
                4: '04',  # Orden de pago
                5: '05',  # Tarjeta de débito
                6: '06',  # Tarjeta de crédito
                7: '07',  # Cheques con la cláusula de "no negociable", "intransferibles", "no a la orden" u otra equivalente
                8: '08',  # Efectivo, por operaciones en las que no existe obligación de utilizar medio de pago
                9: '09',  # Efectivo, en los demás casos
                10: '10', # Medios de pago usados en comercio exterior
                11: '11', # Documentos emitidos por las EDPYMES y las cooperativas de ahorro y crédito no autorizadas a captar depósitos del público
                12: '12', # Tarjeta de crédito emitida en el país o en el exterior por una empresa no perteneciente al sistema financiero, cuyo objeto principal sea la emisión y administración de tarjetas de crédito
                99: '99'  # Otros medios de pago
            }.get(record['codmepag'], '99')

            # Format fields
            fields = [
                str(tipo_kardex).ljust(1),  # Tipo kardex
                str(record['numescritura']).ljust(5),  # Numero escritura
                fecha_escritura.ljust(10),  # Fecha escritura
                str(1).rjust(5),  # Secuencial acto (always 1 in PHP)
                str(record['secuencial_pago']).rjust(5),  # Secuencial pago
                str(medio_pago).ljust(2),  # Codigo medio de pago
                str(moneda).ljust(1),  # Moneda
                str(record['importemp']).rjust(15),  # Importe
                fecha_operacion.ljust(10),  # Fecha operacion
                self.replace_string_pdt(record['documentos'] or '').ljust(20)  # Numero operacion
            ]

            return '|'.join(fields)

        except Exception as e:
            self.logger.error(f"Error formatting medio pago line: {str(e)}")
            raise

class FormularioFormatter(BasePdtFormatter):
    """Formatter for .for files (Formularios)."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.extension = 'for'

    def load_data(self):
        """Load formulario data following the PHP implementation."""
        start_date, end_date = self.get_formatted_dates()

        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT DISTINCT 
                    k.idkardex,
                    k.kardex,
                    k.idtipkar,
                    k.numescritura,
                    k.fechaescritura,
                    r.idrenta,
                    r.idcontratante,
                    f.numformu,
                    f.monto,
                    ROW_NUMBER() OVER (
                        PARTITION BY k.kardex, r.idrenta
                        ORDER BY f.idformulario
                    ) as secuencial_formulario
                FROM kardex k
                INNER JOIN renta r ON r.kardex = k.kardex
                INNER JOIN formulario f ON f.idrenta = r.idrenta
                WHERE k.idtipkar = %s
                AND k.fechaconclusion IS NOT NULL
                AND k.fechaconclusion != '0000-00-00'
                AND k.fechaconclusion != ''
                AND k.fechaconclusion BETWEEN %s AND %s
                ORDER BY 
                    CAST(k.numescritura AS UNSIGNED),
                    r.idrenta,
                    f.idformulario
            """, [self.type_kardex, start_date, end_date])
            
            columns = [col[0] for col in cursor.description]
            self.data = [dict(zip(columns, row)) for row in cursor.fetchall()]

    def format_line(self, record: Dict) -> str:
        """Format a single line for the .for file."""
        try:
            # Get tipo kardex code
            tipo_kardex = {
                1: '1',  # Escritura
                3: '2',  # Transferencia
                4: '5',  # Otros
            }.get(record['idtipkar'], '')

            # Format date safely
            try:
                fecha_escritura = datetime.strptime(record['fechaescritura'], '%Y-%m-%d').strftime('%d/%m/%Y') if record['fechaescritura'] else ''
            except (ValueError, TypeError):
                fecha_escritura = ''

            # Format fields
            fields = [
                str(tipo_kardex).ljust(1),  # Tipo kardex
                str(record['numescritura']).ljust(5),  # Numero escritura
                fecha_escritura.ljust(10),  # Fecha escritura
                str(1).rjust(5),  # Secuencial acto (always 1 in PHP)
                str(record['secuencial_formulario']).rjust(5),  # Secuencial formulario
                str(record['idcontratante']).ljust(12),  # ID Contratante
                self.replace_string_pdt(record['numformu']).ljust(10),  # Numero formulario
                str(record['monto']).rjust(15)  # Monto
            ]

            return '|'.join(fields)

        except Exception as e:
            self.logger.error(f"Error formatting formulario line: {str(e)}")
            raise

class LibrosFormatter(BasePdtFormatter):
    """Formatter for .lib files (Libros)."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.extension = 'lib'

    def load_data(self):
        """Load libros data following the PHP implementation."""
        start_date, end_date = self.get_formatted_dates()
        print(f"\n=== LibrosFormatter Debug ===")
        print(f"Loading data for dates: {start_date} to {end_date}")

        # Convert dates to YYYY-MM-DD format for comparison
        try:
            start_date_db = datetime.strptime(start_date, '%d/%m/%Y').strftime('%Y-%m-%d')
            end_date_db = datetime.strptime(end_date, '%d/%m/%Y').strftime('%Y-%m-%d')
        except ValueError:
            start_date_db = start_date
            end_date_db = end_date

        print(f"DB dates: start={start_date_db}, end={end_date_db}")

        with connection.cursor() as cursor:
            cursor.execute("""
                WITH filtered_libros AS (
                    SELECT 
                        l.numlibro,
                        l.ano,
                        l.fecing,
                        l.tipper,
                        l.apepat,
                        l.apemat,
                        l.prinom,
                        l.segnom,
                        l.ruc,
                        l.empresa,
                        l.domfiscal,
                        l.coddis,
                        l.idtiplib,
                        l.folio,
                        l.feclegal
                    FROM libros l
                    WHERE l.fecing BETWEEN %s AND %s
                    AND l.fecing != '0000-00-00'
                    AND l.fecing != ''
                )
                SELECT 
                    l.*,
                    tl.coddlib,
                    tl.destiplib,
                    u.coddist,
                    u.codprov,
                    u.codpto,
                    ROW_NUMBER() OVER (
                        ORDER BY l.fecing, l.numlibro
                    ) as secuencial_libro
                FROM filtered_libros l
                INNER JOIN tipolibro tl ON tl.idtiplib = l.idtiplib
                LEFT JOIN ubigeo u ON u.coddis = l.coddis
                ORDER BY 
                    l.fecing,
                    l.numlibro
            """, [start_date_db, end_date_db])
            
            columns = [col[0] for col in cursor.description]
            self.data = [dict(zip(columns, row)) for row in cursor.fetchall()]
            print(f"Found {len(self.data)} records")
            print("=== End LibrosFormatter Debug ===\n")

    def format_line(self, record: Dict) -> str:
        """Format a single line for the .lib file."""
        try:
            # Format dates
            fecha_ingreso = datetime.strptime(str(record['fecing']), '%Y-%m-%d').strftime('%d/%m/%Y')
            fecha_legal = record['feclegal'] if record['feclegal'] else ''

            # Format tipo persona
            tipo_persona = '1' if record['tipper'] == 'N' else '2'  # 1=Natural, 2=Juridica

            # Format document type and number
            if record['tipper'] == 'N':
                tipo_documento = '1'  # DNI
                numero_documento = record['ruc'] or ''  # Using RUC field for both types
            else:
                tipo_documento = '6'  # RUC
                numero_documento = record['ruc'] or ''

            # Format names/razon social
            if record['tipper'] == 'N':
                nombres = record['prinom'] or ''
                if record['segnom']:
                    nombres = f"{nombres} {record['segnom']}"
                apellido_paterno = record['apepat'] or ''
                apellido_materno = record['apemat'] or ''
                razon_social = ''
            else:
                nombres = ''
                apellido_paterno = ''
                apellido_materno = ''
                razon_social = record['empresa'] or ''

            # Format ubigeo
            ubigeo = ''
            if record['codpto'] and record['codprov'] and record['coddist']:
                ubigeo = f"{record['codpto']}{record['codprov']}{record['coddist']}"

            # Format fields
            fields = [
                str(record['secuencial_libro']).rjust(5),  # Secuencial
                str(record['coddlib']).ljust(2),  # Codigo libro
                fecha_ingreso.ljust(10),  # Fecha ingreso
                str(tipo_persona).ljust(1),  # Tipo persona
                str(tipo_documento).ljust(1),  # Tipo documento
                self.replace_string_pdt(numero_documento).ljust(12),  # Numero documento
                self.replace_string_pdt(apellido_paterno).ljust(40),  # Apellido paterno
                self.replace_string_pdt(apellido_materno).ljust(40),  # Apellido materno
                self.replace_string_pdt(nombres).ljust(40),  # Nombres
                self.replace_string_pdt(razon_social).ljust(100),  # Razon social
                self.replace_string_pdt(record['domfiscal'] or '').ljust(150),  # Domicilio fiscal
                str(ubigeo).ljust(6),  # Ubigeo
                str(record['folio'] or '').ljust(10),  # Folio
                fecha_legal.ljust(10)  # Fecha legalizacion
            ]

            return '|'.join(fields)

        except Exception as e:
            self.logger.error(f"Error formatting libro line: {str(e)}")
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
        FILE_TYPE_BIE: BienesFormatter,
        FILE_TYPE_OTG: OtorgantesFormatter,
        FILE_TYPE_MPA: MediosPagoFormatter,
        FILE_TYPE_FORM: FormularioFormatter,
        FILE_TYPE_LIB: LibrosFormatter,
    }

    def __init__(self, initial_date: str, final_date: str, file_type: int, type_kardex: Optional[int] = None):
        self.formatter_class = self.FILE_TYPE_FORMATTERS.get(file_type)
        if not self.formatter_class:
            raise ValueError(f"Invalid file type: {file_type}")
            
        self.formatter = self.formatter_class(initial_date, final_date, type_kardex)

    def generate_file(self) -> HttpResponse:
        """Generate PDT file."""
        return self.formatter.generate_file()
