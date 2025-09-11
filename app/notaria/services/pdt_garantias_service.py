from datetime import datetime
from typing import Dict, List, Any, Optional
from django.db import connection
from django.db.models import Q

class PdtGarantiasService:
    """Service for checking PDT errors in Garantías."""

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
        """Load and validate garantías data for the given date range."""
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
                    WHERE k.idtipkar = 4  -- Garantías
                    AND STR_TO_DATE(k.fechaconclusion, '%%d/%%m/%%Y') BETWEEN %s AND %s
                    ORDER BY k.kardex
                """, [start_date, end_date])
                
                kardex_records = {row[0]: row for row in cursor.fetchall()}
                self.total_kardex = len(kardex_records)

                if not kardex_records:
                    return

                # Get bienes info in bulk
                kardex_list = list(kardex_records.keys())
                placeholders = ','.join(['%s'] * len(kardex_list))
                cursor.execute(f"""
                    SELECT 
                        kardex,
                        COUNT(*) > 0 as has_bienes,
                        MAX(CASE WHEN tipob = 'BIENES' THEN 1 ELSE 0 END) as has_valid_tipo
                    FROM detallebienes 
                    WHERE kardex IN ({placeholders})
                    GROUP BY kardex
                """, kardex_list)
                bienes_info = {row[0]: (row[1], row[2]) for row in cursor.fetchall()}

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
                        cxa.parte,
                        CASE 
                            WHEN c.tipper = 'N' THEN CONCAT_WS(' ', 
                                NULLIF(c.prinom, ''),
                                NULLIF(c.segnom, ''),
                                NULLIF(c.apepat, ''),
                                NULLIF(c.apemat, '')
                            )
                            ELSE c.razonsocial
                        END as nombre,
                        c.numdoc,
                        c.tipper
                    FROM contratantesxacto cxa
                    JOIN cliente2 c ON cxa.idcontratante = c.idcontratante
                    WHERE cxa.kardex IN ({placeholders})
                """, kardex_list)
                contratantes_info = {}
                for row in cursor.fetchall():
                    kardex, id_contratante, porcentaje, parte, nombre, numdoc, tipo_per = row
                    if kardex not in contratantes_info:
                        contratantes_info[kardex] = []
                    # Format person identifier based on type
                    if tipo_per == 'N':  # Natural person
                        person_id = f"{nombre.strip()} ({numdoc})" if numdoc else nombre.strip()
                    else:  # Juridical person
                        person_id = f"{nombre.strip()} (RUC: {numdoc})" if numdoc else nombre.strip()
                    contratantes_info[kardex].append((id_contratante, porcentaje, parte, person_id))

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

                # Validate bienes
                has_bienes, has_valid_tipo = bienes_info.get(kardex, (False, False))
                if not has_bienes:
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
                elif not has_valid_tipo:
                    self._add_error(
                        kardex=kardex,
                        id_kardex=id_kardex,
                        error_item="El tipo de bien debe ser 'BIENES'",
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
                    has_acreedor = False
                    has_deudor = False
                    for id_contratante, porcentaje, parte, person_id in contratantes_info[kardex]:
                        # Validate porcentaje
                        if not porcentaje:
                            self._add_error(
                                kardex=kardex,
                                id_kardex=id_kardex,
                                error_item=f"Falta porcentaje de participación para {person_id}",
                                act=acto,
                                file_type=self.FILE_TYPE_OTG,
                                writing_date=None,
                                id_contractor=id_contratante,
                                is_correctable=True,
                                type_of_correction='AUTO'
                            )
                        
                        # Track roles
                        if parte == 1:  # Assuming 1 is acreedor
                            has_acreedor = True
                        elif parte == 2:  # Assuming 2 is deudor
                            has_deudor = True

                    # Validate required roles
                    if not has_acreedor:
                        self._add_error(
                            kardex=kardex,
                            id_kardex=id_kardex,
                            error_item="Falta registrar el Acreedor",
                            act=acto,
                            file_type=self.FILE_TYPE_OTG,
                            writing_date=None,
                            id_contractor=None,
                            is_correctable=True,
                            type_of_correction='AUTO'
                        )
                    if not has_deudor:
                        self._add_error(
                            kardex=kardex,
                            id_kardex=id_kardex,
                            error_item="Falta registrar el Deudor",
                            act=acto,
                            file_type=self.FILE_TYPE_OTG,
                            writing_date=None,
                            id_contractor=None,
                            is_correctable=True,
                            type_of_correction='AUTO'
                        )

        except Exception as e:
            raise Exception(f"Error loading garantías data: {str(e)}")

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
            'categoryCorrect': 'GARANTIA',
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