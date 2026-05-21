"""
Port of RoClass::loadData() — builds in-memory `ro` and `ro_not` staging lists.
"""

from datetime import date, datetime
from typing import List, Tuple

from notaria import models
from uif.services.staging import RoStagedRecord

TIPO_INSTRUMENTO_MAP = {
    1: "E",
    3: "T",
    4: "G",
}


def _tipo_instrumento(idtipkar: int) -> str:
    return TIPO_INSTRUMENTO_MAP.get(idtipkar, "SIN INICIAL")


def _parse_act_codes(codactos: str) -> List[str]:
    if not codactos:
        return []
    return [codactos[i : i + 3] for i in range(0, len(codactos), 3) if i + 3 <= len(codactos)]


def _stage_kardex_row(
    kardex,
    cod_acto: str,
    tipo_acto,
    tipo: str,
) -> RoStagedRecord:
    uif = tipo_acto.actouif if tipo_acto else ""
    return RoStagedRecord(
        id_kardex=kardex.idkardex,
        kardex=kardex.kardex,
        id_tipo_kardex=kardex.idtipkar,
        tipo_instrumento=_tipo_instrumento(kardex.idtipkar),
        cod_acto=cod_acto,
        uif_code=uif or "",
        numero_escritura=kardex.numescritura,
        fecha_escritura=kardex.fechaescritura,
        fecha_conclusion=kardex.fechaconclusion,
        tipo=tipo,
    )


class RoLoadDataService:
    """RoClass loadData equivalent without TRUNCATE/INSERT into MySQL staging tables."""

    def __init__(self):
        self.ro_records: List[RoStagedRecord] = []
        self.ro_not_records: List[RoStagedRecord] = []
        self._tipos_with_uif: dict = {}
        self._act_descriptions: dict = {}

    def load(self, start_date: date, end_date: date) -> Tuple[List[RoStagedRecord], List[RoStagedRecord]]:
        self.ro_records = []
        self.ro_not_records = []
        self._tipos_with_uif = {}

        kardex_qs = (
            models.Kardex.objects.filter(fechaescritura__range=[start_date, end_date])
            .exclude(idtipkar__in=[2, 5])
            .order_by("idtipkar", "fechaescritura", "numescritura")
        )

        all_act_codes = set()
        for kardex in kardex_qs:
            all_act_codes.update(_parse_act_codes(kardex.codactos or ""))

        if all_act_codes:
            for tipo in models.Tiposdeacto.objects.filter(
                idtipoacto__in=list(all_act_codes), actouif__isnull=False
            ).exclude(actouif=""):
                self._tipos_with_uif[tipo.idtipoacto] = tipo

        act_descriptions = {}
        if all_act_codes:
            for tipo in models.Tiposdeacto.objects.filter(idtipoacto__in=list(all_act_codes)):
                act_descriptions[tipo.idtipoacto] = tipo

        self._act_descriptions = act_descriptions

        for kardex in kardex_qs:
            self._stage_kardex_acts(kardex, tipo="I")

        self._load_complementary(start_date, end_date)

        return self.ro_records, self.ro_not_records

    def act_description(self, cod_acto: str) -> str:
        tipo = self._act_descriptions.get(cod_acto)
        if tipo and tipo.desacto:
            return tipo.desacto
        return f"Acto {cod_acto}"

    def _stage_kardex_acts(self, kardex, tipo: str) -> None:
        for cod_acto in _parse_act_codes(kardex.codactos or ""):
            tipo_acto = self._tipos_with_uif.get(cod_acto)
            record = _stage_kardex_row(kardex, cod_acto, tipo_acto, tipo=tipo)
            if tipo_acto:
                self.ro_records.append(record)
            else:
                self.ro_not_records.append(record)

    def _load_complementary(self, start_date: date, end_date: date) -> None:
        """
        Información complementaria (tipo C): firma en rango, escritura anterior al rango.
        Mirrors RoClass loadData second query.
        """
        kardex_with_firma_in_range = set()
        for contratante in (
            models.Contratantes.objects.exclude(fechafirma__isnull=True)
            .exclude(fechafirma="")
            .only("kardex", "fechafirma")
        ):
            firma = self._parse_fecha_firma(contratante.fechafirma)
            if firma and start_date <= firma <= end_date and contratante.kardex:
                kardex_with_firma_in_range.add(contratante.kardex)

        if not kardex_with_firma_in_range:
            return

        for kardex in models.Kardex.objects.filter(
            kardex__in=kardex_with_firma_in_range,
            fechaescritura__lt=start_date,
            fechaescritura__isnull=False,
        ).exclude(idtipkar__in=[2, 5]):
            self._stage_kardex_acts(kardex, tipo="C")

    @staticmethod
    def _parse_fecha_firma(value: str) -> date | None:
        if not value:
            return None
        for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(value.strip(), fmt).date()
            except ValueError:
                continue
        return None
