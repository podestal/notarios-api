from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Any, Optional
from django.db import connection
from django.http import HttpResponse
import logging

# SUNAT acto codes written to PDT (ActFilePdt / PDTClass::initialData). 05 is excluded.
ACT_SUNAT_CODES = (
    "01",
    "02",
    "03",
    "04",
    "06",
    "07",
    "08",
    "09",
    "10",
    "11",
    "12",
    "13",
    "14",
    "15",
    "16",
    "17",
    "18",
    "19",
    "20",
    "21",
    "22",
    "23",
    "24",
    "25",
    "26",
)
ACT_MINUTA_SUNAT = frozenset({"10", "04", "24", "26"})
TIPO_KARDEX_TO_PDT = {1: "1", 3: "2", 4: "5"}


def php_intval(value: Any) -> int:
    try:
        return int(float(str(value).strip() or 0))
    except (TypeError, ValueError):
        return 0


def php_str_pad(value: Any, length: int, *, side: str = "left", pad: str = " ") -> str:
    """PHP str_pad(substr($value, 0, $length), $length, ' ', STR_PAD_LEFT|RIGHT)."""
    text = "" if value is None else str(value)
    text = text[:length]
    if side == "left":
        return text.rjust(length, pad)
    return text.ljust(length, pad)


def replace_string_pdt(text: Any) -> str:
    """PDTClass::remplaceStringPdt — Ñ/ñ → N/n; other specials become space."""
    if not text:
        return ""
    result = str(text)
    replacements = (
        ("?", " "),
        ("*", " "),
        ("QQ11QQ", " "),
        ("Ñ", "N"),
        ("ñ", "n"),
        ("°", " "),
        ("#", " "),
        ("é", " "),
        ("á", " "),
        ("í", " "),
        ("ó", " "),
        ("ú", " "),
        ("'", " "),
        ("&", " "),
        ("É", " "),
        ("Á", " "),
        ("Ó", " "),
        ("Ú", " "),
        ("Í", " "),
        (",", " "),
        ("QQ22KK", " "),
    )
    for old, new in replacements:
        result = result.replace(old, new)
    return result


def _fecha_escritura_ddmmyyyy(value: Any) -> str:
    """PDTClass loadDataAct: explode YYYY-MM-DD → DD/MM/YYYY."""
    raw = str(value or "").strip()
    if not raw:
        return ""
    if "-" in raw and len(raw) >= 10 and raw[4] == "-":
        year, month, day = raw[:10].split("-")
        return f"{day}/{month}/{year}"
    return raw[:10]


def format_act_line(record: Dict[str, Any]) -> str:
    """
    ActFilePdt fields + PDTClass::generateFileAct padding.

    tipoKardex|numeroEscritura|fechaEscritura|fechaConclusion|fechaLegalizacion|
    actoSunat|secuencial|moneda|importe|plazoInicial|plazoFinal|nombreContrato|
    fechaInscripcionMinuta|exibioMedioPago
    """
    try:
        idtipkar = int(record.get("idtipkar") or 0)
    except (TypeError, ValueError):
        idtipkar = 0
    tipo_kardex = TIPO_KARDEX_TO_PDT.get(idtipkar, "")
    format_fecha_escritura = _fecha_escritura_ddmmyyyy(record.get("fechaescritura"))
    fecha_conclusion = str(record.get("fechaconclusion") or "").strip()
    if fecha_conclusion in ("", "0000-00-00"):
        fecha_conclusion = ""

    if tipo_kardex == "5":
        fecha_esc_out = ""
        fecha_conc_out = ""
        fecha_legal = format_fecha_escritura
    else:
        fecha_esc_out = format_fecha_escritura
        fecha_conc_out = fecha_conclusion
        fecha_legal = ""

    acto_sunat = str(record.get("actosunat") or "").strip()
    try:
        idmon = int(record.get("idmon") or 0)
    except (TypeError, ValueError):
        idmon = 0
    importe = record.get("importetrans")
    if idmon == 1:
        codigo_moneda = "2"
    elif idmon == 2:
        codigo_moneda = "1"
    elif idmon == 3:
        codigo_moneda = "1"
        try:
            importe = float(importe or 0) * float(record.get("tipocambio") or 0)
        except (TypeError, ValueError):
            pass
    else:
        codigo_moneda = ""

    if acto_sunat == "14":
        nombre_contrato = replace_string_pdt(record.get("desacto") or "")
    else:
        nombre_contrato = ""

    if acto_sunat in ACT_MINUTA_SUNAT:
        minuta = str(record.get("nminuta") or "")
        exhibio = "1" if record.get("exhibiomp") == "SI" else "0"
    else:
        minuta = ""
        exhibio = ""

    fields = [
        php_str_pad(php_intval(tipo_kardex), 1, side="left"),
        php_str_pad(php_intval(record.get("numescritura")), 5, side="left"),
        php_str_pad(fecha_esc_out, 10, side="left"),
        php_str_pad(fecha_conc_out, 10, side="left"),
        php_str_pad(fecha_legal, 10, side="left"),
        php_str_pad(acto_sunat, 2, side="left"),
        php_str_pad(record.get("secuencial", 1), 5, side="right"),
        php_str_pad(codigo_moneda, 1, side="right"),
        php_str_pad(importe, 15, side="right"),
        php_str_pad("", 10, side="left"),
        php_str_pad("", 11, side="left"),
        php_str_pad(nombre_contrato, 30, side="right"),
        php_str_pad(minuta, 10, side="left"),
        php_str_pad(exhibio, 1, side="left"),
    ]
    return "|".join(fields)

