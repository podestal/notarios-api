"""
RoClass-style error payloads for the UIF dashboard (ItemRo / RowRo metadata).
"""

from typing import Any, Dict, Optional

ROW_TYPE_OPERATION = 1
ROW_TYPE_PARTICIPANT = 2

# Legacy codeElement values used in RoClass.
CODE_ELEMENT_AMOUNT_OTORGANTE = 600
CODE_ELEMENT_AMOUNT_BENEFICIARIO = 600
CODE_ELEMENT_MISSING_PAYMENT_ROWS = 590
CODE_ELEMENT_ESCRITURA = 5


def build_ro_error(
    *,
    id_kardex,
    kardex: str,
    act: str,
    error_type: str,
    error_description: str,
    field_number: int = 0,
    row_type: int = ROW_TYPE_OPERATION,
    code_element: int = 0,
    is_correctable: bool = False,
    type_of_correction: str = "",
    category_correct: str = "RO",
    details_error: str = "",
    id_contratante: Optional[str] = None,
    codacto: str = "",
    uif_code: str = "",
    detail_value: str = "",
) -> Dict[str, Any]:
    payload = {
        "idkardex": id_kardex,
        "kardex": kardex,
        "codacto": codacto,
        "act": act,
        "uif_code": uif_code,
        "status": "invalid",
        "error_type": error_type,
        "error_description": error_description,
        "fieldNumber": field_number,
        "rowType": row_type,
        "codeElement": code_element,
        "isCorrectable": 1 if is_correctable else 0,
        "typeOfCorrection": type_of_correction,
        "categoryCorrect": category_correct,
        "detailsError": details_error,
        "detailValue": detail_value,
    }
    if id_contratante is not None:
        payload["idContratante"] = id_contratante
    return payload


def group_errors_by_kardex(errors: list) -> Dict[str, list]:
    grouped: Dict[str, list] = {}
    for err in errors:
        key = err.get("kardex") or ""
        grouped.setdefault(key, []).append(err)
    return grouped
