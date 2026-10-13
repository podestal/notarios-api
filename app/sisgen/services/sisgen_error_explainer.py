"""
Turn raw SISGEN rejections into user-facing messages that say what is wrong and which field to fix.

Two sources:
- Document-level errors echoed by SISGEN (``RO12: FORMA DE PAGO NO ADMITIDO ...``).
- SOAP-level XSD/parser rejections (``cvc-enumeration-valid ... En la Fila: 55 Columna: 45``),
  located in the request XML with :func:`locate_xml_position` at send time.
"""

from __future__ import annotations

import html
import logging
import re
import xml.parsers.expat
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

SEC_KARDEX = "Kardex"
SEC_CONTRATANTES = "Contratantes"
SEC_PATRIMONIAL = "UIF/PDT Patrimonial"

ORIGEN_DATO = "dato"
ORIGEN_SISTEMA = "sistema"

OPORTUNIDAD_VACIO = "10"

# XML element -> (section, user label)
XML_FIELD_LABELS: Dict[str, Tuple[str, str]] = {
    "TipoDocIdentidad": (SEC_CONTRATANTES, "Tipo de documento"),
    "NumDocIdentificativo": (SEC_CONTRATANTES, "Número de documento"),
    "Profesion": (SEC_CONTRATANTES, "Profesión / ocupación"),
    "OtraProfesion": (SEC_CONTRATANTES, "Profesión / ocupación"),
    "Cargo": (SEC_CONTRATANTES, "Cargo"),
    "OtroCargo": (SEC_CONTRATANTES, "Cargo"),
    "FechaNacimiento": (SEC_CONTRATANTES, "Fecha de nacimiento"),
    "EstadoCivil": (SEC_CONTRATANTES, "Estado civil"),
    "Genero": (SEC_CONTRATANTES, "Sexo"),
    "PaisNacionalidad": (SEC_CONTRATANTES, "Nacionalidad"),
    "PaisResidencia": (SEC_CONTRATANTES, "País de residencia"),
    "ResidePeru": (SEC_CONTRATANTES, "Residente"),
    "RestoDireccion": (SEC_CONTRATANTES, "Dirección"),
    "CodDepartamento": (SEC_CONTRATANTES, "Ubigeo (departamento)"),
    "CodProvincia": (SEC_CONTRATANTES, "Ubigeo (provincia)"),
    "CodDistrito": (SEC_CONTRATANTES, "Ubigeo (distrito)"),
    "Telefono": (SEC_CONTRATANTES, "Teléfono"),
    "Correo": (SEC_CONTRATANTES, "Correo"),
    "RazonSocial": (SEC_CONTRATANTES, "Razón social"),
    "PrimerApellido": (SEC_CONTRATANTES, "Apellido paterno"),
    "SegundoApellido": (SEC_CONTRATANTES, "Apellido materno"),
    "Nombre": (SEC_CONTRATANTES, "Nombres"),
    "ObjetoSocial": (SEC_CONTRATANTES, "Objeto social"),
    "SectorEconomico": (SEC_CONTRATANTES, "Actividad económica"),
    "OtraActividad": (SEC_CONTRATANTES, "Actividad económica"),
    "PartidaRegistral": (SEC_CONTRATANTES, "Partida registral"),
    "SedeRegistral": (SEC_CONTRATANTES, "Sede registral"),
    "FechaFirma": (SEC_CONTRATANTES, "Fecha de firma"),
    "PorcentajeDerecho": (SEC_CONTRATANTES, "Porcentaje de participación"),
    "TipoIntervencion": (SEC_CONTRATANTES, "Condición en el acto"),
    "ClaseIntervencion": (SEC_CONTRATANTES, "Condición en el acto"),
    "DescripcionIntervencion": (SEC_CONTRATANTES, "Condición en el acto"),
    "CodActoJuridico": (SEC_KARDEX, "Acto"),
    "NombreContrato": (SEC_KARDEX, "Acto"),
    "FechaMinuta": (SEC_KARDEX, "Fecha de minuta"),
    "FechaInstrumento": (SEC_KARDEX, "Fecha de escritura"),
    "FechaConclusion": (SEC_KARDEX, "Fecha de conclusión"),
    "FechaIngreso": (SEC_KARDEX, "Fecha de ingreso"),
    "NumDocumento": (SEC_KARDEX, "Número de instrumento"),
    "NumFolios": (SEC_KARDEX, "Folios"),
    "Cuantia": (SEC_PATRIMONIAL, "Cuantía de la operación"),
    "CuantiaOperacion": (SEC_PATRIMONIAL, "Cuantía de la operación"),
    "TipoMoneda": (SEC_PATRIMONIAL, "Moneda"),
    "FormaPago": (SEC_PATRIMONIAL, "Forma de pago"),
    "MomentoPago": (SEC_PATRIMONIAL, "Oportunidad de pago"),
    "DescripcionMomentoPago": (SEC_PATRIMONIAL, "Oportunidad de pago (descripción)"),
    "MedioPago": (SEC_PATRIMONIAL, "Medio de pago"),
    "CuantiaPago": (SEC_PATRIMONIAL, "Monto del medio de pago"),
    "TipoMonedaPago": (SEC_PATRIMONIAL, "Moneda del medio de pago"),
    "FechaPago": (SEC_PATRIMONIAL, "Fecha de pago"),
    "EntidadFinanciera": (SEC_PATRIMONIAL, "Entidad financiera"),
    "IdPago": (SEC_PATRIMONIAL, "Número de documento de pago"),
    "OrigenFondo": (SEC_PATRIMONIAL, "Origen de fondos"),
    "CuantiaOrigen": (SEC_PATRIMONIAL, "Monto del origen de fondos"),
    "NumPlaca": (SEC_PATRIMONIAL, "Placa del vehículo"),
    "AnoFabricacion": (SEC_PATRIMONIAL, "Año de fabricación del vehículo"),
    "TipoVehiculo": (SEC_PATRIMONIAL, "Tipo de vehículo"),
    "IdentificacionPredio": (SEC_PATRIMONIAL, "Identificación del predio"),
    "FechaAdquisicion": (SEC_PATRIMONIAL, "Fecha de adquisición del bien"),
}