class BasePdtFormatter(ABC):
    """Base class for PDT file formatters."""
    
    def __init__(self, initial_date: str, final_date: str, type_kardex: Optional[int] = None):
        self.initial_date = initial_date
        self.final_date = final_date
        self.type_kardex = type_kardex
        self.logger = logging.getLogger(__name__)
        self.data = []
        self.extension = ''  # Will be set by child classes
        self.prefix = '3520'  # Common prefix for all PDT files

    @abstractmethod
    def load_data(self):
        """Load data from database."""
        pass

    @abstractmethod
    def format_line(self, record: Dict) -> str:
        """Format a single line according to PDT specifications."""
        pass

    def get_formatted_dates(self) -> tuple:
        """Convert and validate dates."""
        try:
            # First try DD/MM/YYYY format
            start_date = datetime.strptime(self.initial_date, '%d/%m/%Y')
            end_date = datetime.strptime(self.final_date, '%d/%m/%Y')
        except ValueError:
            try:
                # Then try YYYY-MM-DD format
                start_date = datetime.strptime(self.initial_date, '%Y-%m-%d')
                end_date = datetime.strptime(self.final_date, '%Y-%m-%d')
            except ValueError as e:
                raise ValueError(f"Invalid date format. Dates must be in DD/MM/YYYY or YYYY-MM-DD format")

        return start_date.strftime("%d/%m/%Y"), end_date.strftime("%d/%m/%Y")

    def get_notary_data(self) -> Dict:
        """Get notary configuration data."""
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT 
                    idnotar AS idNotario,
                    nombre AS nombreNotario, 
                    apellido AS apellidosNotario,
                    CONCAT(nombre,' ',apellido) AS notario,
                    telefono AS telefonoNotario,
                    correo AS correoNotario, 
                    ruc AS rucNotario, 
                    direccion AS direccionNotario, 
                    distrito AS distritoNotario, 
                    codnotario AS codigoNotario,
                    codoficial AS codigoOficial, 
                    coduif AS codigoUif 
                FROM confinotario
            """)
            columns = [col[0] for col in cursor.description]
            result = cursor.fetchone()
            
            if not result:
                raise ValueError("No notary configuration found")
                
            return dict(zip(columns, result))

    def generate_file(self) -> HttpResponse:
        """Generate PDT file."""
        try:
            self.load_data()
            
            # Format lines
            content_lines = []
            for record in self.data:
                line = self.format_line(record)
                content_lines.append(line)

            # PHP generateFile*: last field is followed by "|" then chr(13).chr(10).
            content = "".join(f"{line}|\r\n" for line in content_lines)

            # Create response
            response = HttpResponse(content, content_type='text/plain')
            
            # Generate filename: 3520{YYYY}{RUC}.{ext} (PDTClass uses the full year)
            notary_data = self.get_notary_data()
            start_date, _ = self.get_formatted_dates()
            year = start_date.split("/")[-1]
            filename = f"{self.prefix}{year}{notary_data['rucNotario']}.{self.extension}"
            
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            response['Content-Transfer-Encoding'] = 'binary'
            
            return response

        except Exception as e:
            self.logger.error(f"Error generating {self.extension} file: {str(e)}")
            raise

    def replace_string_pdt(self, text: str) -> str:
        return replace_string_pdt(text)

    def get_base_kardex_query(self) -> str:
        """Get the base kardex query that all formatters should use."""
        return """
            WITH kardex_actos AS (
                SELECT 
                    k.idkardex,
                    k.kardex,
                    k.idtipkar,
                    k.numescritura,
                    k.fechaescritura,
                    SUBSTRING(codactos, n.n, 3) as acto_code
                FROM kardex k
                CROSS JOIN (
                    SELECT 1 + (3 * (a.n-1)) as n
                    FROM (
                        SELECT 1 as n UNION SELECT 2 UNION SELECT 3 UNION SELECT 4 
                        UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8
                    ) a
                    WHERE 1 + (3 * (a.n-1)) <= (
                        SELECT MAX(LENGTH(codactos)) FROM kardex
                    )
                ) n
                WHERE k.idtipkar = %s
                AND k.fechaescritura BETWEEN %s AND %s
                AND SUBSTRING(codactos, n.n, 3) != ''
            )
        """

def _pdt_tipo_kardex(idtipkar: Any) -> str:
    try:
        return TIPO_KARDEX_TO_PDT.get(int(idtipkar), "")
    except (TypeError, ValueError):
        return ""


def load_pdt_act_rows(type_kardex: int, start_date: str, end_date: str) -> List[Dict[str, Any]]:
    """PDTClass::initialData + loadDataAct → in-memory temp_act."""
    sunat_placeholders = ",".join(["%s"] * len(ACT_SUNAT_CODES))
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            WITH kardex_actos AS (
                SELECT
                    k.idkardex,
                    k.kardex,
                    k.idtipkar,
                    k.numescritura,
                    k.fechaescritura,
                    k.fechaconclusion,
                    SUBSTRING(k.codactos, n.n, 3) AS acto_code
                FROM kardex k
                CROSS JOIN (
                    SELECT 1 + (3 * (a.n - 1)) AS n
                    FROM (
                        SELECT 1 AS n UNION SELECT 2 UNION SELECT 3 UNION SELECT 4
                        UNION SELECT 5 UNION SELECT 6 UNION SELECT 7 UNION SELECT 8
                    ) a
                ) n
                WHERE k.idtipkar = %s
                  AND STR_TO_DATE(k.fechaconclusion, '%%d/%%m/%%Y')
                      BETWEEN STR_TO_DATE(%s, '%%d/%%m/%%Y')
                      AND STR_TO_DATE(%s, '%%d/%%m/%%Y')
                  AND SUBSTRING(k.codactos, n.n, 3) <> ''
            )
            SELECT
                ka.idkardex,
                ka.kardex,
                ka.idtipkar,
                ka.numescritura,
                ka.fechaescritura,
                ka.fechaconclusion,
                t.idtipoacto,
                t.actosunat,
                t.desacto,
                p.itemmp,
                p.idmon,
                p.nminuta,
                p.importetrans,
                p.exhibiomp,
                p.tipocambio
            FROM kardex_actos ka
            INNER JOIN tiposdeacto t ON t.idtipoacto = ka.acto_code
            INNER JOIN patrimonial p
                ON p.kardex = ka.kardex AND p.idtipoacto = ka.acto_code
            WHERE t.actosunat <> ''
              AND t.actosunat IN ({sunat_placeholders})
            ORDER BY CAST(ka.numescritura AS UNSIGNED) ASC
            """,
            [type_kardex, start_date, end_date, *ACT_SUNAT_CODES],
        )
        columns = [col[0] for col in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

    for index, row in enumerate(rows, start=1):
        row["secuencial"] = index
        acto_sunat = str(row.get("actosunat") or "").strip()
        row["tipo_kardex_pdt"] = _pdt_tipo_kardex(row.get("idtipkar"))
        row["fecha_escritura_fmt"] = _fecha_escritura_ddmmyyyy(row.get("fechaescritura"))
        if acto_sunat in ACT_MINUTA_SUNAT:
            row["exhibio_mp"] = "1" if row.get("exhibiomp") == "SI" else "0"
        else:
            row["exhibio_mp"] = ""
    return rows


def _in_placeholders(values: List[Any]) -> str:
    return ",".join(["%s"] * len(values))


def format_bie_line(record: Dict[str, Any]) -> str:
    """BienFilePdt export fields + PDTClass::generateFileBien (all STR_PAD_RIGHT)."""
    fields = [
        php_str_pad(php_intval(record.get("tipo_kardex_pdt")), 1, side="right"),
        php_str_pad(php_intval(record.get("numescritura")), 5, side="right"),
        php_str_pad(record.get("fecha_escritura_fmt") or "", 10, side="right"),
        php_str_pad(record.get("secuencial_acto"), 5, side="right"),
        php_str_pad(record.get("secuencial_bien"), 5, side="right"),
        php_str_pad(record.get("tipo_bien") or "", 1, side="right"),
        php_str_pad(record.get("codigo_bien") or "", 2, side="right"),
        php_str_pad(record.get("opcion_psm") or "", 1, side="right"),
        php_str_pad(replace_string_pdt(record.get("numero_psm") or ""), 20, side="right"),
        php_str_pad(replace_string_pdt(record.get("numero_serie") or ""), 20, side="right"),
        php_str_pad(replace_string_pdt(record.get("origen_bien") or ""), 1, side="right"),
        php_str_pad(record.get("codigo_ubicacion") or "", 6, side="right"),
        php_str_pad(record.get("fecha_adquisicion") or "", 10, side="right"),
        php_str_pad(replace_string_pdt(record.get("descripcion_otros") or ""), 30, side="right"),
    ]
    return "|".join(fields)


def format_otg_line(record: Dict[str, Any]) -> str:
    """OtorganteFilePdt export fields + PDTClass::generateFileOtorgante."""
    fields = [
        php_str_pad(php_intval(record.get("tipo_kardex_pdt")), 1, side="left"),
        php_str_pad(php_intval(record.get("numescritura")), 5, side="left"),
        php_str_pad(record.get("fecha_escritura_fmt") or "", 10, side="left"),
        php_str_pad(record.get("secuencial_acto"), 5, side="right"),
        php_str_pad(record.get("secuencial_bien") or "", 5, side="right"),
        php_str_pad(record.get("secuencial_otorgante"), 5, side="right"),
        php_str_pad(record.get("tipo_documento") or "", 2, side="right"),
        php_str_pad(record.get("numero_documento") or "", 12, side="right"),
        php_str_pad(record.get("tipo_otorgante") or "", 2, side="right"),
        php_str_pad(record.get("tipo_persona") or "", 1, side="right"),
        php_str_pad(record.get("ubigeo") or "", 6, side="right"),
        php_str_pad(record.get("porcentaje") or "", 6, side="right"),
        php_str_pad(replace_string_pdt(record.get("razon_social") or ""), 40, side="right"),
        php_str_pad(replace_string_pdt(record.get("apellido_paterno") or ""), 20, side="right"),
        php_str_pad(replace_string_pdt(record.get("apellido_materno") or ""), 20, side="right"),
        php_str_pad(replace_string_pdt(record.get("primer_nombre") or ""), 20, side="right"),
        php_str_pad(replace_string_pdt(record.get("segundo_nombre") or ""), 30, side="right"),
        php_str_pad(record.get("pregunta1") or "", 1, side="right"),
        php_str_pad(record.get("pregunta2") or "", 1, side="right"),
        php_str_pad(record.get("pregunta3") or "", 1, side="right"),
    ]
    return "|".join(fields)


def format_mpa_line(record: Dict[str, Any]) -> str:
    """MedioFilePdt export fields + PDTClass::generateFileMedio (no fecha escritura)."""
    fields = [
        php_str_pad(php_intval(record.get("tipo_kardex_pdt")), 1, side="left"),
        php_str_pad(php_intval(record.get("numescritura")), 5, side="left"),
        php_str_pad(record.get("secuencial_acto"), 5, side="right"),
        php_str_pad(record.get("medio_pago") or "", 3, side="right"),
        php_str_pad(record.get("moneda") or "", 1, side="right"),
        php_str_pad(record.get("monto") or "", 15, side="right"),
        php_str_pad(record.get("fecha_pago") or "", 10, side="right"),
        php_str_pad(replace_string_pdt(record.get("documentos") or ""), 25, side="right"),
        php_str_pad(record.get("entidad_financiera") or "", 2, side="right"),
    ]
    return "|".join(fields)


def format_for_line(record: Dict[str, Any]) -> str:
    """FormFilePdt export fields + PDTClass::generateFileForm (raw idtipkar)."""
    fields = [
        php_str_pad(php_intval(record.get("idtipkar")), 1, side="left"),
        php_str_pad(php_intval(record.get("numescritura")), 5, side="left"),
        php_str_pad(record.get("secuencial_acto"), 5, side="right"),
        php_str_pad(record.get("secuencial_otorgante"), 5, side="right"),
        php_str_pad(record.get("tipo_otorgante") or "", 2, side="right"),
        php_str_pad(record.get("numero_formulario") or "", 10, side="right"),
        php_str_pad(record.get("pago_cuenta") or "", 15, side="right"),
    ]
    return "|".join(fields)


def format_lib_line(record: Dict[str, Any]) -> str:
    """LibFilePdt export fields + PDTClass::generateFileLibro."""
    fields = [
        php_str_pad(record.get("numero_libro") or "", 10, side="left"),
        str(record.get("fecha_ingreso") or ""),
        php_str_pad(php_intval(record.get("id_tipo_libro")), 2, side="left"),
        php_str_pad(php_intval(record.get("folio")), 10, side="left"),
        str(record.get("tipo_persona") or ""),
        php_str_pad(record.get("ruc") or "", 11, side="right"),
        php_str_pad(replace_string_pdt(record.get("apellido_paterno") or "").upper(), 15, side="right"),
        php_str_pad(replace_string_pdt(record.get("apellido_materno") or "").upper(), 15, side="right"),
        php_str_pad(replace_string_pdt(record.get("primer_nombre") or "").upper(), 15, side="right"),
        php_str_pad(replace_string_pdt(record.get("segundo_nombre") or "").upper(), 30, side="right"),
        php_str_pad(replace_string_pdt(record.get("razon_social") or "").upper(), 40, side="right"),
    ]
    return "|".join(fields)


class ActosFormatter(BasePdtFormatter):
    """Formatter for .Act files (ActFilePdt / PDTClass::loadDataAct + generateFileAct)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.extension = "Act"

    def load_data(self):
        if self.type_kardex is None:
            raise ValueError("typeKardex is required for .Act files")
        start_date, end_date = self.get_formatted_dates()
        self.data = load_pdt_act_rows(int(self.type_kardex), start_date, end_date)

    def format_line(self, record: Dict) -> str:
        return format_act_line(record)


MPA_ACT_SUNAT = frozenset({"04", "10", "24", "26"})
MPA_DOC_SUNAT = frozenset({"001", "002", "003", "005", "006", "007", "012", "099"})
MPA_BANK_SUNAT = frozenset({"001", "002", "003", "005", "006", "007", "012"})
OTG_DOC_TYPE = {1: "01", 2: "04", 5: "07", 8: "06", 9: "-", 10: "-"}
RENTA_KEEP_SUNAT = frozenset({"04", "22", "01", "16", "26"})
RENTA_DEFAULT_SUNAT = frozenset({"01", "22", "16", "26"})


def _cursor_dicts(cursor) -> List[Dict[str, Any]]:
    cols = [col[0] for col in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def load_pdt_bie_rows(type_kardex: int, start_date: str, end_date: str) -> List[Dict[str, Any]]:
    """PDTClass::loadDataBien using in-memory temp_act."""
    acts = load_pdt_act_rows(type_kardex, start_date, end_date)
    if not acts:
        return []

    rows: List[Dict[str, Any]] = []
    secuencial_bien = 0

    if int(type_kardex) == 3:
        kardex_keys = list({str(a["kardex"]) for a in acts if a.get("kardex")})
        vehicles_by_kardex: Dict[str, List[Dict[str, Any]]] = {k: [] for k in kardex_keys}
        cod_bien = "08"
        with connection.cursor() as cursor:
            cursor.execute("SELECT codbien FROM tipobien WHERE idtipbien = '8' LIMIT 1")
            tipobien = cursor.fetchone()
            if tipobien and tipobien[0]:
                cod_bien = str(tipobien[0])
            if kardex_keys:
                cursor.execute(
                    f"""
                    SELECT detveh, kardex, numplaca, numserie, motor, fecinsc
                    FROM detallevehicular
                    WHERE kardex IN ({_in_placeholders(kardex_keys)})
                    """,
                    kardex_keys,
                )
                for veh in _cursor_dicts(cursor):
                    vehicles_by_kardex.setdefault(str(veh["kardex"]), []).append(veh)

        for act in acts:
            for veh in vehicles_by_kardex.get(str(act["kardex"]), []):
                placa = str(veh.get("numplaca") or "")
                serie = str(veh.get("numserie") or "")
                motor = str(veh.get("motor") or "")
                if placa:
                    opcion, numero_psm = "1", placa
                elif serie:
                    opcion, numero_psm = "2", serie
                else:
                    opcion, numero_psm = "3", motor
                secuencial_bien += 1
                rows.append(
                    {
                        "tipo_kardex_pdt": act["tipo_kardex_pdt"],
                        "numescritura": act["numescritura"],
                        "fecha_escritura_fmt": act["fecha_escritura_fmt"],
                        "secuencial_acto": act["secuencial"],
                        "secuencial_bien": secuencial_bien,
                        "tipo_bien": "B",
                        "codigo_bien": cod_bien,
                        "opcion_psm": opcion,
                        "numero_psm": numero_psm,
                        "numero_serie": "",
                        "origen_bien": "",
                        "codigo_ubicacion": "",
                        "fecha_adquisicion": veh.get("fecinsc") or "",
                        "descripcion_otros": "",
                    }
                )
        return rows

    itemmps = [str(a["itemmp"]) for a in acts if a.get("itemmp")]
    bienes_by_itemmp: Dict[str, List[Dict[str, Any]]] = {}
    if itemmps:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    db.detbien, db.itemmp, db.kardex, db.idtipacto, db.tipob, db.idtipbien,
                    db.coddis, db.fechaconst, db.oespecific, db.smaquiequipo, db.tpsm, db.npsm,
                    tb.codbien
                FROM detallebienes db
                LEFT JOIN tipobien tb ON tb.idtipbien = db.idtipbien
                WHERE db.itemmp IN ({_in_placeholders(itemmps)})
                """,
                itemmps,
            )
            for bien in _cursor_dicts(cursor):
                bienes_by_itemmp.setdefault(str(bien["itemmp"]), []).append(bien)

    for act in acts:
        itemmp = str(act.get("itemmp") or "")
        bienes = bienes_by_itemmp.get(itemmp) or []
        if not bienes:
            continue
        for bien in bienes:
            secuencial_bien += 1
            cod_bien = str(bien.get("codbien") or "")
            tpsm = str(bien.get("tpsm") or "")
            opcion = {"P": "1", "S": "2", "M": "3"}.get(tpsm, "")
            codigo_distrito = str(bien.get("coddis") or "") if cod_bien == "04" else ""
            if codigo_distrito and cod_bien in ("04", "99"):
                origen = "1"
            else:
                origen = ""
            rows.append(
                {
                    "tipo_kardex_pdt": act["tipo_kardex_pdt"],
                    "numescritura": act["numescritura"],
                    "fecha_escritura_fmt": act["fecha_escritura_fmt"],
                    "secuencial_acto": act["secuencial"],
                    "secuencial_bien": secuencial_bien,
                    "tipo_bien": "B" if bien.get("tipob") == "BIENES" else "A",
                    "codigo_bien": cod_bien,
                    "opcion_psm": opcion,
                    "numero_psm": bien.get("npsm") or "",
                    "numero_serie": bien.get("smaquiequipo") or "",
                    "origen_bien": origen,
                    "codigo_ubicacion": codigo_distrito,
                    "fecha_adquisicion": bien.get("fechaconst") or "",
                    "descripcion_otros": (bien.get("oespecific") or "") if cod_bien == "99" else "",
                }
            )
    return rows


