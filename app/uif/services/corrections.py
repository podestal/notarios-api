"""
Subsanación de errores UIF (equivalente a correct_error_uif.php) — Phase 3 subset.
"""

import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List

from notaria import models
from uif.services.ro_validation_rules import (
    FIELD_MONTO_PARTICIPANTE,
    FIELD_OPORTUNIDAD_PAGO,
)

logger = logging.getLogger(__name__)


class UifCorrectionService:
    """Applies manual corrections sent from the RO error dashboard."""

    def apply(self, corrections: List[Dict[str, Any]]) -> Dict[str, Any]:
        applied = []
        skipped = []

        for item in corrections:
            try:
                result = self._apply_one(item)
                if result.get("applied"):
                    applied.append(result)
                else:
                    skipped.append(result)
            except Exception as exc:
                logger.warning("Correction failed: %s", exc, exc_info=True)
                skipped.append({**item, "reason": str(exc)})

        return {
            "applied": applied,
            "skipped": skipped,
            "total_applied": len(applied),
            "total_skipped": len(skipped),
        }

    def _apply_one(self, item: Dict[str, Any]) -> Dict[str, Any]:
        field_number = int(item.get("fieldNumber") or 0)
        kardex = item.get("kardex")
        codacto = item.get("codacto") or item.get("codActo")
        correction_type = (item.get("typeOfCorrection") or "").upper()

        if not kardex or not codacto:
            return {**item, "applied": False, "reason": "kardex y codacto son requeridos"}

        if field_number == FIELD_MONTO_PARTICIPANTE:
            return self._correct_participant_amount(item, kardex, codacto, correction_type)

        if field_number == FIELD_OPORTUNIDAD_PAGO:
            return self._correct_oportunidad(item, kardex, codacto)

        return {
            **item,
            "applied": False,
            "reason": f"Corrección no implementada para fieldNumber={field_number}",
        }

    def _correct_participant_amount(
        self, item: Dict[str, Any], kardex: str, codacto: str, correction_type: str
    ) -> Dict[str, Any]:
        id_contratante = item.get("idContratante") or item.get("idcontratante")
        new_monto = item.get("monto") or item.get("value")
        if not id_contratante or new_monto is None:
            return {**item, "applied": False, "reason": "idContratante y monto requeridos"}

        cxa = models.Contratantesxacto.objects.filter(
            kardex=kardex,
            idcontratante=str(id_contratante),
            idtipoacto__in=[codacto, str(codacto).zfill(3)],
        ).first()
        if not cxa:
            return {**item, "applied": False, "reason": "contratantesxacto no encontrado"}

        monto = Decimal(str(new_monto)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        cxa.monto = format(monto, "f")
        cxa.save(update_fields=["monto"])
        return {**item, "applied": True, "field": "monto_participante"}

    def _correct_oportunidad(self, item: Dict[str, Any], kardex: str, codacto: str) -> Dict[str, Any]:
        descripcion = item.get("descripcion") or item.get("des_idoppago")
        idoppago = item.get("idoppago") or item.get("oportunidadPago")
        pat = models.Patrimonial.objects.filter(
            kardex=kardex, idtipoacto__in=[codacto, str(codacto).zfill(3)]
        ).first()
        if not pat:
            return {**item, "applied": False, "reason": "patrimonial no encontrado"}

        update_fields = []
        if idoppago is not None:
            pat.idoppago = str(idoppago)
            update_fields.append("idoppago")
        if descripcion is not None:
            pat.des_idoppago = str(descripcion)
            update_fields.append("des_idoppago")
        if not update_fields:
            return {**item, "applied": False, "reason": "Sin datos de corrección"}

        pat.save(update_fields=update_fields)
        return {**item, "applied": True, "field": "oportunidad_pago"}
