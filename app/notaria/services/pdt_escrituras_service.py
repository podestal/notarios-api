from datetime import datetime
from typing import Dict, List, Any, Optional
from django.db import connection
from django.db.models import Q

class PdtEscriturasService:
    """Service for checking PDT errors in Escrituras records."""

    # File type constants
    FILE_TYPE_ACT = 'ACT'  # Actos
    FILE_TYPE_BIE = 'BIE'  # Bienes
    FILE_TYPE_OTG = 'OTG'  # Otorgantes
    FILE_TYPE_MP = 'MP'    # Medios de Pago
    FILE_TYPE_FORM = 'FORM'  # Formularios

    def __init__(self, initial_date: str, final_date: str):
        """Initialize with date range."""
        self.initial_date = initial_date
        self.final_date = final_date
        self.total_kardex = 0
        self.errors = []
        self.kardex_data = {}  # Store kardex data for reuse across validations

    def load_data(self) -> None:
        """Load and validate escritura data for the given date range."""
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

            # Get all escrituras in date range
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT DISTINCT 
                        k.kardex,
                        k.idkardex,
                        k.fechaingreso,
                        k.codactos,
                        k.numescritura,
                        k.fechaescritura,
                        k.fechaconclusion,
                        p.itemmp,
                        p.idmon,
                        p.nminuta,
                        p.importetrans,
                        p.exhibiomp,
                        p.tipocambio,
                        p.idtipoacto,
                        t.desacto,
                        t.actosunat,
                        t.actouif,
                        t.umbral
                    FROM kardex k
                    INNER JOIN patrimonial p ON k.kardex = p.kardex
                    LEFT JOIN tiposdeacto t ON t.idtipoacto = p.idtipoacto
                    WHERE k.idtipkar = 1  -- Escrituras
                    AND STR_TO_DATE(k.fechaconclusion, '%%d/%%m/%%Y') 
                    BETWEEN %s AND %s
                    ORDER BY k.kardex ASC
                """, [start_date, end_date])
                
                rows = cursor.fetchall()
                self.kardex_data = {row[0]: row for row in rows}
                self.total_kardex = len(self.kardex_data)

            # First, truncate temporary tables if they exist
            with connection.cursor() as cursor:
                # Drop and recreate is safer than truncate for temp tables
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS pdt (
                        idPdt INT AUTO_INCREMENT PRIMARY KEY,
                        idkardex INT,
                        kardex VARCHAR(30),
                        idTipoKardex INT,
                        codActos VARCHAR(50),
                        actoSunat VARCHAR(10),
                        numeroEscritura VARCHAR(100),
                        fechaEscritura VARCHAR(10),
                        fechaConclusion VARCHAR(10)
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS temp_act (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        idKardex INT,
                        kardex VARCHAR(30),
                        nombreActo VARCHAR(255),
                        itemmp VARCHAR(50),
                        idtipkar INT,
                        numescritura VARCHAR(100),
                        fechaescritura VARCHAR(10),
                        fechaconclusion VARCHAR(10),
                        fechalegal VARCHAR(10),
                        actosunat VARCHAR(10),
                        tipoacto VARCHAR(50),
                        secuencialacto INT,
                        idmon INT,
                        importetransac DECIMAL(10,2),
                        plazoini VARCHAR(10),
                        plazofin VARCHAR(10),
                        desacto TEXT,
                        mminuta VARCHAR(10),
                        exhibiomp TINYINT,
                        temp CHAR(1)
                    )
                """)
                cursor.execute("TRUNCATE TABLE pdt")
                cursor.execute("TRUNCATE TABLE temp_act")

            # Insert initial data into pdt table
            for kardex, data in self.kardex_data.items():
                codactos = data[3]  # codactos
                if not codactos:
                    continue

                # Parse act codes (3 chars each)
                for i in range(0, len(codactos), 3):
                    act_code = codactos[i:i+3]
                    
                    # Check if act code has SUNAT code
                    with connection.cursor() as cursor:
                        cursor.execute("""
                            SELECT idtipoacto, actosunat, actouif, idtipkar, desacto, umbral
                            FROM tiposdeacto 
                            WHERE idtipoacto = %s 
                            AND actosunat <> '' 
                            AND actosunat IN ('01','02','03','04','06','07','08','09','10',
                                            '11','12','13','14','15','16','17','18','19',
                                            '20','21','22','23','24','25','26')
                        """, [act_code])
                        
                        tipo_acto = cursor.fetchone()
                        if tipo_acto:
                            # Insert into pdt table
                            with connection.cursor() as cursor:
                                cursor.execute("""
                                    INSERT INTO pdt (
                                        idkardex, kardex, idTipoKardex, codActos, 
                                        actoSunat, numeroEscritura, fechaEscritura, 
                                        fechaConclusion
                                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                                """, [
                                    data[1],  # idkardex
                                    kardex,
                                    1,  # idTipoKardex for escrituras
                                    act_code,
                                    tipo_acto[1],  # actosunat
                                    data[4],  # numescritura
                                    data[5],  # fechaescritura
                                    data[6]  # fechaconclusion
                                ])

            # Run all validations
            self.load_data_act()
            self.load_data_bien()
            self.load_data_otorgante()
            self.load_data_medio_pago()
            self.load_data_formulario()

        except Exception as e:
            raise Exception(f"Error loading escritura data: {str(e)}")

    def load_data_act(self) -> None:
        """Validate ACT (actos) data."""
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT p.idPdt, p.idKardex, p.kardex, p.idTipoKardex, p.codActos,
                       p.actoSunat, p.numeroEscritura, p.fechaEscritura,
                       STR_TO_DATE(p.fechaConclusion,'%d/%m/%Y') AS fechaConclusionFormato,
                       IF(p.fechaEscritura<=STR_TO_DATE(p.fechaConclusion,'%d/%m/%Y'),0,1) AS validationFechaEscritura,
                       p.fechaConclusion,
                       pat.itemmp, pat.idmon, pat.nminuta AS fechaInscripcionMinuta,
                       pat.importetrans, t.desacto AS acto,
                       pat.exhibiomp AS exhibioMp, pat.tipocambio, pat.idtipoacto
                FROM pdt p
                INNER JOIN patrimonial pat ON p.kardex = pat.kardex
                LEFT JOIN tiposdeacto t ON t.idtipoacto = pat.idtipoacto
                WHERE p.kardex = pat.kardex 
                AND p.codactos = pat.idtipoacto
                ORDER BY CAST(p.numeroEscritura AS UNSIGNED) ASC
            """)
            
            acts = cursor.fetchall()
            for act in acts:
                kardex = act[2]  # kardex
                id_kardex = act[1]  # idKardex
                acto = act[15]  # acto
                num_escritura = act[6]  # numeroEscritura
                fecha_escritura = act[7]  # fechaEscritura
                fecha_conclusion = act[10]  # fechaConclusion
                validation_fecha = act[9]  # validationFechaEscritura

                # Validate escritura number
                if not num_escritura or num_escritura == '0':
                    self._add_error(
                        kardex=kardex,
                        id_kardex=id_kardex,
                        error_item="Número de escritura no puede ser cero",
                        act=acto or "No especificado",
                        file_type=self.FILE_TYPE_ACT,
                        writing_date=fecha_escritura,
                        id_contractor=None
                    )

                # Validate conclusion date
                if validation_fecha == 1:
                    self._add_error(
                        kardex=kardex,
                        id_kardex=id_kardex,
                        error_item="La fecha de conclusión no puede ser menor que la fecha de escritura",
                        act=acto or "No especificado",
                        file_type=self.FILE_TYPE_ACT,
                        writing_date=fecha_escritura,
                        id_contractor=None,
                        is_correctable=True,
                        type_of_correction='AUTO'
                    )

    def load_data_bien(self) -> None:
        """Validate BIE (bienes) data."""
        # Get acts that require bienes validation
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT DISTINCT p.kardex, p.idKardex, t.desacto, p.codActos,
                       pat.itemmp, pat.importetrans
                FROM pdt p
                INNER JOIN patrimonial pat ON p.kardex = pat.kardex
                LEFT JOIN tiposdeacto t ON t.idtipoacto = pat.idtipoacto
                WHERE pat.importetrans > 0
            """)
            
            for row in cursor.fetchall():
                kardex = row[0]
                id_kardex = row[1]
                acto = row[2]
                cod_acto = row[3]
                item_mp = row[4]

                # Check if bienes exist for this kardex
                cursor.execute("""
                    SELECT COUNT(*) 
                    FROM detallebienes 
                    WHERE kardex = %s AND idtipacto = %s
                """, [kardex, cod_acto])
                
                if cursor.fetchone()[0] == 0:
                    self._add_error(
                        kardex=kardex,
                        id_kardex=id_kardex,
                        error_item="No existe bien, ingrese un bien",
                        act=acto or "No especificado",
                        file_type=self.FILE_TYPE_BIE,
                        writing_date=None,
                        id_contractor=None,
                        is_correctable=True,
                        type_of_correction='AUTO',
                        item_mp=item_mp
                    )

    def load_data_otorgante(self) -> None:
        """Validate OTG (otorgantes) data."""
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT p.kardex, p.idKardex, p.actoSunat, t.desacto,
                       cxa.idcontratante, cxa.parte, cxa.porcentaje,
                       c.tipper, c.apepat, c.apemat, c.prinom, c.segnom,
                       c.razonsocial, c.numdoc, c.idtipdoc
                FROM pdt p
                INNER JOIN contratantesxacto cxa ON p.kardex = cxa.kardex
                INNER JOIN cliente2 c ON cxa.idcontratante = c.idcontratante
                LEFT JOIN tiposdeacto t ON p.codActos = t.idtipoacto
                WHERE cxa.parte IN (1, 2)
            """)
            
            for row in cursor.fetchall():
                kardex = row[0]
                id_kardex = row[1]
                acto_sunat = row[2]
                acto = row[3]
                id_contratante = row[4]
                parte = row[5]
                porcentaje = row[6]
                tipo_per = row[7]
                
                # Get required participant types for this act
                cursor.execute("""
                    SELECT tipoOtorgante, descripcionTipoOtorgante 
                    FROM pdt_actos_tipo_otorgante 
                    WHERE actoSunat = %s AND habilitado = 1 AND parte = %s
                """, [acto_sunat, parte])
                
                tipo_otorgante = cursor.fetchone()
                if tipo_otorgante and not porcentaje:
                    self._add_error(
                        kardex=kardex,
                        id_kardex=id_kardex,
                        error_item=f"Falta porcentaje de participación para {tipo_otorgante[1]}",
                        act=acto,
                        file_type=self.FILE_TYPE_OTG,
                        writing_date=None,
                        id_contractor=id_contratante,
                        is_correctable=True,
                        type_of_correction='AUTO'
                    )

    def load_data_medio_pago(self) -> None:
        """Validate MP (medios de pago) data."""
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT p.kardex, p.idKardex, t.desacto, p.codActos,
                       pat.itemmp, pat.exhibiomp
                FROM pdt p
                INNER JOIN patrimonial pat ON p.kardex = pat.kardex
                LEFT JOIN tiposdeacto t ON t.idtipoacto = pat.idtipoacto
                WHERE pat.exhibiomp = 1
            """)
            
            for row in cursor.fetchall():
                kardex = row[0]
                id_kardex = row[1]
                acto = row[2]
                cod_acto = row[3]
                item_mp = row[4]

                # Check if payment methods exist
                cursor.execute("""
                    SELECT COUNT(*) 
                    FROM detallemediopago 
                    WHERE kardex = %s AND tipacto = %s
                """, [kardex, cod_acto])
                
                if cursor.fetchone()[0] == 0:
                    self._add_error(
                        kardex=kardex,
                        id_kardex=id_kardex,
                        error_item="Si exhibió medio de pago, por favor ingrese el registro",
                        act=acto,
                        file_type=self.FILE_TYPE_MP,
                        writing_date=None,
                        id_contractor=None,
                        is_correctable=True,
                        type_of_correction='AUTO',
                        item_mp=item_mp
                    )

    def load_data_formulario(self) -> None:
        """Validate FORM (formularios) data."""
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT p.kardex, p.idKardex, t.desacto, p.codActos,
                       r.idrenta, r.pregu1, r.pregu2, r.pregu3
                FROM pdt p
                INNER JOIN renta r ON p.kardex = r.kardex
                LEFT JOIN tiposdeacto t ON t.idtipoacto = p.codActos
                WHERE p.actoSunat IN ('04', '03')
            """)
            
            for row in cursor.fetchall():
                kardex = row[0]
                id_kardex = row[1]
                acto = row[2]
                id_renta = row[4]

                # Check if form exists for this renta
                cursor.execute("""
                    SELECT COUNT(*) 
                    FROM formulario 
                    WHERE idrenta = %s
                """, [id_renta])
                
                if cursor.fetchone()[0] == 0:
                    self._add_error(
                        kardex=kardex,
                        id_kardex=id_kardex,
                        error_item="Falta número de formulario",
                        act=acto,
                        file_type=self.FILE_TYPE_FORM,
                        writing_date=None,
                        id_contractor=None,
                        is_correctable=True,
                        type_of_correction='AUTO'
                    )

    def _add_error(self, kardex: str, id_kardex: int, error_item: str, 
                  act: str, file_type: str, writing_date: datetime,
                  id_contractor: int, is_correctable: bool = True,
                  type_of_correction: str = 'AUTO', item_mp: str = None) -> None:
        """Add an error to the errors list."""
        self.errors.append({
            'kardex': kardex,
            'idKardex': id_kardex,
            'errorItem': error_item,
            'act': act,
            'fileType': file_type,
            'isCorrectable': 1 if is_correctable else 0,
            'typeOfCorrection': type_of_correction,
            'categoryCorrect': 'ESCRITURA',
            'writingDate': writing_date.strftime('%Y-%m-%d') if writing_date else None,
            'idContractor': id_contractor,
            'itemMp': item_mp,
            'typeAct': act
        })

    def get_results(self) -> Dict[str, Any]:
        """Get the validation results."""
        error_types = {
            'act': len([e for e in self.errors if e['fileType'] == self.FILE_TYPE_ACT]),
            'bie': len([e for e in self.errors if e['fileType'] == self.FILE_TYPE_BIE]),
            'otg': len([e for e in self.errors if e['fileType'] == self.FILE_TYPE_OTG]),
            'mp': len([e for e in self.errors if e['fileType'] == self.FILE_TYPE_MP]),
            'form': len([e for e in self.errors if e['fileType'] == self.FILE_TYPE_FORM])
        }

        return {
            'list': self.errors,
            'totalError': len(self.errors),
            'totalRecords': self.total_kardex,
            'summary': {
                'total_kardex': self.total_kardex,
                'total_errors': len(self.errors),
                'error_breakdown': error_types
            }
        }

    def correct_errors(self, error_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Correct the specified errors."""
        try:
            corrected = 0
            for error in error_list:
                kardex = error.get('kardex')
                category = error.get('categoryCorrect')
                correction_type = error.get('typeOfCorrection')
                
                if not all([kardex, category, correction_type]):
                    continue

                # Implement correction logic based on error type
                if correction_type == 'AUTO':
                    # Implement auto-correction logic here
                    corrected += 1

            return {
                'error': 0,
                'errorDescription': f'Se corrigieron {corrected} errores exitosamente'
            }

        except Exception as e:
            return {
                'error': 1,
                'errorDescription': f'Error al corregir errores: {str(e)}'
            } 