def _otg_preguntas(act: Dict[str, Any], *, tipper: str, parte: Any, renta: Optional[Dict], fecha_adq: str):
    acto = str(act.get("actosunat") or "").strip()
    p1 = p2 = p3 = ""
    id_renta = 0
    parte_s = str(parte or "").strip()
    if acto in RENTA_DEFAULT_SUNAT:
        if tipper == "N" and parte_s in ("1", "1.0"):
            p1, p2, p3 = "0", "0", "1"
    elif acto == "04" and tipper == "N" and parte_s in ("1", "1.0"):
        if fecha_adq:
            if renta:
                p1 = "" if renta.get("pregu1") is None else str(renta.get("pregu1"))
                p2 = "" if renta.get("pregu2") is None else str(renta.get("pregu2"))
                p3 = "" if renta.get("pregu3") is None else str(renta.get("pregu3"))
                id_renta = php_intval(renta.get("idrenta"))
        else:
            p1, p2, p3 = "0", "0", "1"
    if acto not in RENTA_KEEP_SUNAT:
        p1 = p2 = p3 = ""
        id_renta = 0
    return p1, p2, p3, id_renta


def load_pdt_otg_rows(type_kardex: int, start_date: str, end_date: str) -> List[Dict[str, Any]]:
    """PDTClass::loadDataOtorgante using in-memory temp_act."""
    acts = load_pdt_act_rows(type_kardex, start_date, end_date)
    if not acts:
        return []

    pairs = [(str(a["kardex"]), str(a["idtipoacto"])) for a in acts]
    kardex_keys = list({p[0] for p in pairs})

    contratantes: List[Dict[str, Any]] = []
    rentas: Dict[tuple, Dict[str, Any]] = {}
    fechas_adq: Dict[tuple, str] = {}
    with connection.cursor() as cursor:
        if pairs:
            pair_filter = " OR ".join(["(cxa.kardex = %s AND cxa.idtipoacto = %s)"] * len(pairs))
            params: List[Any] = []
            for kardex, idtipoacto in pairs:
                params.extend([kardex, idtipoacto])
            cursor.execute(
                f"""
                SELECT
                    cxa.kardex, cxa.idtipoacto, cxa.idcontratante, cxa.idcondicion,
                    cxa.parte, cxa.porcentaje,
                    c2.idtipdoc, c2.numdoc, c2.tipper, c2.apepat, c2.apemat,
                    c2.prinom, c2.segnom, c2.razonsocial, c2.idubigeo,
                    ac.totorgante
                FROM contratantesxacto cxa
                INNER JOIN cliente2 c2 ON c2.idcontratante = cxa.idcontratante
                LEFT JOIN actocondicion ac ON ac.idcondicion = cxa.idcondicion
                WHERE ({pair_filter})
                  AND (cxa.parte = '1' OR cxa.parte = '2' OR cxa.parte = 1 OR cxa.parte = 2)
                """,
                params,
            )
            contratantes = _cursor_dicts(cursor)

        if kardex_keys:
            cursor.execute(
                f"""
                SELECT idrenta, idcontratante, kardex, pregu1, pregu2, pregu3
                FROM renta
                WHERE kardex IN ({_in_placeholders(kardex_keys)})
                """,
                kardex_keys,
            )
            for row in _cursor_dicts(cursor):
                rentas[(str(row["kardex"]), str(row["idcontratante"]))] = row
            cursor.execute(
                f"""
                SELECT kardex, idtipacto, fechaconst
                FROM detallebienes
                WHERE kardex IN ({_in_placeholders(kardex_keys)})
                """,
                kardex_keys,
            )
            for row in _cursor_dicts(cursor):
                key = (str(row["kardex"]), str(row["idtipacto"]))
                if key not in fechas_adq:
                    fechas_adq[key] = str(row.get("fechaconst") or "")

    by_pair: Dict[tuple, List[Dict[str, Any]]] = {}
    for row in contratantes:
        by_pair.setdefault((str(row["kardex"]), str(row["idtipoacto"])), []).append(row)

    out: List[Dict[str, Any]] = []
    secuencial_otorgante = 1
    for act in acts:
        people = by_pair.get((str(act["kardex"]), str(act["idtipoacto"])), [])
        for person in people:
            tipper = str(person.get("tipper") or "")
            try:
                idtipdoc = int(person.get("idtipdoc") or 0)
            except (TypeError, ValueError):
                idtipdoc = 0
            tipo_doc = OTG_DOC_TYPE.get(idtipdoc, "")
            numero_doc = "" if tipo_doc == "-" else str(person.get("numdoc") or "")
            tipo_persona = "1" if tipper == "N" else ("2" if tipper == "J" else "")
            apepat = replace_string_pdt(person.get("apepat") or "")
            apemat = replace_string_pdt(person.get("apemat") or "")
            prinom = replace_string_pdt(person.get("prinom") or "")
            segnom = replace_string_pdt(person.get("segnom") or "")
            razon = replace_string_pdt(person.get("razonsocial") or "")
            if tipo_persona == "2":
                apepat = apemat = prinom = segnom = ""
            elif tipo_persona == "1":
                razon = ""
            ubigeo = str(person.get("idubigeo") or "")
            if ubigeo == "999999" or len(ubigeo) != 6:
                ubigeo = ""
            try:
                porcentaje = f"{float(person.get('porcentaje') or 0):.2f}"
            except (TypeError, ValueError):
                porcentaje = "0.00"
            renta = rentas.get((str(act["kardex"]), str(person.get("idcontratante"))))
            fecha_adq = fechas_adq.get((str(act["kardex"]), str(act["idtipoacto"])), "")
            p1, p2, p3, id_renta = _otg_preguntas(
                act, tipper=tipper, parte=person.get("parte"), renta=renta, fecha_adq=fecha_adq
            )
            out.append(
                {
                    "idtipkar": act["idtipkar"],
                    "tipo_kardex_pdt": act["tipo_kardex_pdt"],
                    "numescritura": act["numescritura"],
                    "fecha_escritura_fmt": act["fecha_escritura_fmt"],
                    "secuencial_acto": act["secuencial"],
                    "secuencial_bien": "",
                    "secuencial_otorgante": secuencial_otorgante,
                    "tipo_documento": tipo_doc,
                    "numero_documento": numero_doc,
                    "tipo_otorgante": person.get("totorgante") or "",
                    "tipo_persona": tipo_persona,
                    "ubigeo": ubigeo,
                    "porcentaje": porcentaje,
                    "razon_social": razon,
                    "apellido_paterno": apepat,
                    "apellido_materno": apemat,
                    "primer_nombre": prinom,
                    "segundo_nombre": segnom,
                    "pregunta1": p1,
                    "pregunta2": p2,
                    "pregunta3": p3,
                    "id_renta": id_renta,
                }
            )
            secuencial_otorgante += 1
    return out


