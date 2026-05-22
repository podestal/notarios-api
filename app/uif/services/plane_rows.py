"""
RoClass generateData → _arrObjRo plane rows (generateFileRo parity).
"""

import logging
import re
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple

from notaria.models import (
    Cargoprofe,
    Cliente2,
    Contratantes,
    Contratantesxacto,
    Detallebienes,
    Detallemediopago,
    Detallevehicular,
    Nacionalidades,
    Patrimonial,
    Profesiones,
    Tipodocumento,
    Tipoestacivil,
    Ubigeo,
)
from uif.models import Ciiu, FpagoUif, Mediospago, Monedas
from uif.services.complementary import (
    escritura_before_range,
    firma_in_report_range,
    group_medios_for_act,
    has_medios_for_act,
)
from uif.services.conyuge_fields import resolve_conyuge_fields
from uif.services.keys import patrimonial_key
from uif.services.ro_text import remplace_string_ro

logger = logging.getLogger(__name__)

# PHP generateFileRo STR_PAD_LEFT (L) / STR_PAD_RIGHT (R) per field number.
PLANE_FIELD_PAD = {
    1: "L",
    2: "L",
    3: "L",
    4: "R",
    5: "R",
    6: "L",
    7: "L",
    8: "L",
    9: "L",
    10: "L",
    11: "L",
    12: "L",
    13: "L",
    14: "L",
    15: "L",
    16: "L",
    17: "L",
    18: "L",
    19: "L",
    20: "L",
    21: "R",
    22: "L",
    23: "R",
    24: "R",
    25: "R",
    26: "L",
    27: "L",
    28: "L",
    29: "L",
    30: "R",
    31: "L",
    32: "L",
    33: "L",
    34: "L",
    35: "R",
    36: "L",
    37: "L",
    38: "L",
    39: "R",
    40: "L",
    41: "R",
    42: "R",
    43: "R",
    44: "L",
    45: "L",
    46: "L",
    47: "L",
    48: "R",
    49: "R",
    50: "L",
    51: "L",
    52: "L",
    53: "L",
    54: "L",
    55: "L",
    56: "L",
    57: "L",
}

OPERATION_ROLE_PATTERN = re.compile(r"^[OGFN]")
PARTICIPANT_UIF_ROLES = frozenset({"O", "B", "R"})
ISO_MONEDA_FALLBACK = {1: "PEN", 2: "USD"}


def _format_amount(value, decimals: int = 2) -> str:
    try:
        d = Decimal(str(value)).quantize(Decimal(10) ** -decimals, rounding=ROUND_HALF_UP)
        return format(d, f".{decimals}f")
    except Exception:
        return "0.00"


def _format_date_yyyymmdd(value) -> str:
    if not value:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%Y%m%d")
    text = str(value).strip()
    digits = re.sub(r"\D", "", text)
    if len(digits) >= 8:
        if "-" in text[:10]:
            return digits[:8]
        if len(digits) == 8 and int(digits[4:6]) <= 12:
            return digits[:8]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text[:10], fmt).strftime("%Y%m%d")
        except ValueError:
            continue
    return digits[:8] if len(digits) >= 8 else digits


def _format_date_ddmmyyyy(value) -> str:
    if not value:
        return ""
    text = str(value).strip()
    if text in ("00000000", "0"):
        return ""
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(text[:10], fmt).strftime("%d%m%Y")
        except ValueError:
            continue
    digits = re.sub(r"\D", "", text)
    if len(digits) == 8:
        if int(digits[4:6]) <= 12 and int(digits[:4]) > 31:
            return datetime.strptime(digits, "%Y%m%d").strftime("%d%m%Y")
        return digits
    return digits[:8] if len(digits) >= 8 else digits


def _conclusion_flag(fecha_conclusion) -> str:
    if fecha_conclusion is None:
        return "N"
    text = str(fecha_conclusion).strip()
    return "N" if text in ("", "None") else "C"


