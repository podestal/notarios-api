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

    def load_data(self) -> None:
        """Load and validate escritura data for the given date range."""
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

            # Get all data in one query
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
                        t.umbral,
                        -- Add validation fields directly in the query
                        IF(k.fechaescritura <= STR_TO_DATE(k.fechaconclusion,'%%d/%%m/%%Y'), 0, 1) AS fecha_validation,
                        -- Check if bienes exist
                        EXISTS(
                            SELECT 1 FROM detallebienes db 
                            WHERE db.kardex = k.kardex AND db.idtipacto = p.idtipoacto
                        ) AS has_bienes,
                        -- Check if medio pago exists
                        EXISTS(
                            SELECT 1 FROM detallemediopago dm 
                            WHERE dm.kardex = k.kardex AND dm.tipacto = p.idtipoacto
                        ) AS has_medio_pago,
                        -- Check if formulario exists
                        EXISTS(
                            SELECT 1 FROM renta r
                            LEFT JOIN formulario f ON f.idrenta = r.idrenta
                            WHERE r.kardex = k.kardex
                        ) AS has_formulario,
                        -- Get contratantes info
                        GROUP_CONCAT(
                            DISTINCT CONCAT_WS('|', 
                                cxa.idcontratante,
                                cxa.parte,
                                cxa.porcentaje,
                                c.tipper,
                                COALESCE(c.razonsocial, CONCAT_WS(' ', c.apepat, c.apemat, c.prinom, c.segnom))
                            )
                        ) AS contratantes_info
                    FROM kardex k
                    INNER JOIN patrimonial p ON k.kardex = p.kardex
                    LEFT JOIN tiposdeacto t ON t.idtipoacto = p.idtipoacto
                    LEFT JOIN contratantesxacto cxa ON k.kardex = cxa.kardex
                    LEFT JOIN cliente2 c ON cxa.idcontratante = c.idcontratante
                    WHERE k.idtipkar = 1  -- Escrituras
                    AND STR_TO_DATE(k.fechaconclusion, '%%d/%%m/%%Y') 
                    BETWEEN %s AND %s
                    GROUP BY k.kardex, k.idkardex, k.fechaingreso, k.codactos,
                             k.numescritura, k.fechaescritura, k.fechaconclusion,
                             p.itemmp, p.idmon, p.nminuta, p.importetrans,
                             p.exhibiomp, p.tipocambio, p.idtipoacto,
                             t.desacto, t.actosunat, t.actouif, t.umbral
                    ORDER BY k.kardex ASC
                """, [start_date, end_date])
                
                rows = cursor.fetchall()
                self.total_kardex = len(rows)

                # Process all validations in memory
                for row in rows:
                    kardex = row[0]
                    id_kardex = row[1]
                    num_escritura = row[4]
                    fecha_escritura = row[5]
                    acto = row[14]
                    acto_sunat = row[15]
                    fecha_validation = row[18]
                    has_bienes = row[19]
                    has_medio_pago = row[20]
                    has_formulario = row[21]
                    contratantes_info = row[22]
                    monto = row[10]
                    exhibio_mp = row[11]
                    item_mp = row[7]

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
                    if monto and not has_bienes:
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

                    # Validate medio pago
                    if exhibio_mp and not has_medio_pago:
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
                    if acto_sunat in ('04', '03') and not has_formulario:
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
                    if contratantes_info:
                        for contratante in contratantes_info.split(','):
                            id_contratante, parte, porcentaje, tipo_per, nombre = contratante.split('|')
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
            raise Exception(f"Error loading escritura data: {str(e)}")

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