def load_pdt_mpa_rows(type_kardex: int, start_date: str, end_date: str) -> List[Dict[str, Any]]:
    """PDTClass::loadDataMedioPago using in-memory temp_act."""
    acts = load_pdt_act_rows(type_kardex, start_date, end_date)
    eligible = [a for a in acts if str(a.get("exhibio_mp") or "").strip() in ("1", "1.0")]
    if not eligible:
        return []
    itemmps = [str(a["itemmp"]) for a in eligible if a.get("itemmp")]
    if not itemmps:
        return []

    medios_by_itemmp: Dict[str, List[Dict[str, Any]]] = {}
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT
                dmp.detmp, dmp.itemmp, dmp.kardex, dmp.tipacto, dmp.codmepag, dmp.idbancos,
                dmp.importemp, dmp.idmon, dmp.foperacion, dmp.documentos,
                mp.sunat AS sunat_mp,
                b.codbancos
            FROM detallemediopago dmp
            LEFT JOIN mediospago mp ON mp.codmepag = dmp.codmepag
            LEFT JOIN bancos b ON b.idbancos = dmp.idbancos
            LEFT JOIN tiposdeacto t ON t.idtipoacto = dmp.tipacto
            WHERE dmp.itemmp IN ({_in_placeholders(itemmps)})
            """,
            itemmps,
        )
        fetched = _cursor_dicts(cursor)
        acto_sunat_by_tipo: Dict[str, str] = {}
        tipos = list({str(r.get("tipacto") or "") for r in fetched if r.get("tipacto")})
        if tipos:
            cursor.execute(
                f"SELECT idtipoacto, actosunat FROM tiposdeacto WHERE idtipoacto IN ({_in_placeholders(tipos)})",
                tipos,
            )
            for row in cursor.fetchall():
                acto_sunat_by_tipo[str(row[0])] = str(row[1] or "")
        for medio in fetched:
            medio["acto_sunat_mp"] = acto_sunat_by_tipo.get(str(medio.get("tipacto") or ""), "")
            medios_by_itemmp.setdefault(str(medio["itemmp"]), []).append(medio)

    out: List[Dict[str, Any]] = []
    for act in eligible:
        for medio in medios_by_itemmp.get(str(act.get("itemmp") or ""), []):
            if medio.get("acto_sunat_mp") not in MPA_ACT_SUNAT:
                continue
            sunat = str(medio.get("sunat_mp") or "")
            try:
                idmon = int(medio.get("idmon") or 0)
            except (TypeError, ValueError):
                idmon = 0
            moneda = "2" if idmon == 1 else ("1" if idmon == 2 else "")
            documentos = replace_string_pdt(medio.get("documentos") or "")
            if sunat not in MPA_DOC_SUNAT:
                documentos = ""
            banco = str(medio.get("codbancos") or "")
            if sunat not in MPA_BANK_SUNAT:
                banco = ""
            out.append(
                {
                    "tipo_kardex_pdt": act["tipo_kardex_pdt"],
                    "numescritura": act["numescritura"],
                    "secuencial_acto": act["secuencial"],
                    "medio_pago": sunat,
                    "moneda": moneda,
                    "monto": medio.get("importemp") or "",
                    "fecha_pago": medio.get("foperacion") or "",
                    "documentos": documentos,
                    "entidad_financiera": banco,
                }
            )
    return out


def load_pdt_for_rows(type_kardex: int, start_date: str, end_date: str) -> List[Dict[str, Any]]:
    """PDTClass::loadDataFormulario from temp_otg rows with idrenta != 0."""
    otorgantes = load_pdt_otg_rows(type_kardex, start_date, end_date)
    with_renta = [o for o in otorgantes if php_intval(o.get("id_renta")) != 0]
    if not with_renta:
        return []
    ids = [php_intval(o["id_renta"]) for o in with_renta]
    forms: Dict[int, Dict[str, Any]] = {}
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT idrenta, numformu, monto
            FROM formulario
            WHERE idrenta IN ({_in_placeholders(ids)})
            """,
            ids,
        )
        for row in _cursor_dicts(cursor):
            forms[php_intval(row["idrenta"])] = row
    out = []
    for otg in with_renta:
        form = forms.get(php_intval(otg["id_renta"]), {})
        out.append(
            {
                "idtipkar": otg["idtipkar"],
                "numescritura": otg["numescritura"],
                "secuencial_acto": otg["secuencial_acto"],
                "secuencial_otorgante": otg["secuencial_otorgante"],
                "tipo_otorgante": otg["tipo_otorgante"],
                "numero_formulario": form.get("numformu") or "",
                "pago_cuenta": form.get("monto") or "",
            }
        )
    return out


