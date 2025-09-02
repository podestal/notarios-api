"""
This module contains the UIF validation service that wraps the existing UIF validation logic.
"""

from typing import Dict, List, Optional
from datetime import datetime
from django.db.models import Q
from notaria.models import Kardex, Tiposdeacto, Patrimonial, Contratantes, Cliente2, Contratantesxacto
from notaria.views import KardexViewSet

class UIFValidationService:
    def __init__(self):
        self.kardex_viewset = KardexViewSet()
        # Cache for bulk-loaded data
        self._cache = {
            'patrimonial': {},
            'contratantes': {},
            'clientes': {},
            'contratantesxacto': {},
            'tipos_acto': {}
        }

    def bulk_validate_kardex(self, kardex_numbers: List[str]) -> Dict[str, Dict]:
        """
        Validate multiple kardex records at once.
        Returns a dictionary mapping kardex numbers to their validation results.
        """
        try:
            # Clear cache for new batch
            self._clear_cache()
            
            # Bulk fetch all kardex records
            kardex_records = Kardex.objects.filter(kardex__in=kardex_numbers)
            kardex_map = {k.kardex: k for k in kardex_records}
            
            # Get all unique act codes
            act_codes = set()
            for kardex in kardex_records:
                if kardex.codactos:
                    for i in range(0, len(kardex.codactos), 3):
                        if i + 3 <= len(kardex.codactos):
                            act_codes.add(kardex.codactos[i:i+3])

            # Bulk fetch all required data
            self._bulk_fetch_data(kardex_numbers, list(act_codes))

            # Process each kardex
            results = {}
            for kardex_number in kardex_numbers:
                kardex = kardex_map.get(kardex_number)
                if not kardex:
                    results[kardex_number] = self._get_empty_result()
                    continue

                results[kardex_number] = self._validate_single_kardex(kardex)

            return results

        except Exception as e:
            # Return error result for all kardex numbers
            return {
                kardex: {
                    'has_uif_errors': True,
                    'uif_errors': [{
                        'error_type': 'validation_error',
                        'error_description': f'Error validando UIF: {str(e)}'
                    }],
                    'uif_observations': [],
                    'patrimonial_data': {}
                }
                for kardex in kardex_numbers
            }

    def validate_kardex(self, kardex_number: str) -> Dict:
        """
        Validate a single kardex using the bulk validation method.
        """
        results = self.bulk_validate_kardex([kardex_number])
        return results.get(kardex_number, self._get_empty_result())

    def _clear_cache(self):
        """Clear the data cache."""
        self._cache = {
            'patrimonial': {},
            'contratantes': {},
            'clientes': {},
            'contratantesxacto': {},
            'tipos_acto': {}
        }

    def _bulk_fetch_data(self, kardex_numbers: List[str], act_codes: List[str]):
        """Bulk fetch all required data for validation using maps."""
        try:
            # Fetch all patrimonial data
            patrimonial_records = Patrimonial.objects.filter(
                kardex__in=kardex_numbers,
                idtipoacto__in=act_codes
            )
            for patrimonial in patrimonial_records:
                key = (patrimonial.kardex, str(patrimonial.idtipoacto).zfill(3))
                self._cache['patrimonial'][key] = {
                    'idmon': patrimonial.idmon,
                    'importetrans': patrimonial.importetrans,
                    'tipocambio': patrimonial.tipocambio,
                    'kardex': patrimonial.kardex
                }

            # Fetch all contratantes
            contratantes = Contratantes.objects.filter(
                kardex__in=kardex_numbers
            )
            for contratante in contratantes:
                if contratante.kardex not in self._cache['contratantes']:
                    self._cache['contratantes'][contratante.kardex] = []
                self._cache['contratantes'][contratante.kardex].append({
                    'idcontratante': contratante.idcontratante,
                    'kardex': contratante.kardex
                })

            # Get all contratante IDs
            contratante_ids = [c['idcontratante'] for contratantes_list in self._cache['contratantes'].values() for c in contratantes_list]

            # Fetch all cliente2 data
            clientes = Cliente2.objects.filter(
                idcontratante__in=contratante_ids
            )
            for cliente in clientes:
                self._cache['clientes'][cliente.idcontratante] = {
                    'nombre': cliente.nombre,
                    'razonsocial': cliente.razonsocial,
                    'idcontratante': cliente.idcontratante
                }

            # Fetch all contratantesxacto data
            contratantesxacto_records = Contratantesxacto.objects.filter(
                kardex__in=kardex_numbers,
                idtipoacto__in=act_codes,
                idcontratante__in=contratante_ids
            )
            for cxa in contratantesxacto_records:
                key = f"{cxa.kardex}_{cxa.idtipoacto}_{cxa.idcontratante}"
                self._cache['contratantesxacto'][key] = {
                    'monto': cxa.monto,
                    'kardex': cxa.kardex,
                    'idtipoacto': cxa.idtipoacto,
                    'idcontratante': cxa.idcontratante
                }

            # Fetch all tipos_acto data
            tipos_acto = Tiposdeacto.objects.filter(
                idtipoacto__in=act_codes
            )
            for tipo in tipos_acto:
                self._cache['tipos_acto'][tipo.idtipoacto] = {
                    'desacto': tipo.desacto,
                    'idtipoacto': tipo.idtipoacto
                }

        except Exception as e:
            print(f"Error in bulk fetch: {str(e)}")
            # Cache will remain empty or partial, but we'll continue

    def _validate_single_kardex(self, kardex: Kardex) -> Dict:
        """Validate a single kardex using cached data."""
        try:
            uif_errors = []
            uif_observations = []
            patrimonial_data = {}

            # Process each act code
            if kardex.codactos:
                act_codes = [kardex.codactos[i:i+3] for i in range(0, len(kardex.codactos), 3) if i + 3 <= len(kardex.codactos)]
                
                for act_code in act_codes:
                    # Get act description from cache
                    tipo_acto = self._cache['tipos_acto'].get(act_code)
                    act_description = tipo_acto.get('desacto') if tipo_acto else f'Acto {act_code}'

                    # Validate patrimonial data using cached data
                    patrimonial_errors = self._validate_patrimonial_data_cached(
                        kardex.kardex,
                        act_code,
                        act_description
                    )

                    if patrimonial_errors:
                        uif_errors.extend(patrimonial_errors)
                    else:
                        # Get patrimonial summary if no errors
                        summary = self._get_patrimonial_summary_cached(
                            kardex.kardex,
                            act_code
                        )
                        patrimonial_data[act_code] = summary

            # Check for basic validation errors
            if not kardex.numescritura or kardex.numescritura.strip() == '':
                uif_errors.append({
                    'error_type': 'missing_escritura_number',
                    'error_description': 'Número de escritura faltante'
                })

            if not kardex.fechaconclusion:
                uif_errors.append({
                    'error_type': 'missing_conclusion_date',
                    'error_description': 'Fecha de conclusión faltante'
                })

            return {
                'has_uif_errors': len(uif_errors) > 0,
                'uif_errors': uif_errors,
                'uif_observations': uif_observations,
                'patrimonial_data': patrimonial_data
            }

        except Exception as e:
            return {
                'has_uif_errors': True,
                'uif_errors': [{
                    'error_type': 'validation_error',
                    'error_description': f'Error validando UIF: {str(e)}'
                }],
                'uif_observations': [],
                'patrimonial_data': {}
            }

    def _validate_patrimonial_data_cached(self, kardex: str, act_code: str, act_description: str) -> List[Dict]:
        """Validate patrimonial data using cached data."""
        patrimonial_errors = []
        
        try:
            # Get patrimonial data from cache
            patrimonial_key = (kardex, act_code)
            patrimonial = self._cache['patrimonial'].get(patrimonial_key)
            
            if not patrimonial:
                return patrimonial_errors
            
            # Get contratantes from cache
            contratantes = self._cache['contratantes'].get(kardex, [])
            
            # Check currency code and amounts
            if patrimonial['idmon'] and patrimonial['idmon'] != '':
                if not patrimonial['importetrans'] or float(patrimonial['importetrans'] or 0) == 0:
                    for contratante in contratantes:
                        cliente = self._cache['clientes'].get(contratante['idcontratante'])
                        if cliente:
                            nombre = cliente['nombre'] or cliente['razonsocial'] or f"Contratante {contratante['idcontratante']}"
                            patrimonial_errors.append({
                                'error_type': 'currency_without_amount',
                                'error_description': f'{nombre}, código de moneda no se debe informar sin montos'
                            })
            
            # Check participant amounts
            if patrimonial['importetrans'] and float(patrimonial['importetrans'] or 0) > 0:
                total_contratante_amounts = 0
                
                for contratante in contratantes:
                    cliente = self._cache['clientes'].get(contratante['idcontratante'])
                    if not cliente:
                        continue
                        
                    nombre = cliente['nombre'] or cliente['razonsocial'] or f"Contratante {contratante['idcontratante']}"
                    
                    # Check contratante amount using cached data
                    contratante_acto_key = f"{kardex}_{act_code}_{contratante['idcontratante']}"
                    contratante_acto = self._cache['contratantesxacto'].get(contratante_acto_key)
                    
                    if contratante_acto and contratante_acto['monto']:
                        try:
                            monto = float(contratante_acto['monto'])
                            total_contratante_amounts += monto
                        except (ValueError, TypeError):
                            patrimonial_errors.append({
                                'error_type': 'invalid_amount',
                                'error_description': f'{nombre}: Monto inválido'
                            })
                    else:
                        patrimonial_errors.append({
                            'error_type': 'missing_participant_amount',
                            'error_description': f'{nombre} Monto por Participante'
                        })
                
                # Check total amounts match
                if total_contratante_amounts > 0:
                    patrimonial_total = float(patrimonial['importetrans'])
                    if abs(total_contratante_amounts - patrimonial_total) > 0.01:
                        if total_contratante_amounts > patrimonial_total:
                            patrimonial_errors.append({
                                'error_type': 'amount_mismatch',
                                'error_description': f'La suma de los montos de los contratantes otorgantes supera el monto total de la operación: {patrimonial_total:.2f}'
                            })
                        else:
                            patrimonial_errors.append({
                                'error_type': 'amount_mismatch',
                                'error_description': f'La suma de los montos de los contratantes beneficiarios supera el monto total de la operación: {patrimonial_total:.2f}'
                            })
            
            return patrimonial_errors
            
        except Exception as e:
            return [{
                'error_type': 'validation_error',
                'error_description': f'Error validando datos patrimoniales: {str(e)}'
            }]

    def _get_patrimonial_summary_cached(self, kardex: str, act_code: str) -> Dict:
        """Get patrimonial summary using cached data."""
        try:
            # Get patrimonial data from cache
            patrimonial_key = (kardex, act_code)
            patrimonial = self._cache['patrimonial'].get(patrimonial_key)
            
            if not patrimonial:
                return self._get_empty_patrimonial_summary()
            
            # Determine currency type and symbol
            if patrimonial['idmon'] == 2:  # Dollars
                currency_symbol = '$ '
                currency_description = 'DOLARES'
            else:  # Soles
                currency_symbol = 'S./ '
                currency_description = 'SOLES'
            
            # Calculate amount in dollars
            tipo_cambio = float(patrimonial['tipocambio']) if patrimonial['tipocambio'] else 1.0
            importe_trans = float(patrimonial['importetrans']) if patrimonial['importetrans'] else 0.0
            
            if patrimonial['idmon'] == 1:  # Soles - convert to dollars
                en_dolares = importe_trans / tipo_cambio if tipo_cambio > 0 else 0.0
            else:  # Already in dollars
                en_dolares = importe_trans
            
            return {
                'tipo_moneda': currency_description,
                'tipo_cambio': tipo_cambio,
                'patrimonial': importe_trans,
                'en_dolares': round(en_dolares, 2),
                'currency_symbol': currency_symbol
            }
            
        except Exception as e:
            return self._get_empty_patrimonial_summary()

    def _get_empty_patrimonial_summary(self) -> Dict:
        """Return empty patrimonial summary with default values."""
        return {
            'tipo_moneda': 'SOLES',
            'tipo_cambio': 0.0,
            'patrimonial': 0.0,
            'en_dolares': 0.0,
            'currency_symbol': 'S./ '
        }

    def _get_empty_result(self) -> Dict:
        """Return empty validation result."""
        return {
            'has_uif_errors': False,
            'uif_errors': [],
            'uif_observations': [],
            'patrimonial_data': {}
        } 