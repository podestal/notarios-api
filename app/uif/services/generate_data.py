"""
RoClass::generateData threshold gate + loadDataRoNotUmbral (ro=0 → ro_not).
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Tuple

from uif.services.constants import (
    SPECIAL_UIF_CODES,
    USD_THRESHOLD,
    USD_THRESHOLD_SOLES_WITHOUT_EXCHANGE,
)
from uif.services.keys import patrimonial_key
from uif.services.staging import RoStagedRecord


def _to_decimal(value) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    return Decimal(str(value))


def _round2(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class RoGenerateDataService:
    """Marks which staged `ro` rows pass the legacy USD threshold (ro=1)."""

    def partition_by_threshold(
        self,
        ro_records: List[RoStagedRecord],
        patrimonial_map: Dict,
    ) -> Tuple[List[RoStagedRecord], List[RoStagedRecord]]:
        """
        Returns (eligible_ro, below_threshold_ro).
        Mirrors generateData WHERE + loadDataRoNotUmbral for ro=0 rows.
        """
        eligible: List[RoStagedRecord] = []
        below_threshold: List[RoStagedRecord] = []

        for staged in ro_records:
            patrimonial = patrimonial_map.get(patrimonial_key(staged.kardex, staged.cod_acto))
            if self.passes_threshold(staged.uif_code, patrimonial):
                eligible.append(staged)
            else:
                below_threshold.append(staged)

        return eligible, below_threshold

    @staticmethod
    def passes_threshold(uif_code: str, patrimonial) -> bool:
        uif = (uif_code or "").strip()
        if uif in SPECIAL_UIF_CODES:
            return True

        if patrimonial is None:
            return False

        idmon = str(patrimonial.idmon or "").strip()
        importe = _to_decimal(patrimonial.importetrans)

        if idmon == "2":
            return _round2(importe) >= Decimal(str(USD_THRESHOLD))

        # Soles (idmon = 1 or default): convert to USD for threshold.
        tipocambio_raw = patrimonial.tipocambio
        if tipocambio_raw is None or str(tipocambio_raw).strip() == "":
            threshold = Decimal(str(USD_THRESHOLD_SOLES_WITHOUT_EXCHANGE))
            rate = Decimal("1")
        else:
            threshold = Decimal(str(USD_THRESHOLD))
            rate = _round2(_to_decimal(tipocambio_raw))
            if rate <= 0:
                rate = Decimal("1")

        if rate <= 0:
            return False

        usd_amount = _round2(importe / rate)
        return usd_amount >= threshold