def load_pdt_lib_rows(start_date: str, end_date: str) -> List[Dict[str, Any]]:
    """PDTClass::loadDataLibro."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT numlibro, fecing, tipper, apepat, apemat, prinom, segnom, ruc,
                   empresa, idtiplib, folio, ano
            FROM libros
            WHERE fecing BETWEEN STR_TO_DATE(%s, '%%d/%%m/%%Y') AND STR_TO_DATE(%s, '%%d/%%m/%%Y')
              AND CAST(idtiplib AS UNSIGNED) >= 1
              AND CAST(idtiplib AS UNSIGNED) <= 15
              AND idnlibro <> '0'
            """,
            [start_date, end_date],
        )
        books = _cursor_dicts(cursor)
    out = []
    for book in books:
        fecing = book.get("fecing")
        if fecing is None:
            fecha_ingreso = ""
        elif hasattr(fecing, "strftime"):
            fecha_ingreso = fecing.strftime("%d/%m/%Y")
        else:
            parts = str(fecing).split("-")
            if len(parts) >= 3:
                fecha_ingreso = f"{parts[2]}/{parts[1]}/{parts[0]}"
            else:
                fecha_ingreso = str(fecing)
        tipper = str(book.get("tipper") or "")
        out.append(
            {
                "numero_libro": book.get("numlibro") or "",
                "fecha_ingreso": fecha_ingreso,
                "id_tipo_libro": book.get("idtiplib") or "",
                "folio": book.get("folio") or "",
                "tipo_persona": "1" if tipper == "N" else "2",
                "ruc": book.get("ruc") or "",
                "apellido_paterno": book.get("apepat") or "",
                "apellido_materno": book.get("apemat") or "",
                "primer_nombre": book.get("prinom") or "",
                "segundo_nombre": book.get("segnom") or "",
                "razon_social": book.get("empresa") or "",
            }
        )
    return out


