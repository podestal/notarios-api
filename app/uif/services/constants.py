"""RoClass constants (thresholds and exempt act codes)."""

import re

USD_THRESHOLD = 2500
USD_THRESHOLD_SOLES_WITHOUT_EXCHANGE = 7500

# Acts that always enter generateData regardless of patrimonial amount (RoClass WHERE).
SPECIAL_UIF_CODES = frozenset(
    {
        "037",
        "038",
        "039",
        "040",
        "041",
        "042",
        "043",
        "044",
        "045",
        "048",
        "050",
        "051",
        "052",
        "053",
        "054",
        "055",
    }
)

# Acts exempt from O-side / B-side amount equality checks.
ACTS_EXEMPT_OTORGANTE_AMOUNT = frozenset({"034", "028"})
ACTS_EXEMPT_BENEFICIARIO_AMOUNT = frozenset({"026", "027"})

# contratantesxacto.uif roles used in amount rules.
ROLE_OTORGANTE = "O"
ROLE_BENEFICIARIO = "B"
ROLE_REPRESENTANTE = "R"
AMOUNT_PARTICIPANT_ROLES = frozenset({ROLE_OTORGANTE, ROLE_BENEFICIARIO})

# Participant plane / validation roles (generateData contratantes query).
PLANE_PARTICIPANT_ROLES = frozenset({ROLE_OTORGANTE, ROLE_BENEFICIARIO, ROLE_REPRESENTANTE})
OPERATION_UIF_ROLE_PATTERN = re.compile(r"^[OGFN]")

# Document types allowed for Peruvian nationals (RoClass $arrDocumentsPE).
DOCUMENT_TYPES_PERU = frozenset({"1", "8", "10", "11"})

# Acts where incorrect RUC on juridical persons is auto-correctable (RoClass $arrActConst).
ACTS_CONSTITUCION_RUC_CORRECTABLE = frozenset({"037", "038", "039", "040", "042"})