# Known SISGEN enumerations (value -> label) to show allowed values in plain words.
ENUM_LABELS: Dict[str, Dict[str, str]] = {
    "TipoDocIdentidad": {
        "01": "DNI",
        "02": "Carné de identidad (FF.PP.)",
        "03": "Carné de identidad (FF.AA.)",
        "04": "Carné de extranjería",
        "07": "Pasaporte",
        "08": "RUC",
        "09": "Otro documento",
        "10": "Sin documento",
        "12": "Doc. de entidad extranjera",
        "13": "Doc. de entidad extranjera",
    },
}


def fix_mojibake(text: Any) -> str:
    """SISGEN sends some messages as UTF-8 bytes decoded as Latin-1 (``OPERACIÃ³N``)."""
    s = str(text or "").strip()
    if "Ã" not in s and "Â" not in s:
        return s
    try:
        fixed = s.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return s
    ascii_letters = [c for c in fixed if c.isascii() and c.isalpha()]
    return fixed.upper() if ascii_letters and all(c.isupper() for c in ascii_letters) else fixed


_CODE_RE = re.compile(r"^\s*([A-Z]{2}\d{2})\s*[:\-–]?\s*(.*)$", re.S)


def split_code(text: str) -> Tuple[str, str]:
    m = _CODE_RE.match(text or "")
    if not m:
        return "", (text or "").strip()
    return m.group(1), m.group(2).strip()


# --------------------------------------------------------------------------- kardex lookups


class KardexContext:
    """Lazy, cached DB lookups for one kardex; every query is best-effort."""

    def __init__(self, kardex: str):
        self.kardex = (kardex or "").strip()
        self._cache: Dict[str, Any] = {}

    def _rows(self, key: str, sql: str, params: List[Any]) -> List[Dict[str, Any]]:
        if key in self._cache:
            return self._cache[key]
        rows: List[Dict[str, Any]] = []
        if self.kardex:
            try:
                from django.db import connection

                with connection.cursor() as cur:
                    cur.execute(sql, params)
                    cols = [c[0] for c in cur.description]
                    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
            except Exception:
                logger.warning("SISGEN explainer lookup %s failed for %s", key, self.kardex, exc_info=True)
        self._cache[key] = rows
        return rows

    def personas(self) -> List[Dict[str, Any]]:
        return self._rows(
            "personas",
            """
            SELECT DISTINCT co.idcontratante, cl.idcliente, cl.tipper, cl.prinom, cl.segnom,
                   cl.apepat, cl.apemat, cl.razonsocial, cl.idtipdoc, cl.numdoc, cl.idprofesion,
                   cl.detaprofesion
            FROM contratantes co
            JOIN cliente2 cl ON cl.idcontratante = co.idcontratante
            WHERE co.kardex = %s
            """,
            [self.kardex],
        )

    def persona(self, idcliente: Any) -> Optional[Dict[str, Any]]:
        target = str(idcliente or "").lstrip("0")
        for p in self.personas():
            if str(p.get("idcliente") or "").lstrip("0") == target:
                return p
        return None

    def patrimoniales(self) -> List[Dict[str, Any]]:
        return self._rows(
            "patrimonial",
            """
            SELECT p.itemmp, p.idtipoacto, t.desacto, t.cod_ancert, p.importetrans, p.fpago,
                   f.descripcion AS fpago_desc, p.idoppago, p.des_idoppago
            FROM patrimonial p
            LEFT JOIN tiposdeacto t ON t.idtipoacto = p.idtipoacto
            LEFT JOIN fpago_uif f ON f.id_fpago = p.fpago
            WHERE p.kardex = %s
            """,
            [self.kardex],
        )

    def medios_pago(self) -> List[Dict[str, Any]]:
        return self._rows(
            "medios",
            """
            SELECT d.itemmp, d.codmepag, m.desmpagos, d.importemp
            FROM detallemediopago d
            LEFT JOIN mediospago m ON m.codmepag = d.codmepag
            WHERE d.kardex = %s
            """,
            [self.kardex],
        )

    def acto_nombre(self, cod_ancert: str) -> str:
        rows = self._rows(
            f"acto:{cod_ancert}",
            """
            SELECT DISTINCT t.desacto, (cx.kardex IS NOT NULL) AS en_kardex
            FROM tiposdeacto t
            LEFT JOIN contratantesxacto cx ON cx.idtipoacto = t.idtipoacto AND cx.kardex = %s
            WHERE t.cod_ancert = %s
            ORDER BY en_kardex DESC
            """,
            [self.kardex, cod_ancert],
        )
        return str(rows[0]["desacto"]).strip() if rows else ""

    def bien(self, detbien: Any) -> Optional[Dict[str, Any]]:
        rows = self._rows(
            f"bien:{detbien}",
            "SELECT detbien, tipob, idtipbien, pregistral FROM detallebienes WHERE kardex = %s AND detbien = %s",
            [self.kardex, detbien],
        )
        return rows[0] if rows else None