class BienesFormatter(BasePdtFormatter):
    """Formatter for .Bie files (BienFilePdt / PDTClass::generateFileBien)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.extension = "Bie"

    def load_data(self):
        if self.type_kardex is None:
            raise ValueError("typeKardex is required for .Bie files")
        start_date, end_date = self.get_formatted_dates()
        self.data = load_pdt_bie_rows(int(self.type_kardex), start_date, end_date)

    def format_line(self, record: Dict) -> str:
        return format_bie_line(record)


class OtorgantesFormatter(BasePdtFormatter):
    """Formatter for .Otg files (OtorganteFilePdt / PDTClass::generateFileOtorgante)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.extension = "Otg"

    def load_data(self):
        if self.type_kardex is None:
            raise ValueError("typeKardex is required for .Otg files")
        start_date, end_date = self.get_formatted_dates()
        self.data = load_pdt_otg_rows(int(self.type_kardex), start_date, end_date)

    def format_line(self, record: Dict) -> str:
        return format_otg_line(record)


class MediosPagoFormatter(BasePdtFormatter):
    """Formatter for .Mpa files (MedioFilePdt / PDTClass::generateFileMedio)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.extension = "Mpa"

    def load_data(self):
        if self.type_kardex is None:
            raise ValueError("typeKardex is required for .Mpa files")
        start_date, end_date = self.get_formatted_dates()
        self.data = load_pdt_mpa_rows(int(self.type_kardex), start_date, end_date)

    def format_line(self, record: Dict) -> str:
        return format_mpa_line(record)


class FormularioFormatter(BasePdtFormatter):
    """Formatter for .For files (FormFilePdt / PDTClass::generateFileForm)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.extension = "For"

    def load_data(self):
        if self.type_kardex is None:
            raise ValueError("typeKardex is required for .For files")
        start_date, end_date = self.get_formatted_dates()
        self.data = load_pdt_for_rows(int(self.type_kardex), start_date, end_date)

    def format_line(self, record: Dict) -> str:
        return format_for_line(record)