class PlaneRowBuilder:
    """Builds plane-file rows exactly like RoClass::_arrObjRo (medios + participantes)."""

    def __init__(self):
        self._fpago_map: Optional[Dict[str, str]] = None
        self._medio_map: Optional[Dict[int, str]] = None
        self._moneda_map: Optional[Dict[int, str]] = None
        self._tipodoc_map: Optional[Dict[int, str]] = None
        self._prof_map: Optional[Dict[int, str]] = None
        self._cargo_map: Optional[Dict[int, str]] = None
        self._civil_map: Optional[Dict[int, str]] = None
        self._nacion_map: Optional[Dict[str, str]] = None
        self._ciiu_map: Optional[Dict[str, str]] = None
        self._ubigeo_cache: Dict[str, Ubigeo] = {}

    @property
    def fpago_map(self) -> Dict[str, str]:
        if self._fpago_map is None:
            self._fpago_map = {str(r.id_fpago): (r.codigo or "") for r in FpagoUif.objects.all()}
        return self._fpago_map

    @property
    def medio_map(self) -> Dict[int, str]:
        if self._medio_map is None:
            self._medio_map = {int(m.codmepag): (m.uif or "") for m in Mediospago.objects.all()}
        return self._medio_map

    @property
    def moneda_map(self) -> Dict[int, str]:
        if self._moneda_map is None:
            self._moneda_map = {
                int(m.idmon): (m.codigo or ISO_MONEDA_FALLBACK.get(int(m.idmon), "PEN"))
                for m in Monedas.objects.all()
            }
        return self._moneda_map

    @property
    def tipodoc_map(self) -> Dict[int, str]:
        if self._tipodoc_map is None:
            self._tipodoc_map = {}
            for row in Tipodocumento.objects.all():
                raw = (row.codtipdoc or "").strip()
                try:
                    self._tipodoc_map[row.idtipdoc] = str(int(raw))
                except ValueError:
                    self._tipodoc_map[row.idtipdoc] = raw
        return self._tipodoc_map

    @property
    def prof_map(self) -> Dict[int, str]:
        if self._prof_map is None:
            self._prof_map = {p.idprofesion: (p.codprof or "") for p in Profesiones.objects.all()}
        return self._prof_map

    @property
    def cargo_map(self) -> Dict[int, str]:
        if self._cargo_map is None:
            self._cargo_map = {
                c.idcargoprofe: (c.codcargoprofe or "") for c in Cargoprofe.objects.all()
            }
        return self._cargo_map

    @property
    def civil_map(self) -> Dict[int, str]:
        if self._civil_map is None:
            self._civil_map = {
                t.idestcivil: str(t.idestcivil) for t in Tipoestacivil.objects.all()
            }
        return self._civil_map

    @property
    def nacion_map(self) -> Dict[str, str]:
        if self._nacion_map is None:
            self._nacion_map = {}
            for n in Nacionalidades.objects.all():
                key = str(n.idnacionalidad)
                self._nacion_map[key] = (n.codnacion or "")[:2]
        return self._nacion_map

    @property
    def ciiu_map(self) -> Dict[str, str]:
        if self._ciiu_map is None:
            self._ciiu_map = {c.coddivi: c.coddivi for c in Ciiu.objects.all()}
        return self._ciiu_map

    def build_rows(
        self,
        ro_records: List[Dict[str, Any]],
        range_start: Optional[date] = None,
        range_end: Optional[date] = None,
    ) -> List[Dict[str, str]]:
        rows: List[Dict[str, str]] = []
        code_row = 0
        registration_number = 0

        kardex_list = list({r["kardex"] for r in ro_records})
        patrimonial_by_key = self._load_patrimonial(kardex_list)
        detalle_medio_by_kardex = self._load_detalle_medio(kardex_list)
        contratantes_by_kardex = self._load_contratantes(kardex_list)

        for ro in ro_records:
            tipo = str(ro.get("tipo", "I"))
            kardex = ro["kardex"]
            cod_acto = str(ro.get("codacto", ""))
            pat = patrimonial_by_key.get(patrimonial_key(kardex, cod_acto))
            op_ctx = self._operation_context(ro, pat)
            detalle_list = detalle_medio_by_kardex.get(kardex, [])

            if tipo == "C":
                if range_start is None or range_end is None:
                    continue
                if not escritura_before_range(kardex, range_start):
                    continue
                if not has_medios_for_act(kardex, cod_acto, detalle_list):
                    continue
                _, tipo_acto_medio = group_medios_for_act(kardex, cod_acto, detalle_list)
                registration_number += 1
                reg_num = registration_number
                participants = self._load_participants_complementary(
                    kardex,
                    tipo_acto_medio,
                    range_start,
                    range_end,
                    contratantes_by_kardex.get(kardex, []),
                )
                for participant in participants:
                    code_row += 1
                    row = self._base_operation_row(op_ctx, reg_num, code_row)
                    row.update(
                        self._participant_fields(
                            participant,
                            op_ctx,
                            kardex,
                            tipo_acto_medio,
                            is_complementary=True,
                        )
                    )
                    row["kardex"] = kardex
                    rows.append(row)
                continue

            if tipo != "I":
                continue

            inscripcion, zona_bien, partida_bien = self._bien_registral(
                kardex, cod_acto, ro.get("tipo_instrumento") or ro.get("idtipkar")
            )

            registration_number += 1
            reg_num = registration_number

            medios = self._group_medios(kardex, cod_acto, detalle_list)
            tipo_acto_medio = cod_acto

            for medio in medios:
                code_row += 1
                tipo_acto_medio = str(medio.get("tipacto") or cod_acto)
                row = self._base_operation_row(op_ctx, reg_num, code_row)
                row.update(
                    self._medio_payment_fields(medio, op_ctx, inscripcion, zona_bien, partida_bien)
                )
                row["kardex"] = kardex
                rows.append(row)

            participants = self._load_participants(
                kardex, tipo_acto_medio, contratantes_by_kardex.get(kardex, [])
            )
            for participant in participants:
                code_row += 1
                row = self._base_operation_row(op_ctx, reg_num, code_row)
                row.update(
                    self._participant_fields(
                        participant, op_ctx, kardex, tipo_acto_medio, is_complementary=False
                    )
                )
                row["kardex"] = kardex
                rows.append(row)

        return rows

    def _load_participants_complementary(
        self,
        kardex: str,
        cod_acto: str,
        range_start: date,
        range_end: date,
        contratantes: List[Contratantes],
    ) -> List[dict]:
        act_variants = {cod_acto, str(cod_acto).zfill(3), str(cod_acto).lstrip("0")}
        cxa_list = Contratantesxacto.objects.filter(
            kardex=kardex, idtipoacto__in=list(act_variants)
        )
        contratante_by_id = {c.idcontratante: c for c in contratantes}
        cliente_ids = [c.idcontratante for c in cxa_list if c.idcontratante]
        clientes = {
            c.idcontratante: c for c in Cliente2.objects.filter(idcontratante__in=cliente_ids)
        }

        participants = []
        for cxa in cxa_list:
            role = (cxa.uif or "").strip().upper()
            if role not in PARTICIPANT_UIF_ROLES:
                continue
            contratante = contratante_by_id.get(cxa.idcontratante)
            if not contratante or not firma_in_report_range(
                contratante.fechafirma, range_start, range_end
            ):
                continue
            cliente = clientes.get(cxa.idcontratante)
            if not cliente:
                continue
            participants.append(
                {"cxa": cxa, "cliente": cliente, "contratante": contratante}
            )
        participants.sort(key=lambda p: (p["cxa"].uif or ""), reverse=True)
        return participants

    def _load_patrimonial(self, kardex_list: List[str]) -> Dict[Tuple[str, str], Patrimonial]:
        result = {}
        if not kardex_list:
            return result
        for pat in Patrimonial.objects.filter(kardex__in=kardex_list):
            key = patrimonial_key(pat.kardex, str(pat.idtipoacto))
            result[key] = pat
        return result

    def _load_detalle_medio(self, kardex_list: List[str]) -> Dict[str, List[Detallemediopago]]:
        grouped: Dict[str, List[Detallemediopago]] = defaultdict(list)
        if not kardex_list:
            return grouped
        for det in Detallemediopago.objects.filter(kardex__in=kardex_list):
            grouped[det.kardex].append(det)
        return grouped

    def _load_contratantes(self, kardex_list: List[str]) -> Dict[str, List[Contratantes]]:
        grouped: Dict[str, List[Contratantes]] = defaultdict(list)
        if not kardex_list:
            return grouped
        for c in Contratantes.objects.filter(kardex__in=kardex_list):
            grouped[c.kardex].append(c)
        return grouped

    def _operation_context(self, ro: Dict[str, Any], pat: Optional[Patrimonial]) -> dict:
        idmon = int(pat.idmon or 1) if pat else 1
        moneda = self.moneda_map.get(idmon) or ISO_MONEDA_FALLBACK.get(idmon, "PEN")
        monto = _format_amount(pat.importetrans if pat else 0)
        tipo_cambio = _format_amount(pat.tipocambio if pat and pat.tipocambio else "0.00")
        if pat and (not pat.tipocambio or str(pat.tipocambio).strip() == ""):
            tipo_cambio = "0.00"

        fpago_codigo = ""
        oportunidad = ""
        des_opp = ""
        if pat:
            fpago_codigo = (self.fpago_map.get(str(pat.fpago or "").strip(), "") or "")[:1]
            oportunidad = str(pat.idoppago or "").strip()[:2]
            if str(pat.idoppago or "").strip() == "99":
                des_opp = remplace_string_ro(
                    pat.des_idoppago or "NO PRECISA"
                ).upper()[:40]
            else:
                des_opp = ""

        fecha_esc = _format_date_yyyymmdd(ro.get("fechaescritura"))
        fecha_conc = ro.get("fechaconclusion")
        conclusion = _conclusion_flag(fecha_conc)

        return {
            "tipo_envio": str(ro.get("tipo", "I") or "I")[:1],
            "ipnp": str(ro.get("tipo_instrumento") or "")[:2],
            "num_escritura": str(ro.get("numescritura") or ""),
            "fecha_escritura": fecha_esc,
            "conclusion": conclusion,
            "tipo_operacion": str(ro.get("uif_code") or "")[:3],
            "forma_pago": fpago_codigo,
            "oportunidad": oportunidad,
            "descripcion_oportunidad": des_opp,
            "moneda": moneda,
            "monto_operacion": monto,
            "tipo_cambio": tipo_cambio,
            "idmon": idmon,
        }

    def _bien_registral(
        self, kardex: str, cod_acto: str, tipo_instrumento
    ) -> Tuple[str, str, str]:
        ipnp = str(tipo_instrumento or "")[:1]
        act_variants = {cod_acto, str(cod_acto).zfill(3), str(cod_acto).lstrip("0")}

        if ipnp == "T":
            qs = Detallevehicular.objects.filter(kardex=kardex)
            for row in qs:
                if str(row.idtipacto or "") in act_variants:
                    has = bool(
                        str(row.idsedereg or "").strip()
                        and str(row.pregistral or "").strip()
                    )
                    return (
                        "I" if has else "N",
                        str(row.idsedereg or "")[:2],
                        remplace_string_ro(row.pregistral or "")[:12],
                    )
        else:
            for row in Detallebienes.objects.filter(kardex=kardex):
                if str(row.idtipacto or "") in act_variants:
                    has = bool(
                        str(row.idsedereg or "").strip()
                        and str(row.pregistral or "").strip()
                    )
                    return (
                        "I" if has else "N",
                        str(row.idsedereg or "")[:2],
                        remplace_string_ro(row.pregistral or "")[:12],
                    )
        return "N", "", ""

    def _group_medios(
        self, kardex: str, cod_acto: str, detalles: List[Detallemediopago]
    ) -> List[dict]:
        act_variants = {cod_acto, str(cod_acto).zfill(3), str(cod_acto).lstrip("0")}
        grouped: Dict[Tuple, dict] = {}
        for det in detalles:
            if str(det.tipacto or "") not in act_variants:
                continue
            key = (det.codmepag, det.tipacto)
            if key not in grouped:
                grouped[key] = {
                    "tipacto": det.tipacto,
                    "codmepag": det.codmepag,
                    "monto": Decimal("0"),
                }
            grouped[key]["monto"] += Decimal(str(det.importemp or 0))
        return list(grouped.values())

    def _base_operation_row(self, op: dict, reg_num: int, code_row: int) -> Dict[str, str]:
        return {
            "item_1": str(code_row),
            "item_2": str(reg_num),
            "item_3": op["tipo_envio"],
            "item_4": op["ipnp"],
            "item_5": op["num_escritura"][:6],
            "item_6": op["fecha_escritura"],
            "item_7": "",
            "item_8": "",
            "item_9": op["conclusion"],
            "item_10": "",
            "item_11": "U",
            "item_12": "",
            "item_13": "",
            "item_14": "",
            "item_15": "",
            "item_16": "",
            "item_17": "",
            "item_18": "",
            "item_19": "",
            "item_20": "",
            "item_21": "",
            "item_22": "",
            "item_23": "",
            "item_24": "",
            "item_25": "",
            "item_26": "",
            "item_27": "",
            "item_28": "",
            "item_29": "",
            "item_30": "",
            "item_31": "",
            "item_32": "",
            "item_33": "",
            "item_34": "",
            "item_35": "",
            "item_36": "",
            "item_37": "",
            "item_38": "",
            "item_39": "",
            "item_40": "",
            "item_41": "",
            "item_42": "",
            "item_43": "",
            "item_44": "",
            "item_45": op["tipo_operacion"],
            "item_46": "",
            "item_47": "",
            "item_48": "",
            "item_49": "",
            "item_50": op["moneda"],
            "item_51": op["monto_operacion"],
            "item_52": "0.00",
            "item_53": "0.00",
            "item_54": op["tipo_cambio"],
            "item_55": "",
            "item_56": "",
            "item_57": "",
        }

    def _medio_payment_fields(
        self, medio: dict, op: dict, inscripcion: str, zona: str, partida: str
    ) -> Dict[str, str]:
        codigo_fondo = ""
        if medio.get("codmepag") is not None:
            codigo_fondo = (self.medio_map.get(int(medio["codmepag"])) or "")[:2]
        monto_fondo = _format_amount(medio.get("monto", 0))
        return {
            "item_44": codigo_fondo,
            "item_46": op["forma_pago"],
            "item_47": op["oportunidad"],
            "item_48": op["descripcion_oportunidad"],
            "item_49": "",
            "item_50": op["moneda"],
            "item_51": op["monto_operacion"],
            "item_52": "0.00",
            "item_53": monto_fondo,
            "item_54": op["tipo_cambio"],
            "item_55": inscripcion,
            "item_56": zona[:2],
            "item_57": partida[:12],
        }

    def _load_participants(
        self, kardex: str, cod_acto: str, contratantes: List[Contratantes]
    ) -> List[dict]:
        act_variants = {cod_acto, str(cod_acto).zfill(3), str(cod_acto).lstrip("0")}
        cxa_list = Contratantesxacto.objects.filter(kardex=kardex, idtipoacto__in=list(act_variants))
        contratante_by_id = {c.idcontratante: c for c in contratantes}
        cliente_ids = [c.idcontratante for c in cxa_list if c.idcontratante]
        clientes = {
            c.idcontratante: c for c in Cliente2.objects.filter(idcontratante__in=cliente_ids)
        }

        participants = []
        for cxa in cxa_list:
            role = (cxa.uif or "").strip().upper()
            if role not in PARTICIPANT_UIF_ROLES:
                continue
            cliente = clientes.get(cxa.idcontratante)
            if not cliente:
                continue
            participants.append(
                {
                    "cxa": cxa,
                    "cliente": cliente,
                    "contratante": contratante_by_id.get(cxa.idcontratante),
                }
            )
        participants.sort(key=lambda p: (p["cxa"].uif or ""), reverse=True)
        return participants

    def _participant_fields(
        self,
        participant: dict,
        op: dict,
        kardex: str,
        cod_acto: str,
        is_complementary: bool = False,
    ) -> Dict[str, str]:
        cxa = participant["cxa"]
        cliente = participant["cliente"]
        contratante = participant["contratante"]
        role = (cxa.uif or "").strip().upper()
        tipper = (cliente.tipper or "N").upper()

        representante = role if role == "R" else ""
        persona_operacion = role if OPERATION_ROLE_PATTERN.match(role) else ""
        persona_afavor = role if role == "B" else ""

        persona_que_representa = self._persona_que_representa(contratante, role)
        tipo_repr = ""
        if role == "R" and contratante and contratante.inscrito is not None:
            tipo_repr = "2" if str(contratante.inscrito) == "0" else "1"

        residente = str(cliente.residente or "").strip()
        condicion_residencia = "1" if residente in ("", "1") else "2"
        tipo_persona = "1" if tipper == "N" else "3"

        cod_tipo_doc = ""
        if tipper == "N" and cliente.idtipdoc:
            cod_tipo_doc = self.tipodoc_map.get(cliente.idtipdoc, "")

        numero_doc = str(cliente.numdoc or "") if tipper == "N" else ""
        numero_ruc = ""
        if tipper == "J":
            if cliente.idtipdoc == 8:
                numero_ruc = str(cliente.numdoc or "")
            elif cliente.idtipdoc == 10:
                numero_ruc = "99999999999"

        tipo_persona_code = "1" if tipper == "N" else "3"
        if tipper == "N":
            apepat = remplace_string_ro(cliente.apepat or "", tipo_persona_code)
            apemat = remplace_string_ro(cliente.apemat or "", 1)
            nombres = remplace_string_ro(
                " ".join(filter(None, [cliente.prinom, cliente.segnom])), 1
            )
        else:
            apepat = remplace_string_ro(cliente.razonsocial or "", tipo_persona_code)
            apemat = ""
            nombres = ""

        cod_nacion = ""
        if tipper == "N" and cliente.nacionalidad:
            cod_nacion = self.nacion_map.get(str(cliente.nacionalidad).strip(), "")[:2]

        fecha_nac = ""
        if tipper == "N" and cliente.cumpclie:
            fecha_nac = _format_date_yyyymmdd(cliente.cumpclie)

        cod_estado = ""
        if tipper == "N" and cliente.idestcivil:
            cod_estado = self.civil_map.get(int(cliente.idestcivil), str(cliente.idestcivil))

        cod_prof = ""
        if tipper == "N" and cliente.idprofesion:
            cod_prof = (self.prof_map.get(int(cliente.idprofesion)) or "")[:3]

        objeto_social = ""
        if tipper == "J":
            objeto_social = remplace_string_ro(cliente.contacempresa or "", 1)

        cod_ciiu = ""
        if tipper == "J" and cliente.actmunicipal:
            cod_ciiu = self.ciiu_map.get(str(cliente.actmunicipal).strip(), "")[:4]

        cod_cargo = ""
        if tipper == "N" and cliente.idcargoprofe:
            cod_cargo = (self.cargo_map.get(int(cliente.idcargoprofe)) or "")[:3]

        zona_reg = ""
        partida_reg = ""
        if role == "R" and contratante:
            zona_reg = str(contratante.idsedereg or "").zfill(2)[:2]
            partida_reg = remplace_string_ro(contratante.numpartida or "")[:12]

        if tipper == "N":
            direccion = remplace_string_ro(cliente.direccion or "", 1).upper()
        else:
            direccion = remplace_string_ro(cliente.domfiscal or "", 1).upper()

        dep, prov, dist = "", "", ""
        if cliente.idubigeo:
            ubi = self._ubigeo(cliente.idubigeo)
            if ubi:
                dep = (ubi.codpto or "")[:2]
                prov = (ubi.codprov or "")[:2]
                dist = (ubi.coddist or "")[:2]

        fecha_firma = ""
        firma_flag = ""
        if contratante:
            firma_flag = str(contratante.firma or "").strip()
            fecha_firma = _format_date_yyyymmdd(contratante.fechafirma)

        conclusion = op["conclusion"]
        if not is_complementary and tipper == "N" and (
            firma_flag in ("0", "") or fecha_firma == ""
        ):
            conclusion = "N"

        participacion, ap_pat, ap_mat, nom_con = resolve_conyuge_fields(
            cliente, role, kardex, cod_acto
        )

        monto_part = _format_amount(cxa.monto or "0.00")
        origen_fondo = remplace_string_ro(cxa.ofondo or "", 1).upper()[:40]

        moneda_part = "" if representante == "R" else op["moneda"]

        return {
            "item_9": conclusion,
            "item_10": fecha_firma,
            "item_13": representante[:1],
            "item_14": persona_operacion[:1],
            "item_15": persona_afavor[:1],
            "item_16": persona_que_representa[:1],
            "item_17": tipo_repr[:1],
            "item_18": condicion_residencia[:1],
            "item_19": tipo_persona[:1],
            "item_20": cod_tipo_doc[:1],
            "item_21": numero_doc[:20],
            "item_22": numero_ruc[:11],
            "item_23": apepat[:120],
            "item_24": apemat[:40],
            "item_25": nombres[:40],
            "item_26": cod_nacion[:2],
            "item_27": fecha_nac,
            "item_28": cod_estado[:1],
            "item_29": cod_prof,
            "item_30": objeto_social[:40],
            "item_31": cod_ciiu[:4],
            "item_32": cod_cargo[:3],
            "item_33": zona_reg,
            "item_34": partida_reg,
            "item_35": direccion[:150],
            "item_36": dep,
            "item_37": prov,
            "item_38": dist,
            "item_39": "",
            "item_40": participacion[:1],
            "item_41": ap_pat[:40],
            "item_42": ap_mat[:40],
            "item_43": nom_con[:40],
            "item_44": "",
            "item_46": "",
            "item_47": "",
            "item_48": "",
            "item_49": origen_fondo,
            "item_50": moneda_part[:3],
            "item_51": "0.00",
            "item_52": monto_part,
            "item_53": "0.00",
            "item_54": "0.00",
            "item_55": "",
            "item_56": "",
            "item_57": "",
        }

    def _persona_que_representa(self, contratante: Optional[Contratantes], role: str) -> str:
        if role != "R" or not contratante or not contratante.idcontratanterp:
            return ""
        rep = (
            Contratantesxacto.objects.filter(
                idcontratante=str(contratante.idcontratanterp).strip()
            )
            .exclude(uif__isnull=True)
            .exclude(uif="")
            .filter(uif__in=["B", "O", "G", "F", "N", "R"])
            .first()
        )
        if not rep or not rep.uif:
            return ""
        return "N" if rep.uif == "R" else rep.uif

    def _ubigeo(self, coddis: str) -> Optional[Ubigeo]:
        key = str(coddis).strip()
        if key not in self._ubigeo_cache:
            self._ubigeo_cache[key] = Ubigeo.objects.filter(coddis=key).first()
        return self._ubigeo_cache[key]
