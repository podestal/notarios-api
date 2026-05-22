"""
RoClass cónyuge fields (items 40–43) — shared plane + validation logic.
"""

from typing import Optional, Tuple

from notaria.models import Cliente2, Contratantesxacto
from uif.services.ro_text import remplace_string_ro

SPOUSE_UIF_ROLES = ("B", "O", "G", "F", "N", "R")


def act_variants(cod_acto: str) -> set:
    cod = str(cod_acto or "").strip()
    return {cod, cod.zfill(3), cod.lstrip("0")}


def participacion_conyuge_sql_default(cliente: Cliente2) -> str:
    """PHP SELECT CASE for participacionConyuge before spouse lookup."""
    tipper = (cliente.tipper or "").strip().upper()
    conyuge = str(cliente.conyuge or "").strip()
    if tipper == "N" and conyuge:
        return "N"
    if tipper == "J" and not conyuge:
        return ""
    return "N"


def lookup_spouse_in_act(
    *,
    conyuge_idcliente: str,
    kardex: str,
    cod_acto: str,
) -> Optional[Cliente2]:
    """RoClass spouse SQL: cónyuge must appear as participant on the same act."""
    conyuge_id = str(conyuge_idcliente or "").strip()
    if not conyuge_id:
        return None
    spouse = Cliente2.objects.filter(idcliente=conyuge_id).first()
    if not spouse:
        return None
    rep_cxa = Contratantesxacto.objects.filter(
        idcontratante=spouse.idcontratante,
        kardex=kardex,
        idtipoacto__in=list(act_variants(cod_acto)),
        uif__in=SPOUSE_UIF_ROLES,
    ).first()
    return spouse if rep_cxa else None


def resolve_conyuge_fields(
    cliente: Cliente2,
    role: str,
    kardex: str,
    cod_acto: str,
) -> Tuple[str, str, str, str]:
    """
    Returns (participacion, apellido_paterno, apellido_materno, nombres) for items 40–43.
    Mirrors RoClass generateData participant branch.
    """
    participacion = participacion_conyuge_sql_default(cliente)
    ap_pat, ap_mat, nombres = "", "", ""

    if role == "R" or not str(cliente.conyuge or "").strip():
        return participacion, ap_pat, ap_mat, nombres

    spouse = lookup_spouse_in_act(
        conyuge_idcliente=str(cliente.conyuge).strip(),
        kardex=kardex,
        cod_acto=cod_acto,
    )
    if spouse:
        return (
            "S",
            remplace_string_ro(spouse.apepat or "", 1).upper()[:40],
            remplace_string_ro(spouse.apemat or "", 1).upper()[:40],
            remplace_string_ro(
                " ".join(filter(None, [spouse.prinom, spouse.segnom])), 1
            ).upper()[:40],
        )
    return "N", ap_pat, ap_mat, nombres
