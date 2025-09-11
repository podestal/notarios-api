from datetime import datetime
from typing import Dict, List, Any, Optional
from django.db import connection
from django.db.models import Q

class PdtVehicularesService:
    """Service for checking PDT errors in Vehicular acts."""

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

    def load_data(self) -> None:
        """Load and validate vehicular data for the given date range."""
        try:
            # Convert dates once
            try:
                # Try DD/MM/YYYY format first (like PHP)
                start_date = datetime.strptime(self.initial_date, '%d/%m/%Y').date()
                end_date = datetime.strptime(self.final_date, '%d/%m/%Y').date()
            except ValueError:
                # Try YYYY-MM-DD format as fallback
                start_date = datetime.strptime(self.initial_date, '%Y-%m-%d').date()
                end_date = datetime.strptime(self.final_date, '%Y-%m-%d').date()

            # First get kardex records - this is our base set
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT 
                        k.kardex,
                        k.idkardex,
                        k.fechaingreso,
                        k.codactos,
                        k.numescritura,
                        k.fechaescritura,
                        k.fechaconclusion,
                        p.itemmp,
                        p.idmon,
                        p.importetrans,
                        p.exhibiomp,
                        t.desacto,
                        t.actosunat,
                        IF(k.fechaescritura <= STR_TO_DATE(k.fechaconclusion,'%%d/%%m/%%Y'), 0, 1) AS fecha_validation
                    FROM kardex k
                    INNER JOIN patrimonial p ON k.kardex = p.kardex
                    LEFT JOIN tiposdeacto t ON t.idtipoacto = p.idtipoacto
                    WHERE k.idtipkar = 3  -- Vehicular acts
                    AND STR_TO_DATE(k.fechaconclusion, '%%d/%%m/%%Y') BETWEEN %s AND %s
                    ORDER BY k.kardex
                """, [start_date, end_date])
                
                kardex_records = {row[0]: row for row in cursor.fetchall()}
                self.total_kardex = len(kardex_records)

                if not kardex_records:
                    return

                # Get vehicle info in bulk
                kardex_list = list(kardex_records.keys())
                placeholders = ','.join(['%s'] * len(kardex_list))
                cursor.execute(f"""
                    SELECT 
                        kardex,
                        COUNT(*) > 0 as has_vehiculo,
                        MAX(CASE WHEN numplaca IS NOT NULL OR numserie IS NOT NULL OR motor IS NOT NULL THEN 1 ELSE 0 END) as has_valid_info
                    FROM detallevehicular 
                    WHERE kardex IN ({placeholders})
                    GROUP BY kardex
                """, kardex_list)
                vehiculo_info = {row[0]: (row[1], row[2]) for row in cursor.fetchall()}

                # Get medio pago info in bulk
                cursor.execute(f"""
                    SELECT DISTINCT kardex 
                    FROM detallemediopago 
                    WHERE kardex IN ({placeholders})
                """, kardex_list)
                has_medio_pago = {row[0] for row in cursor.fetchall()}

                # Get formulario info in bulk
                cursor.execute(f"""
                    SELECT DISTINCT r.kardex 
                    FROM renta r
                    JOIN formulario f ON f.idrenta = r.idrenta
                    WHERE r.kardex IN ({placeholders})
                """, kardex_list)
                has_formulario = {row[0] for row in cursor.fetchall()}

                # Get contratantes info in bulk
                cursor.execute(f"""
                    SELECT 
                        cxa.kardex,
                        cxa.idcontratante,
                        cxa.porcentaje,
                        COALESCE(c.razonsocial, CONCAT_WS(' ', c.apepat, c.apemat, c.prinom, c.segnom)) as nombre
                    FROM contratantesxacto cxa
                    JOIN cliente2 c ON cxa.idcontratante = c.idcontratante
                    WHERE cxa.kardex IN ({placeholders})
                """, kardex_list)
                contratantes_info = {}
                for row in cursor.fetchall():
                    if row[0] not in contratantes_info:
                        contratantes_info[row[0]] = []
                    contratantes_info[row[0]].append((row[1], row[2], row[3]))

            # Process validations in memory with pre-fetched data
            for kardex, data in kardex_records.items():
                id_kardex = data[1]
                num_escritura = data[4]
                fecha_escritura = data[5]
                acto = data[11]
                acto_sunat = data[12]
                fecha_validation = data[13]
                monto = data[9]
                exhibio_mp = data[10]
                item_mp = data[7]

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
                if fecha_validation == 1:
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

                # Validate vehicular details
                has_vehiculo, has_valid_info = vehiculo_info.get(kardex, (False, False))
                if not has_vehiculo:
                    self._add_error(
                        kardex=kardex,
                        id_kardex=id_kardex,
                        error_item="No existe vehículo, ingrese un vehículo",
                        act=acto or "No especificado",
                        file_type=self.FILE_TYPE_BIE,
                        writing_date=None,
                        id_contractor=None,
                        is_correctable=True,
                        type_of_correction='AUTO',
                        item_mp=item_mp
                    )
                elif not has_valid_info:
                    self._add_error(
                        kardex=kardex,
                        id_kardex=id_kardex,
                        error_item="Debe ingresar al menos placa, serie o motor del vehículo",
                        act=acto,
                        file_type=self.FILE_TYPE_BIE,
                        writing_date=None,
                        id_contractor=None,
                        is_correctable=True,
                        type_of_correction='AUTO',
                        item_mp=item_mp
                    )

                # Validate medio pago
                if exhibio_mp and kardex not in has_medio_pago:
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

                # Validate formulario for specific acts
                if acto_sunat in ('04', '03') and kardex not in has_formulario:
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

                # Validate contratantes
                if kardex in contratantes_info:
                    for id_contratante, porcentaje, nombre in contratantes_info[kardex]:
                        if not porcentaje:
                            self._add_error(
                                kardex=kardex,
                                id_kardex=id_kardex,
                                error_item=f"Falta porcentaje de participación para {nombre}",
                                act=acto,
                                file_type=self.FILE_TYPE_OTG,
                                writing_date=None,
                                id_contractor=id_contratante,
                                is_correctable=True,
                                type_of_correction='AUTO'
                            )

        except Exception as e:
            raise Exception(f"Error loading vehicular data: {str(e)}")

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
            'categoryCorrect': 'VEHICULAR',
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