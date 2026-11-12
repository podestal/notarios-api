"""
Parse SUNARP ``Boleta Informativa`` vehicular PDFs into structured JSON.

Works on pdfplumber plain text where fields look like ``Label : value``.
Masked SUNARP values (``##########``) are kept as empty strings.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

_MASK = re.compile(r"^#+$")
_LABEL_ALT = (
    r"Nombre|Direcci[oó]n|DNI|Placa|Tipo Uso|Categor[ií]a|Carrocer[ií]a|Marca|"
    r"Modelo|A[nñ]o Fab|A[nñ]o Mod|N[°º]\s*Versi[oó]n|N[°º]\s*Serie|N[°º]\s*de\s*VIN|"
    r"Color\s*1|Color\s*2|Color\s*3|N[°º]\s*Motor|Tipo Combus|Pot\.?\s*Motor|"
    r"N[°º]\s*Cilindros|Cilindrada|Peso Neto|Peso Bruto|Carga [UÚ]til|"
    r"N[°º]\s*Asientos|N[°º]\s*Pasajer\.?|N[°º]\s*Ejes|N[°º]\s*Ruedas|"
    r"Longitud|Ancho|Altura|Form\.?\s*Rodan\.?|Inmatriculac\.?|Fec\.?\s*Prop|"
    r"Condici[oó]n|N[°º]\s*Partida"
)
# Next field label must be followed by ``:`` so values like
# ``Taxis y Colectivos (Categoria M1)`` are not truncated.
# Optional whitespace lets empty values (``Categoría : Color 3 :``) stop cleanly.
_FIELD = re.compile(
    rf"(?P<label>{_LABEL_ALT})\s*:\s*(?P<value>.*?)(?="
    rf"(?:\s*(?:{_LABEL_ALT})\s*:|"
    rf"\s*(?:OFICINA|NO REGISTRA|NO EXISTEN|COPIA INFORMATIVA|"
    rf"DATOS ADICIONALES|P[aá]gina)\b)|$)",
    re.IGNORECASE | re.DOTALL,
)
_SWALLOWED_LABEL = re.compile(
    rf"^(?:{_LABEL_ALT})\s*:",
    re.IGNORECASE,
)


def _clean(value: str) -> str:
    text = re.sub(r"\s+", " ", (value or "")).strip(" :\t\n\r")
    if not text or _MASK.match(text):
        return ""
    if _SWALLOWED_LABEL.match(text):
        return ""
    return text


def _norm_label(label: str) -> str:
    key = re.sub(r"[°º\.]", "", label.lower())
    key = (
        key.replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("ñ", "n")
    )
    key = re.sub(r"\s+", "_", key.strip())
    mapping = {
        "nombre": "propietario_nombre",
        "direccion": "propietario_direccion",
        "dni": "propietario_dni",
        "placa": "placa",
        "tipo_uso": "tipo_uso",
        "categoria": "categoria",
        "carroceria": "carroceria",
        "marca": "marca",
        "modelo": "modelo",
        "ano_fab": "anio_fabricacion",
        "ano_mod": "anio_modelo",
        "n_version": "numero_version",
        "n_serie": "numero_serie",
        "n_de_vin": "vin",
        "color_1": "color_1",
        "color_2": "color_2",
        "color_3": "color_3",
        "n_motor": "numero_motor",
        "tipo_combus": "combustible",
        "pot_motor": "potencia_motor",
        "n_cilindros": "numero_cilindros",
        "cilindrada": "cilindrada",
        "peso_neto": "peso_neto",
        "peso_bruto": "peso_bruto",
        "carga_util": "carga_util",
        "n_asientos": "numero_asientos",
        "n_pasajer": "numero_pasajeros",
        "n_ejes": "numero_ejes",
        "n_ruedas": "numero_ruedas",
        "longitud": "longitud",
        "ancho": "ancho",
        "altura": "altura",
        "form_rodan": "formula_rodante",
        "inscrip": "fecha_inscripcion",
        "inscripulac": "fecha_inscripcion",
        "inmatriculac": "fecha_inscripcion",
        "fec_prop": "fecha_propiedad",
        "condicion": "condicion",
        "n_partida": "partida",
    }
    return mapping.get(key, key)


def _extract_meta(text: str) -> Dict[str, str]:
    meta: Dict[str, str] = {}
    m_date = re.search(r"(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2})", text)
    if m_date:
        meta["emitido_en"] = m_date.group(1)
    m_user = re.search(
        r"Usuario\s+Nro\.?\s*Transacci[oó]n\s+Pagado.*?\n(\S+)\s+(\d+)\s+([\d.]+)",
        text,
        re.IGNORECASE,
    )
    if m_user:
        meta["usuario"] = m_user.group(1)
        meta["nro_transaccion"] = m_user.group(2)
        meta["pagado"] = m_user.group(3)
    m_oficina = re.search(
        r"OFICINA\s+([A-ZÁÉÍÓÚÑ]+(?:\s+[A-ZÁÉÍÓÚÑ]+)*)(?=\s*(?:N[°º]|Tipo|Placa|Categor|$|\n))",
        text,
        re.IGNORECASE,
    )
    if m_oficina:
        meta["oficina"] = _clean(m_oficina.group(1))
    if "VEHÍCULO EN CIRCULACION" in text.upper() or "VEHICULO EN CIRCULACION" in text.upper():
        meta["estado_vehiculo"] = "EN CIRCULACION"
    if re.search(r"NO REGISTRA AFECTACIONES", text, re.IGNORECASE):
        meta["afectaciones"] = "NO REGISTRA AFECTACIONES"
    m_extra = re.search(
        r"DATOS ADICIONALES.*?\n(.+?)(?:\nCOPIA|\nP[aá]gina|$)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if m_extra:
        meta["datos_adicionales"] = _clean(m_extra.group(1))
    # DNI often sits after nombre on the same line as "DNI" label with value on direccion line.
    m_dni = re.search(
        r"Nombre\s*:\s*.+?\s+DNI\s*\nDirecci[oó]n\s*:\s*.+?\s+(\d{8,11})\b",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if m_dni:
        meta["propietario_dni"] = m_dni.group(1)
    else:
        m_dni2 = re.search(r"Direcci[oó]n\s*:\s*.+?\s+(\d{8,11})\b", text, re.IGNORECASE)
        if m_dni2:
            meta["propietario_dni"] = m_dni2.group(1)
    return meta


def parse_boleta_vehicular_text(text: str) -> Dict[str, Any]:
    if not (text or "").strip():
        raise ValueError("Empty PDF text; cannot parse boleta vehicular")
    if "BOLETA INFORMATIVA" not in text.upper():
        raise ValueError("PDF does not look like a SUNARP Boleta Informativa")

    fields: Dict[str, str] = {}
    for match in _FIELD.finditer(text):
        label = _norm_label(match.group("label"))
        value = _clean(match.group("value"))
        # Prefer first non-empty value for a label.
        if label not in fields or (value and not fields[label]):
            fields[label] = value

    meta = _extract_meta(text)
    if meta.get("propietario_dni") and not fields.get("propietario_dni"):
        fields["propietario_dni"] = meta.pop("propietario_dni")
    elif "propietario_dni" in meta:
        meta.pop("propietario_dni", None)

    # Nombre often ends with the bare "DNI" label (value sits on the next line).
    nombre = fields.get("propietario_nombre") or ""
    if re.search(r"\bDNI\s*$", nombre, re.IGNORECASE):
        fields["propietario_nombre"] = _clean(re.sub(r"\bDNI\s*$", "", nombre, flags=re.IGNORECASE))

    # Dirección line often appends DNI digits — strip if we captured dni separately.
    dni = fields.get("propietario_dni") or ""
    direccion = fields.get("propietario_direccion") or ""
    if dni and direccion.endswith(dni):
        fields["propietario_direccion"] = _clean(direccion[: -len(dni)])

    payload = {
        "documento": "boleta_informativa",
        "tipo": "vehicular",
        "meta": meta,
        "propietario": {
            "nombre": fields.get("propietario_nombre", ""),
            "direccion": fields.get("propietario_direccion", ""),
            "dni": fields.get("propietario_dni", ""),
        },
        "vehiculo": {
            "placa": fields.get("placa", ""),
            "tipo_uso": fields.get("tipo_uso", ""),
            "categoria": fields.get("categoria", ""),
            "carroceria": fields.get("carroceria", ""),
            "marca": fields.get("marca", ""),
            "modelo": fields.get("modelo", ""),
            "anio_fabricacion": fields.get("anio_fabricacion", ""),
            "anio_modelo": fields.get("anio_modelo", ""),
            "numero_version": fields.get("numero_version", ""),
            "numero_serie": fields.get("numero_serie", ""),
            "vin": fields.get("vin", ""),
            "color_1": fields.get("color_1", ""),
            "color_2": fields.get("color_2", ""),
            "color_3": fields.get("color_3", ""),
            "numero_motor": fields.get("numero_motor", ""),
            "combustible": fields.get("combustible", ""),
            "potencia_motor": fields.get("potencia_motor", ""),
            "numero_cilindros": fields.get("numero_cilindros", ""),
            "cilindrada": fields.get("cilindrada", ""),
            "peso_neto": fields.get("peso_neto", ""),
            "peso_bruto": fields.get("peso_bruto", ""),
            "carga_util": fields.get("carga_util", ""),
            "numero_asientos": fields.get("numero_asientos", ""),
            "numero_pasajeros": fields.get("numero_pasajeros", ""),
            "numero_ejes": fields.get("numero_ejes", ""),
            "numero_ruedas": fields.get("numero_ruedas", ""),
            "longitud": fields.get("longitud", ""),
            "ancho": fields.get("ancho", ""),
            "altura": fields.get("altura", ""),
            "formula_rodante": fields.get("formula_rodante", ""),
            "fecha_inscripcion": fields.get("fecha_inscripcion", ""),
            "fecha_propiedad": fields.get("fecha_propiedad", ""),
            "condicion": fields.get("condicion", ""),
            "partida": fields.get("partida", ""),
            "oficina": meta.get("oficina", ""),
        },
        "fields": fields,
    }
    return payload


def placa_from_parsed(parsed: Optional[Dict[str, Any]]) -> str:
    if not parsed:
        return ""
    veh = parsed.get("vehiculo") or {}
    return str(veh.get("placa") or parsed.get("fields", {}).get("placa") or "").strip()


def partida_from_parsed(parsed: Optional[Dict[str, Any]]) -> str:
    if not parsed:
        return ""
    veh = parsed.get("vehiculo") or {}
    return str(veh.get("partida") or parsed.get("fields", {}).get("partida") or "").strip()
