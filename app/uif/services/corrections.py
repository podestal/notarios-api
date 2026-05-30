"""
Subsanación de errores UIF (equivalente a correct_error_uif.php).
"""

import json
import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

from notaria import models
from uif.services.ro_validation_rules import (
    FIELD_MONTO_PARTICIPANTE,
    FIELD_OPORTUNIDAD_PAGO,
)

logger = logging.getLogger(__name__)

# correct_error_uif.php categoryCorrect auto-fixes (cliente2).
CATEGORY_CONSTITUCION_RUC = 1
CATEGORY_PROFESION = 2
CATEGORY_CARGO = 3
TIPDOC_SIN_RUC = 10
PROFESION_OTROS_ID = 53
PROFESION_OTROS_LABEL = "OTROS"
CARGO_OTROS_ID = 36
CARGO_OTROS_LABEL = "OTROS"


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

        total_applied = len(applied)
        return {
            "applied": applied,
            "skipped": skipped,
            "total_applied": total_applied,
            "total_skipped": len(skipped),
            # Legacy correct_error_uif.php response shape
            "error": 0,
            "errorDescription": f"Se afectaron {total_applied} registros.",
        }

    @staticmethod
    def parse_corrections_payload(data: Any) -> Optional[List[Dict[str, Any]]]:
        """Accept Django `{ corrections: [...] }` or legacy `{ listError: json }`."""
        if not isinstance(data, dict):
            return None

        corrections = data.get("corrections")
        if isinstance(corrections, list) and corrections:
            return corrections

        list_error = data.get("listError")
        if isinstance(list_error, str) and list_error.strip():
            try:
                list_error = json.loads(list_error)
            except json.JSONDecodeError:
                return None
        if isinstance(list_error, list) and list_error:
            return list_error

        return None

    @staticmethod
    def _parse_category(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _id_contratante(item: Dict[str, Any]) -> Optional[str]:
        raw = item.get("idContractor") or item.get("idContratante") or item.get("idcontratante")
        if raw is None:
            return None
        text = str(raw).strip()
        return text or None

    def _apply_one(self, item: Dict[str, Any]) -> Dict[str, Any]:
        category = self._parse_category(item.get("categoryCorrect"))
        if category == CATEGORY_CONSTITUCION_RUC:
            return self._correct_constitucion_ruc(item)
        if category == CATEGORY_PROFESION:
            return self._correct_profesion(item)
        if category == CATEGORY_CARGO:
            return self._correct_cargo(item)

        field_number = int(item.get("fieldNumber") or 0)
        kardex = item.get("kardex")
        codacto = item.get("codacto") or item.get("codActo") or item.get("tipoActo")
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

    def _correct_constitucion_ruc(self, item: Dict[str, Any]) -> Dict[str, Any]:
        id_contratante = self._id_contratante(item)
        if not id_contratante:
            return {**item, "applied": False, "reason": "idContractor requerido"}

        rows = models.Cliente2.objects.filter(idcontratante=id_contratante).update(
            idtipdoc=TIPDOC_SIN_RUC,
            numdoc="",
        )
        if not rows:
            return {**item, "applied": False, "reason": "cliente2 no encontrado"}

        return {
            **item,
            "applied": True,
            "field": "constitucion_ruc",
            "categoryCorrect": CATEGORY_CONSTITUCION_RUC,
        }

    def _correct_profesion(self, item: Dict[str, Any]) -> Dict[str, Any]:
        id_contratante = self._id_contratante(item)
        if not id_contratante:
            return {**item, "applied": False, "reason": "idContractor requerido"}

        rows = models.Cliente2.objects.filter(idcontratante=id_contratante).update(
            idprofesion=PROFESION_OTROS_ID,
            detaprofesion=PROFESION_OTROS_LABEL,
        )
        if not rows:
            return {**item, "applied": False, "reason": "cliente2 no encontrado"}

        return {
            **item,
            "applied": True,
            "field": "profesion",
            "categoryCorrect": CATEGORY_PROFESION,
        }

    def _correct_cargo(self, item: Dict[str, Any]) -> Dict[str, Any]:
        id_contratante = self._id_contratante(item)
        if not id_contratante:
            return {**item, "applied": False, "reason": "idContractor requerido"}

        rows = models.Cliente2.objects.filter(idcontratante=id_contratante).update(
            idcargoprofe=CARGO_OTROS_ID,
            profocupa=CARGO_OTROS_LABEL,
        )
        if not rows:
            return {**item, "applied": False, "reason": "cliente2 no encontrado"}

        return {
            **item,
            "applied": True,
            "field": "cargo",
            "categoryCorrect": CATEGORY_CARGO,
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