def persona_nombre(p: Optional[Dict[str, Any]]) -> str:
    if not p:
        return ""
    if (p.get("razonsocial") or "").strip() and (p.get("tipper") or "").upper() == "J":
        return str(p["razonsocial"]).strip()
    parts = [p.get("prinom"), p.get("segnom"), p.get("apepat"), p.get("apemat")]
    name = " ".join(str(x).strip() for x in parts if x and str(x).strip())
    return name or str(p.get("razonsocial") or "").strip()


def _campo(
    seccion: str,
    campo: str,
    referencia: str = "",
    valor_actual: Any = None,
    accion: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {"seccion": seccion, "campo": campo}
    if referencia:
        out["referencia"] = referencia
    if valor_actual not in (None, ""):
        out["valor_actual"] = str(valor_actual)
    out["accion"] = accion or default_accion(seccion)
    return out


# ``accion`` tells the UI how to fix a campo: quick fix in place, edit form, or open the kardex.
def default_accion(seccion: str) -> Dict[str, Any]:
    tab = {SEC_CONTRATANTES: "contratantes", SEC_PATRIMONIAL: "patrimonial"}.get(seccion, "kardex")
    return {"tipo": "ir_kardex", "seccion": tab}


def _accion_editar_contratante(p: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not p or not p.get("idcontratante"):
        return None
    return {"tipo": "editar_contratante", "idcontratante": str(p["idcontratante"])}


def _accion_tipo_documento(p: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not p or not p.get("idcontratante"):
        return None
    return {
        "tipo": "cliente2_tipo_documento",
        "idcontratante": str(p["idcontratante"]),
        "tipper": (p.get("tipper") or "").upper(),
        "idtipdoc": p.get("idtipdoc"),
        "numdoc": str(p.get("numdoc") or "").strip(),
    }


def _accion_profesion(p: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not p or not p.get("idcontratante"):
        return None
    return {
        "tipo": "cliente2_profesion",
        "idcontratante": str(p["idcontratante"]),
        "idprofesion": p.get("idprofesion") or None,
    }


def _accion_forma_pago(pat: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "tipo": "patrimonial_forma_pago",
        "itemmp": str(pat.get("itemmp") or ""),
        "fpago": str(pat.get("fpago") or ""),
    }


def _accion_oportunidad_pago(pat: Dict[str, Any], sugerido: str = "") -> Dict[str, Any]:
    out = {
        "tipo": "patrimonial_oportunidad_pago",
        "itemmp": str(pat.get("itemmp") or ""),
        "idoppago": str(pat.get("idoppago") or ""),
    }
    if sugerido:
        out["sugerido"] = sugerido
    return out


def _persona_ref(ctx: KardexContext, idcliente: Any) -> str:
    name = persona_nombre(ctx.persona(idcliente))
    return name or f"Cliente con ID {str(idcliente).lstrip('0')}"


def _acto_ref(ctx: KardexContext, cod: str) -> str:
    name = ctx.acto_nombre(cod)
    return f"{name} (código SISGEN {cod})" if name else f"Acto código SISGEN {cod}"


def _money(v: Any) -> str:
    try:
        return f"{float(v):,.2f}"
    except (TypeError, ValueError):
        return str(v or "")


# --------------------------------------------------------------------------- document-level rules


Explained = Dict[str, Any]
Rule = Callable[[str, KardexContext], Explained]


def _rule_ro04(body: str, ctx: KardexContext) -> Explained:
    faltan = [
        p for p in ctx.personas()
        if (p.get("tipper") or "").upper() == "N"
        and not p.get("idprofesion")
        and not (p.get("detaprofesion") or "").strip()
    ]
    return {
        "titulo": "Falta la profesión de una persona natural",
        "mensaje_usuario": "SISGEN exige la profesión u ocupación de todas las personas naturales que intervienen.",
        "que_hacer": "Registre la profesión u ocupación en la ficha del contratante y vuelva a enviar.",
        "campos": [
            _campo(SEC_CONTRATANTES, "Profesión / ocupación", persona_nombre(p), accion=_accion_profesion(p))
            for p in faltan
        ]
        or [_campo(SEC_CONTRATANTES, "Profesión / ocupación")],
    }


def _patrimonial_campos(
    ctx: KardexContext,
    campo: str,
    value_fn: Callable[[Dict[str, Any]], Any],
    accion_fn: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    rows = ctx.patrimoniales()
    return [
        _campo(
            SEC_PATRIMONIAL,
            campo,
            str(p.get("desacto") or "").strip(),
            value_fn(p),
            accion=accion_fn(p) if accion_fn else None,
        )
        for p in rows
    ] or [_campo(SEC_PATRIMONIAL, campo)]


def _rule_ro12(body: str, ctx: KardexContext) -> Explained:
    return {
        "titulo": "Forma de pago no admitida para el acto",
        "mensaje_usuario": "SISGEN no acepta la forma de pago registrada para este tipo de acto.",
        "que_hacer": "Cambie la forma de pago del acto por una admitida (por ejemplo, al contado o a plazos) y revise que los medios de pago sean coherentes.",
        "campos": _patrimonial_campos(
            ctx, "Forma de pago", lambda p: p.get("fpago_desc") or p.get("fpago"), _accion_forma_pago
        ),
    }


def _rule_ro11(body: str, ctx: KardexContext) -> Explained:
    medios = ctx.medios_pago()
    return {
        "titulo": "Medio de pago no admitido para el acto",
        "mensaje_usuario": "Uno de los medios de pago registrados no está permitido para este tipo de acto.",
        "que_hacer": "Cambie el medio de pago por uno admitido o elimínelo si no corresponde.",
        "campos": [
            _campo(SEC_PATRIMONIAL, "Medio de pago", valor_actual=f"{m.get('desmpagos') or m.get('codmepag')} · {_money(m.get('importemp'))}")
            for m in medios
        ] or [_campo(SEC_PATRIMONIAL, "Medio de pago")],
    }


def _rule_vl15(body: str, ctx: KardexContext) -> Explained:
    campos = []
    medios = ctx.medios_pago()
    for p in ctx.patrimoniales():
        suma = sum(float(m.get("importemp") or 0) for m in medios if str(m.get("itemmp")) == str(p.get("itemmp")))
        campos.append(
            _campo(
                SEC_PATRIMONIAL,
                "Cuantía vs. suma de medios de pago",
                str(p.get("desacto") or "").strip(),
                f"cuantía {_money(p.get('importetrans'))} · medios {_money(suma)}",
            )
        )
    return {
        "titulo": "Los medios de pago no suman la cuantía",
        "mensaje_usuario": "La suma de los montos de los medios de pago debe ser igual a la cuantía de la operación.",
        "que_hacer": "Corrija los montos de los medios de pago o la cuantía del acto para que coincidan.",
        "campos": campos or [_campo(SEC_PATRIMONIAL, "Medios de pago")],
    }


def _rule_vl34(body: str, ctx: KardexContext) -> Explained:
    no_requiere = "NO REQUIERE" in body.upper()
    return {
        "titulo": "Oportunidad de pago no corresponde" if no_requiere else "Falta la oportunidad de pago",
        "mensaje_usuario": (
            "Este acto no lleva oportunidad de pago, pero se registró una."
            if no_requiere
            else "Este acto requiere que se indique la oportunidad de pago."
        ),
        "que_hacer": (
            "Deje vacía la oportunidad de pago del acto."
            if no_requiere
            else "Seleccione la oportunidad de pago del acto (por ejemplo, a la firma de la minuta o del instrumento)."
        ),
        "campos": _patrimonial_campos(
            ctx,
            "Oportunidad de pago",
            lambda p: p.get("des_idoppago") or p.get("idoppago"),
            lambda p: _accion_oportunidad_pago(p, OPORTUNIDAD_VACIO if no_requiere else ""),
        ),
    }


_ACTO_RE = re.compile(r"ACTO JUR[IÍ]DICO\s+(\d{4})")
_ID_RE = re.compile(r"(?:IDMAESTRO|PERSONA CON ID)\s+(\d+)")
_MAESTRO_RE = re.compile(r"MAESTRO\s+(\d+)")


def _rule_ec36(body: str, ctx: KardexContext) -> Explained:
    m = _ACTO_RE.search(body.upper())
    acto = _acto_ref(ctx, m.group(1)) if m else ""
    no_requiere = "NO REQUIERE" in body.upper()
    return {
        "titulo": "Medios de pago no corresponden" if no_requiere else "Faltan los medios de pago",
        "mensaje_usuario": (
            f"El acto {acto} no lleva medios de pago, pero se registraron."
            if no_requiere
            else f"El acto {acto} requiere que se registren los medios de pago."
        ),
        "que_hacer": (
            "Elimine los medios de pago de este acto."
            if no_requiere
            else "Registre los medios de pago con sus montos (deben sumar la cuantía)."
        ),
        "campos": [_campo(SEC_PATRIMONIAL, "Medios de pago", acto)],
    }


def _rule_ec34(body: str, ctx: KardexContext) -> Explained:
    m = _ACTO_RE.search(body.upper())
    acto = _acto_ref(ctx, m.group(1)) if m else ""
    return {
        "titulo": "El acto no admite cuantía",
        "mensaje_usuario": f"Se registró una cuantía para el acto {acto}, pero SISGEN no la permite en este tipo de acto.",
        "que_hacer": "Elimine la cuantía y los datos de pago de este acto.",
        "campos": [_campo(SEC_PATRIMONIAL, "Cuantía de la operación", acto)],
    }


def _rule_ec40(body: str, ctx: KardexContext) -> Explained:
    up = body.upper()
    m_desc = re.search(r"INTERVENCI[OÓ]N\s+(\d+)", up)
    m = _ACTO_RE.search(up)
    acto = _acto_ref(ctx, m.group(1)) if m else ""
    return {
        "titulo": "Condición del contratante no válida para el acto",
        "mensaje_usuario": (
            f"La condición asignada (código {m_desc.group(1) if m_desc else '?'}) no es válida para el acto {acto}."
        ),
        "que_hacer": "Revise la condición de cada contratante en este acto y asigne una que corresponda al tipo de acto.",
        "campos": [_campo(SEC_CONTRATANTES, "Condición en el acto", acto)],
    }


def _rule_vl29(body: str, ctx: KardexContext) -> Explained:
    m = re.search(r"INTERVENCI[OÓ]N\s+(.+?)\s+REQUIERE", body.upper())
    condicion = m.group(1).strip().title() if m else ""
    return {
        "titulo": f"Falta un contratante con condición {condicion}".strip(),
        "mensaje_usuario": f"El acto necesita al menos un contratante válido con la condición {condicion}.",
        "que_hacer": "Agregue o corrija el contratante con esa condición en el acto.",
        "campos": [_campo(SEC_CONTRATANTES, "Condición en el acto", condicion)],
    }


def _rule_ec48(body: str, ctx: KardexContext) -> Explained:
    m = _ID_RE.search(body.upper())
    ref = _persona_ref(ctx, m.group(1)) if m else ""
    return {
        "titulo": "Representante repetido",
        "mensaje_usuario": (
            f"{ref} figura más de una vez como representante." if ref else "Hay un representante registrado más de una vez."
        ),
        "que_hacer": "Deje una sola vez a cada representante por persona representada.",
        "campos": [_campo(SEC_CONTRATANTES, "Representación", ref)],
    }


def _rule_ec06(body: str, ctx: KardexContext) -> Explained:
    m = re.search(r"MAESTRO PERSONAS? (?:NATURALES|JUR[IÍ]DICAS)\s+(.+?)\s+NO INFORMADO", body.upper())
    nombre = m.group(1).strip() if m else ""
    return {
        "titulo": "Contratante sin participación en el acto",
        "mensaje_usuario": f"{nombre or 'Un contratante'} está registrado en el kardex pero no tiene condición en ningún acto.",
        "que_hacer": "Asigne la condición del contratante en el acto correspondiente o elimínelo si no interviene.",
        "campos": [_campo(SEC_CONTRATANTES, "Condición en el acto", nombre)],
    }


def _rule_text_cleanup(titulo: str, que_hacer: str) -> Rule:
    def rule(body: str, ctx: KardexContext) -> Explained:
        m = _ID_RE.search(body.upper())
        ref = _persona_ref(ctx, m.group(1)) if m else ""
        persona = ctx.persona(m.group(1)) if m else None
        texto = re.split(r"\s+EN PERSONA CON", body, maxsplit=1)[0]
        texto = re.sub(r"^.*?(?:INCLUIDOS? EN(?: EL TEXTO)?)\s+", "", texto)
        return {
            "titulo": titulo,
            "mensaje_usuario": f"Texto observado: «{texto.strip()}».",
            "que_hacer": que_hacer,
            "campos": [
                _campo(SEC_CONTRATANTES, "Datos del cliente", ref, accion=_accion_editar_contratante(persona))
            ],
        }

    return rule


def _rule_ec05(body: str, ctx: KardexContext) -> Explained:
    up = body.upper()
    m = _MAESTRO_RE.search(up)
    bien = ctx.bien(m.group(1)) if m else None
    ref = ""
    if bien:
        ref = f"Bien {bien.get('tipob') or ''} partida {bien.get('pregistral') or '-'}".strip()
    elif m:
        ref = f"Bien con ID {m.group(1)}"
    if "NO PERMITE OBJETOS" in up:
        return {
            "titulo": "El acto no admite bienes",
            "mensaje_usuario": "Se registraron bienes en un acto que no los admite.",
            "que_hacer": "Elimine los bienes de este acto.",
            "campos": [_campo(SEC_PATRIMONIAL, "Bienes", ref)],
        }
    return {
        "titulo": "Tipo de bien no válido para el acto",
        "mensaje_usuario": "El tipo de bien registrado no está permitido en este acto.",
        "que_hacer": "Cambie el tipo de bien o elimínelo si no corresponde al acto.",
        "campos": [_campo(SEC_PATRIMONIAL, "Tipo de bien", ref)],
    }


def _rule_vl01(body: str, ctx: KardexContext) -> Explained:
    sin_ruc = [p for p in ctx.personas() if (p.get("tipper") or "").upper() == "J" and str(p.get("idtipdoc")) == "8"
               and not re.fullmatch(r"\d{11}", str(p.get("numdoc") or "").strip())]
    return {
        "titulo": "RUC con formato incorrecto",
        "mensaje_usuario": "Una persona jurídica tiene RUC vacío o sin 11 dígitos.",
        "que_hacer": "Corrija el RUC (11 dígitos). Si la empresa está en constitución, use el tipo de documento «Sin documento».",
        "campos": [
            _campo(SEC_CONTRATANTES, "Número de documento (RUC)", persona_nombre(p), p.get("numdoc"), accion=_accion_tipo_documento(p))
            for p in sin_ruc
        ]
        or [_campo(SEC_CONTRATANTES, "Número de documento (RUC)")],
    }


def _rule_ex06(body: str, ctx: KardexContext) -> Explained:
    sin_doc = [p for p in ctx.personas() if not str(p.get("numdoc") or "").strip() and str(p.get("idtipdoc")) != "10"]
    return {
        "titulo": "Falta el número de documento",
        "mensaje_usuario": "Un contratante no tiene número de documento de identidad.",
        "que_hacer": "Registre el número de documento del contratante.",
        "campos": [
            _campo(SEC_CONTRATANTES, "Número de documento", persona_nombre(p), accion=_accion_tipo_documento(p))
            for p in sin_doc
        ]
        or [_campo(SEC_CONTRATANTES, "Número de documento")],
    }


def _rule_vl19(body: str, ctx: KardexContext) -> Explained:
    return {
        "titulo": "Fecha de conclusión anterior a la autorización",
        "mensaje_usuario": "La fecha de conclusión no puede ser anterior a la fecha de autorización del instrumento.",
        "que_hacer": "Corrija la fecha de conclusión o la fecha de escritura del kardex.",
        "campos": [_campo(SEC_KARDEX, "Fecha de conclusión"), _campo(SEC_KARDEX, "Fecha de escritura")],
    }


DOCUMENT_RULES: Dict[str, Rule] = {
    "RO04": _rule_ro04,
    "RO11": _rule_ro11,
    "RO12": _rule_ro12,
    "VL01": _rule_vl01,
    "VL15": _rule_vl15,
    "VL19": _rule_vl19,
    "VL29": _rule_vl29,
    "VL34": _rule_vl34,
    "EC05": _rule_ec05,
    "EC06": _rule_ec06,
    "EC17": _rule_text_cleanup(
        "Espacios dobles en un texto",
        "Quite los espacios consecutivos del texto indicado en la ficha del cliente.",
    ),
    "EC26": _rule_text_cleanup(
        "Carácter especial no permitido",
        "Quite el carácter especial (por ejemplo «;») del texto indicado en la ficha del cliente.",
    ),
    "EC34": _rule_ec34,
    "EC36": _rule_ec36,
    "EC40": _rule_ec40,
    "EC48": _rule_ec48,
    "EX06": _rule_ex06,
}


def _dedupe_key(code: str, body: str) -> str:
    body = re.split(r"\s+EN PERSONA CON", body.upper(), maxsplit=1)[0]
    return f"{code}|{re.sub(r'[^A-Z0-9]+', ' ', body).strip()[:80]}"


def explain_document_errors(
    raw_errors: List[Any],
    *,
    kardex: str,
    estado: str = "",
    ctx: Optional[KardexContext] = None,
) -> List[Dict[str, Any]]:
    """Structured, de-duplicated explanations for SISGEN document-level ``<ERROR>`` texts."""
    ctx = ctx or KardexContext(kardex)
    out: List[Dict[str, Any]] = []
    index_by_key: Dict[str, int] = {}
    for raw in raw_errors or []:
        text = fix_mojibake(raw)
        if not text:
            continue
        code, body = split_code(text)
        key = _dedupe_key(code, body)
        if key in index_by_key:
            prev = out[index_by_key[key]]
            if len(text) > len(prev["mensaje_tecnico"]):
                prev["mensaje_tecnico"] = text
            continue

        rule = DOCUMENT_RULES.get(code)
        explained: Explained
        if rule:
            try:
                explained = rule(body, ctx)
            except Exception:
                logger.warning("SISGEN explainer rule %s failed", code, exc_info=True)
                explained = {}
        elif text.lower().startswith("transaction rolled back"):
            explained = {
                "titulo": "SISGEN no pudo guardar el documento",
                "mensaje_usuario": "SISGEN canceló el registro por otro error del mismo documento.",
                "que_hacer": "Corrija los demás errores del documento y vuelva a enviar.",
                "campos": [],
            }
        else:
            explained = {}

        entry = {
            "kardex": kardex,
            "codigo": code,
            "titulo": explained.get("titulo") or (f"Observación de SISGEN ({code})" if code else "Observación de SISGEN"),
            "mensaje_usuario": explained.get("mensaje_usuario") or body.capitalize(),
            "que_hacer": explained.get("que_hacer") or "",
            "campos": explained.get("campos") or [],
            "origen": ORIGEN_DATO,
            "mensaje_tecnico": text,
        }
        if estado:
            entry["estado"] = estado
        index_by_key[key] = len(out)
        out.append(entry)

    # SISGEN often repeats a specific error ("... IDMAESTRO 9074 ...") with a generic one of the same code.
    specific_codes = {e["codigo"] for e in out if e["codigo"] and re.search(r"\d", split_code(e["mensaje_tecnico"])[1])}
    return [
        e for e in out
        if not (e["codigo"] in specific_codes and not re.search(r"\d", split_code(e["mensaje_tecnico"])[1]))
    ]


# --------------------------------------------------------------------------- SOAP / XSD rejections

_POS_RE = re.compile(r"En la Fila:\s*(\d+)\s*Columna:\s*(\d+)", re.I)
_PERSONA_TAGS = {"PersonaNatural", "PersonaJuridica"}


class _Node:
    __slots__ = ("tag", "attrs", "parent", "children", "text", "start", "end")

    def __init__(self, tag: str, attrs: Dict[str, str], parent: Optional["_Node"], start: Tuple[int, int]):
        self.tag = tag.split(":")[-1].split("}")[-1]
        self.attrs = attrs
        self.parent = parent
        self.children: List["_Node"] = []
        self.text = ""
        self.start = start
        self.end = start

    def child_text(self, tag: str) -> str:
        for ch in self.children:
            if ch.tag == tag:
                return ch.text.strip()
        return ""

    def find_text(self, tag: str) -> str:
        stack = list(self.children)
        while stack:
            n = stack.pop(0)
            if n.tag == tag and n.text.strip():
                return n.text.strip()
            stack[:0] = n.children
        return ""


def parse_soap_position(message: str) -> Optional[Tuple[int, int]]:
    m = _POS_RE.search(message or "")
    return (int(m.group(1)), int(m.group(2))) if m else None


def locate_xml_position(xml_text: str, line: int, column: int) -> Optional[Dict[str, Any]]:
    """
    Map a Xerces (line, column) from SISGEN to the element in the XML we sent.
    Xerces reports the position right after the offending element's end tag.
    """
    if not xml_text or line <= 0:
        return None
    parser = xml.parsers.expat.ParserCreate()
    nodes: List[_Node] = []
    stack: List[_Node] = []

    def start(tag, attrs):
        node = _Node(tag, attrs, stack[-1] if stack else None, (parser.CurrentLineNumber, parser.CurrentColumnNumber + 1))
        if stack:
            stack[-1].children.append(node)
        stack.append(node)
        nodes.append(node)

    def end(tag):
        node = stack.pop()
        node.end = (parser.CurrentLineNumber, parser.CurrentColumnNumber + len(tag) + 4)

    def chars(data):
        if stack:
            stack[-1].text += data

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = chars
    try:
        parser.Parse(xml_text.encode("utf-8"), True)
    except xml.parsers.expat.ExpatError:
        logger.warning("SISGEN explainer: request XML not parseable for location", exc_info=True)
        return None

    on_line = [n for n in nodes if not n.children and n.end[0] == line]
    if on_line:
        target = min(on_line, key=lambda n: abs(n.end[1] - column))
    else:
        containing = [n for n in nodes if n.start[0] <= line <= n.end[0]]
        if not containing:
            return None
        target = max(containing, key=lambda n: (n.start[0], n.start[1]))

    loc: Dict[str, Any] = {"elemento": target.tag, "valor": html.unescape(target.text.strip())}
    p: Optional[_Node] = target
    while p is not None:
        if p.tag in _PERSONA_TAGS and "persona" not in loc:
            name = p.find_text("RazonSocial") or " ".join(
                x for x in (p.find_text("Nombre"), p.find_text("PrimerApellido"), p.find_text("SegundoApellido")) if x
            )
            loc["persona"] = html.unescape(name)
            loc["persona_id"] = p.attrs.get("id", "")
            loc["persona_tipo"] = "J" if p.tag == "PersonaJuridica" else "N"
        elif p.tag == "Operacion" and "acto_codigo" not in loc:
            loc["acto_codigo"] = p.child_text("CodActoJuridico")
            loc["acto_nombre"] = p.child_text("NombreContrato")
        elif p.tag == "MedioPago" and "medio_pago" not in loc:
            loc["medio_pago"] = p.child_text("MedioPago") or p.find_text("MedioPago")
        elif p.tag == "DocumentoNotarial":
            loc["kardex"] = p.find_text("NumKardex")
            break
        p = p.parent
    return loc


# Allowed-value lists that identify the field when the request XML is not available.
ENUM_SIGNATURES: Dict[Tuple[str, ...], Tuple[str, str]] = {
    ("08", "09", "10", "12", "13"): ("TipoDocIdentidad", "J"),
}


def _element_from_message(raw: str, allowed: List[str], persona_tipo: str) -> Tuple[str, str]:
    """Best-effort field from the XSD message alone (type name or known enumeration)."""
    m_type = re.search(r"for type '#?AnonType_([A-Za-z]+)'", raw)
    if m_type:
        type_name = m_type.group(1)
        matches = [k for k in XML_FIELD_LABELS if type_name.startswith(k)]
        if matches:
            return max(matches, key=len), persona_tipo
    sig = ENUM_SIGNATURES.get(tuple(allowed))
    if sig:
        return sig[0], persona_tipo or sig[1]
    return "", persona_tipo


def _enum_text(field: str, values: List[str]) -> str:
    labels = ENUM_LABELS.get(field, {})
    return ", ".join(f"{v} ({labels[v]})" if v in labels else v for v in values)


_PERSONA_DOC_FIELDS = {"TipoDocIdentidad", "NumDocIdentificativo"}
_PERSONA_PROFESION_FIELDS = {"Profesion", "OtraProfesion"}
# Persona fields stored per contratante (condition in the act), not in the client's ficha.
_CONTRATANTE_ACTO_FIELDS = {
    "Cargo", "OtroCargo", "FechaFirma", "PorcentajeDerecho",
    "TipoIntervencion", "ClaseIntervencion", "DescripcionIntervencion",
}


def _patrimonial_for_acto(ctx: KardexContext, acto_codigo: str) -> Optional[Dict[str, Any]]:
    rows = ctx.patrimoniales()
    if acto_codigo:
        matches = [p for p in rows if str(p.get("cod_ancert") or "").strip() == str(acto_codigo).strip()]
        if len(matches) == 1:
            return matches[0]
    return rows[0] if len(rows) == 1 else None


def _soap_accion(element: str, seccion: str, loc: Dict[str, Any], ctx: Optional[KardexContext]) -> Optional[Dict[str, Any]]:
    if ctx is None:
        return None
    if seccion == SEC_CONTRATANTES and element not in _CONTRATANTE_ACTO_FIELDS:
        persona = ctx.persona(loc["persona_id"]) if loc.get("persona_id") else None
        if element in _PERSONA_DOC_FIELDS:
            return _accion_tipo_documento(persona)
        if element in _PERSONA_PROFESION_FIELDS:
            return _accion_profesion(persona)
        return _accion_editar_contratante(persona)
    if element in ("FormaPago", "MomentoPago", "DescripcionMomentoPago"):
        pat = _patrimonial_for_acto(ctx, loc.get("acto_codigo") or "")
        if pat is None:
            return None
        return _accion_forma_pago(pat) if element == "FormaPago" else _accion_oportunidad_pago(pat)
    return None


def explain_soap_message(
    message: str,
    *,
    kardex: str = "",
    location: Optional[Dict[str, Any]] = None,
    ctx: Optional[KardexContext] = None,
) -> Dict[str, Any]:
    """Explain a SOAP-level rejection (XSD validation / SISGEN parser error)."""
    raw = fix_mojibake((message or "").strip().splitlines()[0] if message else "")
    loc = location or {}
    target_kardex = loc.get("kardex") or kardex
    if ctx is None and target_kardex:
        ctx = KardexContext(target_kardex)
    element = loc.get("elemento") or ""
    value = loc.get("valor", "")

    m_complex = re.search(r"cvc-complex-type\.2\.4\.[a-d]:.*?element '([A-Za-z]+)'", raw)
    m_enum = re.search(r"cvc-enumeration-valid: Value '([^']*)' .*?enumeration '\[([^\]]*)\]'", raw)
    m_len = re.search(r"cvc-maxLength-valid: Value '([^']*)' with length = '(\d+)' .*?maxLength '(\d+)'", raw)
    m_num = re.search(r'For input string: "([^"]*)"', raw)
    allowed = [v.strip() for v in m_enum.group(2).split(",") if v.strip()] if m_enum else []

    persona_tipo = loc.get("persona_tipo", "")
    if not element and m_complex:
        element = m_complex.group(1)
    if not element:
        element, persona_tipo = _element_from_message(raw, allowed, persona_tipo)
    seccion, campo = XML_FIELD_LABELS.get(element, ("", element))
    en_campo = f" en {campo}" if campo else ""

    referencia_parts = []
    if loc.get("persona"):
        referencia_parts.append(loc["persona"])
    if loc.get("acto_codigo") or loc.get("acto_nombre"):
        referencia_parts.append(f"Acto {loc.get('acto_nombre') or loc.get('acto_codigo')}")
    referencia = " · ".join(referencia_parts)

    origen = ORIGEN_DATO
    titulo = "SISGEN rechazó el documento"
    mensaje = ""
    que_hacer = ""

    if m_enum:
        bad = m_enum.group(1)
        value = bad
        titulo = f"Valor no permitido{en_campo}"
        if element == "TipoDocIdentidad" and persona_tipo == "J":
            mensaje = (
                f"El tipo de documento «{bad}» ({ENUM_LABELS['TipoDocIdentidad'].get(bad, bad)}) no es válido para una persona jurídica."
            )
            que_hacer = "Use RUC (08) si la empresa tiene RUC, o «Sin documento» (10) si está en constitución."
        else:
            mensaje = f"SISGEN no acepta el valor «{bad or 'vacío'}»{en_campo}."
            que_hacer = f"Seleccione uno de los valores permitidos: {_enum_text(element, allowed)}."
    elif m_len:
        val, length, max_len = m_len.groups()
        value = val
        titulo = f"Texto demasiado largo{en_campo}"
        mensaje = f"«{val}» tiene {length} caracteres y SISGEN admite como máximo {max_len}."
        que_hacer = f"Acorte el texto a {max_len} caracteres o menos."
    elif "Invalid date" in raw or ("cvc-datatype-valid" in raw and "date" in raw.lower()):
        titulo = f"Fecha inválida{en_campo}"
        if value:
            mensaje = f"El valor «{value}» no es una fecha válida."
        elif loc:
            mensaje = "La fecha está vacía o incompleta."
        else:
            mensaje = "Una fecha del documento está vacía o no es válida."
        que_hacer = "Registre la fecha completa con el formato correcto."
    elif m_num:
        value = m_num.group(1)
        titulo = f"Valor numérico inválido{en_campo}"
        mensaje = f"SISGEN esperaba un número y recibió «{value or 'vacío'}»."
        que_hacer = "Registre un valor numérico (sin guiones ni letras)."
    elif raw.lower().startswith("null"):
        titulo = f"Falta un dato{en_campo}"
        mensaje = (
            f"{campo[:1].upper() + campo[1:]} está vacío o no tiene un valor válido."
            if campo
            else "Un dato obligatorio del documento está vacío o no es válido."
        )
        que_hacer = "Complete el dato y vuelva a enviar."
    elif m_complex:
        origen = ORIGEN_SISTEMA
        titulo = "Error en la estructura del XML generado"
        mensaje = f"El elemento «{element}» no está en la posición o forma que SISGEN espera."
        que_hacer = "Este error no se corrige desde el kardex: contacte a sistemas con el kardex y este mensaje."
    else:
        origen = ORIGEN_SISTEMA
        mensaje = raw or "SISGEN no devolvió detalle del error."
        que_hacer = "Si el problema persiste, contacte a sistemas con el kardex y este mensaje."

    campos = []
    if origen == ORIGEN_DATO and campo:
        campos.append(
            _campo(seccion or SEC_KARDEX, campo, referencia, value, accion=_soap_accion(element, seccion, loc, ctx))
        )
    if origen == ORIGEN_DATO and not campo:
        que_hacer += " Si no ubica el dato, vuelva a enviar el documento: el sistema indicará el campo exacto."

    return {
        "kardex": target_kardex,
        "codigo": "XSD",
        "titulo": titulo,
        "mensaje_usuario": mensaje,
        "que_hacer": que_hacer,
        "campos": campos,
        "origen": origen,
        "mensaje_tecnico": raw,
    }


def locate_soap_failure(message: str, request_xml: str) -> Optional[Dict[str, Any]]:
    pos = parse_soap_position(message)
    if not pos or not request_xml:
        return None
    try:
        return locate_xml_position(request_xml, *pos)
    except Exception:
        logger.warning("SISGEN explainer: locate failed", exc_info=True)
        return None


def short_user_message(errors: List[Any]) -> str:
    """One line for tables: titles of the explained errors."""
    titles = []
    for e in errors or []:
        t = e.get("titulo") if isinstance(e, dict) else str(e)
        if t and t not in titles:
            titles.append(t)
    return " · ".join(titles)