class LibrosFormatter(BasePdtFormatter):
    """Formatter for .lib files (LibFilePdt / PDTClass::generateFileLibro)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.extension = "lib"

    def load_data(self):
        start_date, end_date = self.get_formatted_dates()
        self.data = load_pdt_lib_rows(start_date, end_date)

    def format_line(self, record: Dict) -> str:
        return format_lib_line(record)


class PdtFileService:
    """Service for generating PDT files."""
    
    # File type constants
    FILE_TYPE_ACT = 1  # Actos
    FILE_TYPE_BIE = 2  # Bienes
    FILE_TYPE_OTG = 3  # Otorgantes
    FILE_TYPE_MPA = 4  # Medio de Pago
    FILE_TYPE_FORM = 5  # Formulario
    FILE_TYPE_LIB = 6  # Libros

    FILE_TYPE_FORMATTERS = {
        FILE_TYPE_ACT: ActosFormatter,
        FILE_TYPE_BIE: BienesFormatter,
        FILE_TYPE_OTG: OtorgantesFormatter,
        FILE_TYPE_MPA: MediosPagoFormatter,
        FILE_TYPE_FORM: FormularioFormatter,
        FILE_TYPE_LIB: LibrosFormatter,
    }

    def __init__(self, initial_date: str, final_date: str, file_type: int, type_kardex: Optional[int] = None):
        self.formatter_class = self.FILE_TYPE_FORMATTERS.get(file_type)
        if not self.formatter_class:
            raise ValueError(f"Invalid file type: {file_type}")
            
        self.formatter = self.formatter_class(initial_date, final_date, type_kardex)

    def generate_file(self) -> HttpResponse:
        """Generate PDT file."""
        return self.formatter.generate_file()
