from dataclasses import dataclass
from datetime import date
from typing import Optional


@dataclass(frozen=True)
class RoStagedRecord:
    """In-memory row equivalent to legacy `ro` / `ro_not` staging tables."""

    id_kardex: int
    kardex: str
    id_tipo_kardex: int
    tipo_instrumento: str
    cod_acto: str
    uif_code: str
    numero_escritura: Optional[str]
    fecha_escritura: Optional[date]
    fecha_conclusion: Optional[date]
    tipo: str  # I = escritura en rango, C = complementario
