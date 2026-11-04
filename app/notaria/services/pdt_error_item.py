"""
Shared PDT error item shape (legacy ItemClass / get_list_errors.php).

categoryCorrect / typeOfCorrection match Cpu/PDTClass.php + pdt/correct_error.php:
  1 Actos   — type 1: minuta > escritura → set patrimonial.nminuta
  2 Bienes  — type 1 relink itemmp; 2 insert default bien; 3 fill oespecific
  3 Otorg.  — type 1 RUC acto 22; 2 redistribute %; 3 insert renta
  4 Medio   — type 1 documentos=VOUCHER; 2 relink itemmp
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, Optional

from .pdt_dates import format_pdt_writing_date

# Categories (correct_error.php)
CATEGORY_ACTOS = 1
CATEGORY_BIENES = 2
CATEGORY_OTORGANTES = 3
CATEGORY_MEDIO_PAGO = 4

# typeOfCorrection within each category
TYPE_ACT_MINUTA = 1

TYPE_BIEN_RELINK = 1
TYPE_BIEN_INSERT = 2
TYPE_BIEN_DESCRIPCION = 3

TYPE_OTG_RUC = 1
TYPE_OTG_PORCENTAJE = 2
TYPE_OTG_RENTA = 3

TYPE_MP_DOCUMENTOS = 1
TYPE_MP_RELINK = 2


def format_pdt_writing_date_dmy(value: Any) -> Optional[str]:
    """DD/MM/YYYY — same as PDTClass::$formatFechaEscritura for writingDate."""
    ymd = format_pdt_writing_date(value)
    if not ymd:
        return None
    try:
        return datetime.strptime(ymd[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return None


def build_pdt_error_item(
    *,
    kardex: str,
    id_kardex: int,
    error_item: str,
    act: str,
    file_type: str,
    type_act: Any = None,
    item_mp: Any = None,
    writing_date: Any = None,
    id_contractor: Any = None,
    category_correct: int = 0,
    type_of_correction: int = 0,
    is_correctable: bool = False,
) -> Dict[str, Any]:
    """Build one get_list_errors.php row."""
    return {
        "kardex": kardex or "",
        "idKardex": id_kardex or 0,
        "errorItem": error_item or "",
        "act": act or "",
        "fileType": file_type or "",
        "isCorrectable": 1 if is_correctable else 0,
        "typeOfCorrection": int(type_of_correction or 0),
        "categoryCorrect": int(category_correct or 0),
        "writingDate": format_pdt_writing_date_dmy(writing_date) or "",
        "idContractor": id_contractor if id_contractor not in (None, "") else 0,
        "itemMp": item_mp if item_mp not in (None, "") else 0,
        # PHP typeAct = idtipoacto / tipacto code (used as tipoActo in Subsanar POST)
        "typeAct": "" if type_act in (None, "") else str(type_act),
    }
