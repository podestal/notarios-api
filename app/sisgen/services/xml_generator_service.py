"""
This module contains the XML generator service for the sisgen service.
"""

import html
import logging
from typing import Dict, List, Optional, Set, Tuple
from xml.sax.saxutils import escape
from ..utils.constants import APP_CONSTANTS, TIPO_KARDEX_SISGEN_MAPPING
from datetime import datetime
from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator
from django.db import connection
from django.db.utils import DatabaseError

from notaria.constants import FORMAS_PAGO, MONEDAS, OPORTUNIDADES_PAGO

logger = logging.getLogger(__name__)

class SISGENXmlGenerator:
    """Lengths aligned with legacy xml_kardex.php (mb_substr limits)."""
    JUR_RAZON_SOCIAL_MAX = 120
    JUR_OTRA_ACTIVIDAD_MAX = 50
    # XSD Origen (OrigenFondosType) maxLength 40
    ORIGEN_FONDOS_MAX = 40
    JUR_TELEFONO_MAX = 20
    JUR_PARTIDA_MAX = 12
    JUR_RESTO_DIRECCION_MAX = 255

    _email_validator = EmailValidator()

    def __init__(self):
        self.logger = logger

    def _unescape_db_markup(self, value: Optional[str]) -> str:
        """
        BD/UI a veces guardan entidades ya escapadas (&amp;), que al volver a
        escapar quedan &amp;amp; en el XML y pueden romper validadores.
        """
        if value is None:
            return ""
        s = str(value).strip()
        for _ in range(6):
            t = html.unescape(s)
            if t == s:
                break
            s = t
        return s.strip()

    def _xml_pcdata(self, value: Optional[str]) -> str:
        """Escape text for XML element character content."""
        return escape(self._unescape_db_markup(value))

    def _xml_pcdata_trunc(self, value: Optional[str], max_len: int) -> str:
        """Trim, truncate to max_len codepoints, then XML-escape."""
        s = self._unescape_db_markup(value)
        if max_len >= 0 and len(s) > max_len:
            s = s[:max_len]
        return escape(s)

    def _normalize_sector_economico_token(self, raw: Optional[str]) -> str:
        """
        Valor para <SectorEconomico>:
        - Subclase SUNAT numérica: 3–6 dígitos (ej. 4923).
        - Tabla local `ciiu.coddivi`: una letra A–Q (ej. H=hoteles, I=transporte).
        """
        t = self._unescape_db_markup(raw).strip()
        if not t:
            return ""
        if t.isdigit() and 3 <= len(t) <= 6:
            return t
        if len(t) == 1 and t.isalpha():
            return t.upper()
        return ""

    def _persona_juridica_sector_economico(self, person: Dict) -> str:
        """
        xml_kardex.php emite <SectorEconomico> desde columna `ciuu`.

        En cliente2 muchos guardan el sector en `actmunicipal`: puede ser la letra
        `coddivi` de la tabla `ciiu`, o un código numérico SUNAT (véase serializer
        actmunicipal ↔ ciiu). Ese valor va a SectorEconomico, no a OtraActividad.
        """
        for key in ("ciuu", "ciuu_empr"):
            v = self._unescape_db_markup(person.get(key)).strip()
            if v:
                return v
        return self._normalize_sector_economico_token(person.get("actmunicipal"))

    def _email_ok(self, addr: str) -> bool:
        if not addr or not addr.strip():
            return False
        try:
            self._email_validator(addr.strip())
            return True
        except ValidationError:
            return False

    def _legacy_text_short(self, raw: Optional[str], max_len: int) -> str:
        """Legacy PHP-style cleanup for OtraProfesion / OtroCargo (trim, collapse noise)."""
        s = self._unescape_db_markup(raw)
        for ch in ("(", ")", "/"):
            s = s.replace(ch, "")
        while "  " in s:
            s = s.replace("  ", " ")
        s = s.strip()
        if max_len >= 0 and len(s) > max_len:
            s = s[:max_len]
        return s

    def _telefono_natural_legacy_ok(self, tel: Optional[str]) -> bool:
        """PHP ValidarIsTelefono: dígitos después de quitar () y -."""
        if not tel or not str(tel).strip():
            return False
        valor = (
            str(tel)
            .replace("(", "")
            .replace(")", "")
            .replace("-", "")
            .strip()
        )
        return valor.isdigit()

    def _tipo_doc_natural_para_xml(self, person: Dict, doc: Dict) -> str:
        """
        Legacy PersonaNatural: mapea tipo 15 → 10; respeta instrumento 2 solo en validación PHP,
        pero el mapeo 15→10 se aplica en la salida XML del PHP original.
        """
        raw = person.get("idtipdoc")
        if raw is None or str(raw).strip() == "":
            return ""
        tip_str = str(raw).strip()
        if tip_str == "15":
            tip_str = "10"
        if tip_str.isdigit():
            return str(int(tip_str)).zfill(2)
        return tip_str

    def _tipo_doc_juridico_para_xml(self, person: Dict, doc: Dict) -> str:
        """Legacy ValidarDocumentoJuridica: fuerza 08 si RUC 11 dígitos; tipo vacío+sin doc → 10."""
        tipo_inst = str(doc.get("idtipkar") or "").strip()
        tip_raw = person.get("idtipdoc")
        numdoc = (person.get("numdoc") or "").strip()
        tip_str = "" if tip_raw is None else str(tip_raw).strip()

        if tipo_inst == "2":
            return tip_str.zfill(2) if tip_str.isdigit() else tip_str

        if tip_str == "":
            if numdoc == "":
                tip_str = "10"
            else:
                return ""
        elif numdoc == "":
            tnorm = tip_str.zfill(2) if tip_str.isdigit() else tip_str
            if tnorm not in ("10", "15"):
                pass
        else:
            tnorm = tip_str.zfill(2) if tip_str.isdigit() else tip_str
            if tnorm != "08" and len(numdoc) == 11 and numdoc.isdigit():
                tip_str = "08"

        if tip_str.isdigit():
            return str(int(tip_str)).zfill(2)
        return tip_str

    def _pais_nacionalidad_codigo(self, person: Dict) -> Optional[str]:
        """Legacy: <PaisNacionalidad> usa codnacion (tabla nacionalidades), no 'PE' fijo."""
        raw = person.get("nacionalidad")
        if raw is None or str(raw).strip() == "":
            return None
        s = str(raw).strip()
        try:
            with connection.cursor() as cursor:
                if s.isdigit():
                    cursor.execute(
                        "SELECT codnacion FROM nacionalidades WHERE idnacionalidad = %s LIMIT 1",
                        [int(s)],
                    )
                else:
                    cursor.execute(
                        "SELECT codnacion FROM nacionalidades WHERE TRIM(UPPER(codnacion)) = TRIM(UPPER(%s)) LIMIT 1",
                        [s],
                    )
                row = cursor.fetchone()
                if row and row[0] and str(row[0]).strip():
                    return str(row[0]).strip()
        except Exception:
            self.logger.warning("No se pudo resolver codnacion para nacionalidad=%r", s)
        if len(s) <= 4 and s.isalpha():
            return s.upper()
        return None

    def _profesion_cod_natural(self, person: Dict) -> Optional[str]:
        """Profesión: idprofesion → codprof; si falta, coincide desprofesion con detaprofesion."""
        ip = person.get("idprofesion")
        if ip not in (None, "", 0, "0"):
            cod = self._get_valid_profession_code(str(ip))
            if cod and cod != "001":
                return cod
        det = (person.get("detaprofesion") or "").strip()
        if not det:
            return None
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT codprof FROM profesiones
                    WHERE TRIM(UPPER(desprofesion)) = TRIM(UPPER(%s))
                    LIMIT 1
                    """,
                    [det],
                )
                row = cursor.fetchone()
                if row and row[0]:
                    return str(row[0]).strip().zfill(3)
        except Exception as e:
            self.logger.warning("profesion por detaprofesion: %s", e)
        return None

    def _cargo_cod_natural(self, person: Dict) -> Optional[str]:
        """Cargo natural: idcargoprofe → codcargoprofe (tabla cargoprofe)."""
        cid = person.get("idcargoprofe")
        if cid in (None, "", 0, "0"):
            return None
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT codcargoprofe FROM cargoprofe WHERE idcargoprofe = %s LIMIT 1",
                    [cid],
                )
                row = cursor.fetchone()
                if row and row[0] is not None and str(row[0]).strip():
                    return str(row[0]).strip()
        except Exception as e:
            self.logger.warning("cargo natural: %s", e)
        return None

    def _persona_juridica_otra_actividad_text(self, person: Dict) -> str:
        """
        Objeto social va en <OtraActividad> (no existe <ObjetoSocial> en el XSD).

        Caso frecuente en cliente2: `actmunicipal` trae solo un código de una letra
        (p. ej. "H") y el texto útil está en `contacempresa`. El patrón antiguo
        `(actmunicipal or contacempresa)` en Python tomaba "H" (truthy) y nunca
        leía contacempresa → RO06. Aquí se exige longitud mínima en actmunicipal.

        Si `actmunicipal` es **solo una letra** (tabla `ciiu.coddivi`) o **solo dígitos**
        (subclase SUNAT), va a <SectorEconomico>, no aquí.

        RO06 si falta sector u objeto social descriptivo en <OtraActividad>.
        """
        # Texto largo típico de actividad / objeto (licencia municipal, etc.)
        min_descriptive = 3
        # `objeto` a veces viene corrupto o como código de 1 letra ("H") por JOIN/BD
        min_objeto_field = 4

        def chunk(key: str) -> str:
            raw = person.get(key)
            if raw is None:
                return ""
            return self._unescape_db_markup(raw)

        actmun = chunk("actmunicipal")
        contem = chunk("contacempresa")

        # 1) actmunicipal reservado para <SectorEconomico> (letra A-Q o dígitos)
        if not self._normalize_sector_economico_token(actmun):
            if len(actmun) >= min_descriptive:
                return actmun
        if len(contem) >= min_descriptive:
            return contem

        for key in ("impeorigen", "impmotivo"):
            s = chunk(key)
            if len(s) >= min_descriptive:
                return s

        # 2) objeto / alias solo si no parece un código basura
        for key in ("objeto", "objsocial", "objetosocial"):
            s = chunk(key)
            if len(s) >= min_objeto_field:
                return s

        # 3) Combinar fragmentos no triviales (evita perder info si está partida)
        merge_keys = (
            "actmunicipal",
            "contacempresa",
            "impeorigen",
            "impmotivo",
            "objeto",
            "objsocial",
            "objetosocial",
        )
        seen = set()
        parts: List[str] = []
        for key in merge_keys:
            s = chunk(key)
            if not s or s in seen:
                continue
            if key == "actmunicipal" and self._normalize_sector_economico_token(s):
                continue
            if key in ("objeto", "objsocial", "objetosocial") and len(s) < min_objeto_field:
                continue
            if len(s) < min_descriptive:
                continue
            seen.add(s)
            parts.append(s)
        merged = ", ".join(parts) if parts else ""
        if len(merged) >= min_descriptive:
            return merged

        # 4) Último recurso: no enviar un solo carácter (RO06); mínimo descriptivo
        for key in merge_keys:
            s = chunk(key)
            if key == "actmunicipal" and self._normalize_sector_economico_token(s):
                continue
            if len(s) >= min_descriptive:
                self.logger.warning(
                    "Persona jurídica id=%s: usando OtraActividad desde %s (revisar calidad); "
                    "ideal: actmunicipal u objeto social completo en cliente.",
                    person.get("idcliente"),
                    key,
                )
                return s

        self.logger.error(
            "Persona jurídica id=%s sin texto válido para <OtraActividad> "
            "(y revise CIIU en actmunicipal/ciuu para <SectorEconomico>, RO06). "
            "Razón social=%r",
            person.get("idcliente"),
            (person.get("razonsocial") or "")[:80],
        )
        return ""

    def _solo_digitos(self, raw) -> str:
        """Solo dígitos para ubigeo / códigos geo (BD a veces trae guiones o texto)."""
        if raw is None:
            return ""
        return "".join(c for c in str(raw).strip() if c.isdigit())

    def _clip_cod_geo_dos(self, x: str) -> str:
        """Un código geo XSD [0-9]{2}: '4'→'04', '040102' erróneo en un campo→últimos 2."""
        if not x:
            return ""
        if len(x) <= 2:
            return x.zfill(2)
        return x[-2:]

    def _partes_ubigeo_pe(
        self,
        idubigeo_raw=None,
        departamento=None,
        provincia=None,
        distrito=None,
    ) -> Tuple[str, str, str]:
        """
        XSD CodDepartamento/CodProvincia/CodDistrito: patrón [0-9]{2} cada uno.
        Si `distrito` (o otro campo) trae el ubigeo de 6 dígitos pegado, se parte.
        """
        ub = self._solo_digitos(idubigeo_raw)
        if len(ub) == 6:
            return ub[:2], ub[2:4], ub[4:6]
        dep = self._solo_digitos(departamento)
        prov = self._solo_digitos(provincia)
        dist = self._solo_digitos(distrito)
        for blob in (dist, dep, prov):
            if len(blob) == 6:
                return blob[:2], blob[2:4], blob[4:6]

        return (
            self._clip_cod_geo_dos(dep),
            self._clip_cod_geo_dos(prov),
            self._clip_cod_geo_dos(dist),
        )

    def _persona_juridica_ubigeo_parts(self, person: Dict) -> Tuple[str, str, str]:
        """Departamento/provincia/distrito para XML SISGEN (2 dígitos c/u)."""
        return self._partes_ubigeo_pe(
            person.get("idubigeo"),
            person.get("departamento"),
            person.get("provincia"),
            person.get("distrito"),
        )

    def _persona_natural_nombre(self, person: Dict) -> str:
        """
        Nombre(s) de pila para <Nombre>. xml_kardex.php usa el campo `nom`
        (primer + segundo nombre); antes solo enviábamos prinom.
        """
        p1 = (person.get("prinom") or "").strip()
        p2 = (person.get("segnom") or "").strip()
        joined = " ".join(x for x in (p1, p2) if x).strip()
        if joined:
            return joined
        return (person.get("nombre") or "").strip()

    def _tipo_instrumento_sisgen(self, doc: Dict) -> str:
        """
        SISGEN <TipoInstrumento>: E/C/V/G/T from kardex.idtipkar (legacy PHP tipokardex).
        Was hardcoded E — broke transferencias vehiculares (idtipkar 3 → V).
        """
        raw = doc.get("idtipkar")
        if raw is None or raw == "":
            return "E"
        try:
            key = int(raw)
        except (TypeError, ValueError):
            self.logger.warning("idtipkar no numérico %r, usando E", raw)
            return "E"
        return TIPO_KARDEX_SISGEN_MAPPING.get(key, "E")

    def _clean_folio(self, folio: str) -> str:
        """Clean folio number by removing non-numeric characters"""
        if not folio:
            return "0"
        return ''.join(c for c in folio if c.isdigit()) or "0"

    def _num_folios_libro_notarial_pe(self, folio_ini: int, folio_fin: int) -> int:
        """
        Folios útiles entre folioini y foliofin en libros con secuencia anverso/vuelta
        por cada número hasta el siguiente: 1 → 1vta → 2 → 2vta → 3 ⇒ 5 (no 3).

        Fórmula: 2 * (folio_fin - folio_ini) + 1 cuando folio_fin >= folio_ini.
        Un solo número de folio (ini == fin) cuenta como 1.
        """
        if folio_fin < folio_ini:
            return 1
        return max(1, 2 * (folio_fin - folio_ini) + 1)

    def _calculate_num_folios(self, doc: Dict) -> int:
        """NumFolios para SISGEN; usa convención libro PE (anverso + vueltas entre números)."""
        try:
            folio_ini = self._clean_folio(doc.get("folioini", "0"))
            folio_fin = self._clean_folio(doc.get("foliofin", "0"))
            fi = int(folio_ini)
            ff = int(folio_fin)
            return self._num_folios_libro_notarial_pe(fi, ff)
        except Exception:
            return 1

    def _add_participant_condition(self, participant: Dict) -> str:
        """Add participant condition"""
        condition = ""
        if participant.get("idcondicion"):
            condition = f'{participant.get("idcondicion")}'
            if participant.get("item"):
                condition += f'.{participant.get("item")}/'
        return condition

    def _safe_float(self, value: str, default: float = 0.0) -> float:
        """Safely convert string to float, returning default if conversion fails"""
        try:
            if not value or value.strip() == '':
                return default
            return float(value)
        except (ValueError, TypeError):
            return default

    def _format_date(self, date_str: str) -> str:
        """Format date to YYYY-MM-DD format"""
        if not date_str:
            return ""
        try:
            # Try parsing with different formats
            for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y']:
                try:
                    date_obj = datetime.strptime(date_str, fmt)
                    return date_obj.strftime('%Y-%m-%d')  # Always return in YYYY-MM-DD format
                except ValueError:
                    continue
            return date_str
        except Exception:
            return date_str

    def _get_notary_codes(self, notary_data: Dict) -> Tuple[str, str]:
        """Get notary codes from confinotario table"""
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT codnotario, ruc 
                    FROM confinotario 
                    LIMIT 1
                """)
                result = cursor.fetchone()
                if result:
                    cod_notario = str(result[0]).strip()
                    cod_notaria = str(result[1]).strip()
                    return cod_notario, cod_notaria
                
                return "00000000", "00000000000"  # Default values
        except Exception as e:
            self.logger.error(f"Error getting notary codes: {str(e)}")
            return "00000000", "00000000000"

    def _get_tipo_intervencion_desc(self, role: str, acto_juridico: str = None, participant_data: Dict = None) -> Tuple[str, str]:
        """TipoIntervencion por rol; DescripcionIntervencion desde actocondicion / vista PHP."""
        try:
            tipo_int = '1' if role == 'O' else '2' if role == 'B' else '3'

            cod_cond = self._codconsisgen_from_actocondicion(participant_data or {})
            if cod_cond:
                return tipo_int, cod_cond

            # For acto_juridico 0909 (ACLARACION), use specific mappings
            if acto_juridico == '0909':
                with connection.cursor() as cursor:
                    # Get the specific type of aclaracion from tiposdeacto
                    cursor.execute("""
                        SELECT idtipoacto, desacto 
                        FROM tiposdeacto 
                        WHERE cod_ancert = %s
                    """, [acto_juridico])
                    result = cursor.fetchone()
                    
                    if result:
                        idtipoacto = result[0]
                        # For ACLARACION DE DONACION (idtipoacto 991)
                        if idtipoacto == '991':
                            if role == 'O':
                                return tipo_int, '084'  # Otorgante in ACLARACION DE DONACION
                            elif role == 'B':
                                return tipo_int, '011'  # Beneficiario in ACLARACION DE DONACION
                        # For ACLARACION Y MODIFICACION PARCIAL DE CONSTITUCION E.I.R.L. (idtipoacto 934)
                        elif idtipoacto == '934':
                            if role == 'O':
                                return tipo_int, '005'  # Otorgante
                            elif role == 'R':
                                return tipo_int, '006'  # Representante
                        # For other types of ACLARACION
                        else:
                            if role == 'O':
                                return tipo_int, '084'  # Default for Otorgante in ACLARACION
                            elif role == 'B':
                                return tipo_int, '011'  # Default for Beneficiario in ACLARACION
                            elif role == 'R':
                                return tipo_int, '006'  # Default for Representante in ACLARACION
            
            # Default mappings for other acto_juridico types
            if role == 'O':
                return tipo_int, '001'
            elif role == 'B':
                return tipo_int, '017'
            elif role == 'R':
                return tipo_int, '003'
            
            return tipo_int, '001'  # default
        except Exception as e:
            self.logger.error(f"Error getting intervention description: {str(e)}")
            return '1', '001'  # default

    def _codconsisgen_from_actocondicion(self, participant: Optional[Dict]) -> Optional[str]:
        """
        Código SISGEN para <DescripcionIntervencion>: tabla actocondicion.codconsisgen
        (legacy PHP / vista sisgen_intervenciones_* por condición).
        """
        if not participant:
            return None
        raw = participant.get("idcondicion")
        if raw is None or str(raw).strip() == "":
            return None
        idc = str(raw).strip()
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT codconsisgen FROM actocondicion
                    WHERE TRIM(idcondicion) = TRIM(%s)
                    LIMIT 1
                    """,
                    [idc],
                )
                row = cursor.fetchone()
                if row and row[0] is not None and str(row[0]).strip():
                    cod = str(row[0]).strip()
                    return cod.zfill(3) if cod.isdigit() else cod
        except DatabaseError as e:
            self.logger.warning("actocondicion no disponible o error DB: %s", e)
        except Exception as e:
            self.logger.error("Error leyendo codconsisgen: %s", e)
        # Vista opcional (algunas instalaciones PHP)
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT condicionnsisgen FROM sisgen_intervenciones_6
                    WHERE TRIM(idcondicion) = TRIM(%s)
                    LIMIT 1
                    """,
                    [idc],
                )
                row = cursor.fetchone()
                if row and row[0] is not None and str(row[0]).strip():
                    cod = str(row[0]).strip()
                    return cod.zfill(3) if cod.isdigit() else cod
        except DatabaseError:
            pass
        return None

    def _resolve_patrimonial_for_doc(self, doc: Dict) -> Optional[Dict]:
        """
        Primera fila patrimonial del acto (importetrans, idmon, itemmp, fpago).
        Alineado con xml_kardex.php por kardex + idtipoacto derivado de codactos.
        """
        kardex = doc.get("kardex")
        codactos = (doc.get("codactos") or "").strip()
        if not kardex:
            return None
        variants = []
        if len(codactos) >= 3:
            p3 = codactos[:3]
            variants.extend([p3, p3.zfill(6)])
        if len(codactos) >= 6:
            variants.append(codactos[:6])

        try:
            with connection.cursor() as cursor:
                for vid in variants:
                    if not vid:
                        continue
                    cursor.execute(
                        """
                        SELECT importetrans, idmon, itemmp, fpago,
                               nminuta, idoppago, exhibiomp
                        FROM patrimonial
                        WHERE kardex = %s AND TRIM(idtipoacto) = TRIM(%s)
                        LIMIT 1
                        """,
                        [kardex, vid],
                    )
                    row = cursor.fetchone()
                    if row and row[0] is not None and float(row[0]) > 0:
                        return {
                            "importetrans": float(row[0]),
                            "idmon": row[1],
                            "itemmp": row[2],
                            "fpago": row[3],
                            "nminuta": row[4],
                            "idoppago": row[5],
                            "exhibiomp": row[6],
                        }
                cursor.execute(
                    """
                    SELECT importetrans, idmon, itemmp, fpago,
                           nminuta, idoppago, exhibiomp
                    FROM patrimonial
                    WHERE kardex = %s
                    ORDER BY itemmp
                    LIMIT 1
                    """,
                    [kardex],
                )
                row = cursor.fetchone()
                if row and row[0] is not None and float(row[0]) > 0:
                    self.logger.warning(
                        "Patrimonial: coincidencia laxa idtipoacto para kardex=%s codactos=%s",
                        kardex,
                        codactos,
                    )
                    return {
                        "importetrans": float(row[0]),
                        "idmon": row[1],
                        "itemmp": row[2],
                        "fpago": row[3],
                        "nminuta": row[4],
                        "idoppago": row[5],
                        "exhibiomp": row[6],
                    }
        except Exception as e:
            self.logger.error("Error leyendo patrimonial: %s", e)
        return None

    def _sisgen_codmon_from_idmon(self, idmon) -> str:
        """Codificación SISGEN de moneda (MONEDAS.codmon), fallback soles."""
        if idmon is None or idmon == "":
            return "01"
        try:
            k = int(idmon)
        except (TypeError, ValueError):
            return "01"
        if k == 0:
            return "01"
        meta = MONEDAS.get(k)
        if meta and meta.get("codmon"):
            return str(meta["codmon"]).zfill(2)
        return "01"

    def _detalle_mediopago_rows(
        self, kardex: Optional[str], itemmp: Optional[str]
    ) -> List[Dict]:
        """Filas detallemediopago ligadas al item patrimonial (ValidarMoneda / medios)."""
        if not kardex:
            return []
        try:
            with connection.cursor() as cursor:
                cols_sql = """
                        SELECT
                            detmp,
                            codmepag,
                            fpago AS dmp_fpago,
                            importemp,
                            idmon AS dmp_idmon,
                            foperacion,
                            idbancos,
                            documentos,
                            itemmp
                        FROM detallemediopago
                """
                if itemmp not in (None, ""):
                    cursor.execute(
                        cols_sql
                        + """
                        WHERE kardex = %s AND TRIM(IFNULL(itemmp,'')) = TRIM(IFNULL(%s,''))
                        ORDER BY detmp
                        """,
                        [kardex, itemmp],
                    )
                else:
                    cursor.execute(
                        cols_sql
                        + """
                        WHERE kardex = %s
                        ORDER BY detmp
                        """,
                        [kardex],
                    )
                cols = [c[0] for c in cursor.description]
                return [dict(zip(cols, row)) for row in cursor.fetchall()]
        except Exception as e:
            self.logger.warning("detallemediopago no legible kardex=%s: %s", kardex, e)
            return []

    def _forma_pago_sisgen(self, fpago_raw) -> Optional[str]:
        """Letra FormaPago cuando fpago no está en FORMAS_PAGO (valor ya en BD)."""
        if fpago_raw is None or str(fpago_raw).strip() == "":
            return None
        s = str(fpago_raw).strip().upper()
        return s[0] if s else None

    def _fecha_firma_element_xml(self, row: Dict, indent_tabs: str) -> str:
        """
        Emite FechaFirma solo con fecha XSD-válida (yyyy-mm-dd). Cadena vacía o no parseable:
        no se emite el elemento — SISGEN rechaza <FechaFirma></FechaFirma> (cvc-datatype-valid date).
        Si la clave no viene en row o es None, tampoco se emite.
        """
        if "fechafirma" not in row:
            return ""
        raw = row.get("fechafirma")
        if raw is None:
            return ""
        s = str(raw).strip()
        if not s:
            return ""
        fd = self._format_date(s)
        if not fd:
            return ""
        return f"{indent_tabs}<FechaFirma>{fd}</FechaFirma>\n"

    def _tiporepresentacion_es_representante(self, participant: Dict) -> bool:
        """contratantes.tiporepresentacion numérica 1 / '01'; evita marcar '02' u otros códigos."""
        t = str(participant.get("tiporepresentacion") or "").strip()
        if not t:
            return False
        try:
            return int(t, 10) == 1
        except ValueError:
            return False

    def _idcontratanterp_coincide(
        self, rep_principal_raw, principal_idcontratante
    ) -> bool:
        if principal_idcontratante is None or rep_principal_raw is None:
            return False
        pid = str(principal_idcontratante).strip()
        raw = str(rep_principal_raw).strip()
        if not pid or not raw:
            return False
        if pid == raw:
            return True
        for token in raw.replace(";", ",").split(","):
            if token.strip() == pid:
                return True
        return False

    def _representantes_filas_directas(
        self, todos_participantes: List[Dict], principal_idcontratante
    ) -> List[Dict]:
        """Filas contratantes con tiporepresentación activa que representan al principal."""
        out: List[Dict] = []
        for p in todos_participantes:
            if not self._tiporepresentacion_es_representante(p):
                continue
            if self._idcontratanterp_coincide(
                p.get("idcontratanterp"), principal_idcontratante
            ):
                out.append(p)
        return out

    def _representante_recursive_xml(
        self,
        rep: Dict,
        todos_participantes: List[Dict],
        indent_representante: int,
        depth: int,
    ) -> str:
        """
        Representante con cadena RepresentanteRepresentante (representante de representante).
        indent_representante: nivel de tabuladores antes de <Representante>.
        """
        max_rr_depth = 6
        skip_nested = depth > max_rr_depth
        if skip_nested:
            self.logger.warning(
                "Representantes anidados truncados en profundidad %s idcontratante=%s",
                depth,
                rep.get("idcontratante"),
            )

        TAB = "\t"
        t_r = TAB * indent_representante
        t_r1 = TAB * (indent_representante + 1)
        t_r2 = TAB * (indent_representante + 2)

        xml_parts: List[str] = [f"{t_r}<Representante>\n"]
        xml_parts.append(f'{t_r1}<IdMaestro>{rep.get("idcliente", "")}</IdMaestro>\n')

        rep_part = rep.get("numpartidareg") or rep.get("numpartida")
        if rep.get("inscrito") == "1" and (rep.get("idsedereg") or rep_part):
            xml_parts.append(f"{t_r1}<InscripcionRepresentacion>\n")
            if rep.get("idsedereg"):
                xml_parts.append(
                    f'{t_r2}<SedeRegistral>{rep.get("idsedereg", "")}</SedeRegistral>\n'
                )
            if rep_part:
                xml_parts.append(
                    f'{t_r2}<PartidaRegistral>{escape(str(rep_part).strip())}'
                    f"</PartidaRegistral>\n"
                )
            xml_parts.append(f"{t_r1}</InscripcionRepresentacion>\n")

        xml_parts.append(self._fecha_firma_element_xml(rep, t_r1))

        nested = (
            []
            if skip_nested
            else self._representantes_filas_directas(
                todos_participantes, rep.get("idcontratante")
            )
        )
        if nested:
            xml_parts.append(f"{t_r1}<Representantes>\n")
            for nr in nested:
                xml_parts.append(f"{t_r2}<RepresentanteRepresentante>\n")
                xml_parts.append(
                    self._representante_recursive_xml(
                        nr,
                        todos_participantes,
                        indent_representante + 3,
                        depth + 1,
                    )
                )
                xml_parts.append(f"{t_r2}</RepresentanteRepresentante>\n")
            xml_parts.append(f"{t_r1}</Representantes>\n")

        xml_parts.append(f"{t_r}</Representante>\n")
        return "".join(xml_parts)

    def _representantes_bajo_sujeto_xml(
        self,
        principal_idcontratante,
        todos_participantes: List[Dict],
    ) -> str:
        """Bloque <Representantes> bajo <Sujeto> con soporte R-de-R."""
        reps = self._representantes_filas_directas(
            todos_participantes, principal_idcontratante
        )
        base_wrap = "\t" * 7
        base_row = 8
        xml_parts = [f"{base_wrap}<Representantes>\n"]
        for rep in reps:
            xml_parts.append(
                self._representante_recursive_xml(
                    rep, todos_participantes, indent_representante=base_row, depth=0
                )
            )
        xml_parts.append(f"{base_wrap}</Representantes>\n")
        return "".join(xml_parts)

    def _participante_marcador_no_interviniente(self, p: Dict) -> bool:
        """
        Flags opcionales de BD/vistas PHP (repre, firma, visita == 'N') fuera de uif='N'
        para evitar confundir con rol SUNAT en garantías.
        """
        if str(p.get("repre") or "").strip().upper() == "N":
            return True
        if str(p.get("firma") or "").strip().upper() == "N":
            return True
        if str(p.get("visita") or "").strip().upper() == "N":
            return True
        return False

    def _coleccion_no_interviniente_ids(
        self,
        participants: List[Dict],
        sujeto_id_maestro_emisor_ids: Set[str],
    ) -> List[str]:
        """Ids Maestro declarados como no intervinientes (marcadores + cónyuges casados)."""
        collected: List[str] = []
        seen: Set[str] = set()

        def push(cid: str) -> None:
            cid = cid.strip()
            if not cid or cid == "0" or cid in seen:
                return
            if cid in sujeto_id_maestro_emisor_ids:
                return
            seen.add(cid)
            collected.append(cid)

        for p in participants:
            ic = str(p.get("idcliente") or "").strip()
            if self._participante_marcador_no_interviniente(p) and ic:
                push(ic)

        for p in participants:
            if str(p.get("tipper") or "").strip().upper() != "N":
                continue
            if str(p.get("idestcivil") or "").strip() != "2":
                continue
            cy = str(p.get("conyuge") or "").strip()
            if not cy or cy in ("0", "0000000000"):
                continue
            uif_role = (p.get("uif") or "").strip().upper()
            if uif_role == "R":
                continue
            push(cy)

        return sorted(collected)

    def _cuantia_origen_participant(
        self, participant: Dict, doc: Dict, pat_row: Optional[Dict]
    ) -> float:
        """Monto línea intervención: cx.monto; si falta y hay un solo sujeto con fondo, usa patrimonial."""
        cuantia = self._safe_float(participant.get("monto", "0.00"))
        if cuantia > 0:
            return cuantia
        if not pat_row or not participant.get("ofondo"):
            return cuantia
        parts = doc.get("participants") or []
        with_fondo = [
            p
            for p in parts
            if (p.get("uif") or "").strip().upper() in ("O", "B")
            and (p.get("ofondo") or "").strip()
        ]
        if len(with_fondo) == 1:
            return float(pat_row["importetrans"])
        return cuantia

    def _doc_requires_renta_impuesto_xml(self, doc: Dict) -> bool:
        """
        PHP: preguntas renta (pregu*) en XML cuando aplica UIF/SUNAT al acto.
        Alineado con la lógica relajada de validación _sisgen_skip_uif_money_checks.
        """
        au = (doc.get("actouif") or "").strip().upper()
        if au in ("N", "NO", "0", "NINGUNO", "-"):
            return False
        if au:
            return True
        asn = (doc.get("actosunat") or "").strip().upper()
        return bool(asn and asn not in ("N", "NO", "0", "-"))

    def _normalize_pregunta_renta_xml(self, raw) -> str:
        """Normaliza pregu1..3 de tabla renta a 0/1 para elementos SISGEN."""
        if raw is None:
            return "0"
        s = str(raw).strip().upper()
        if not s:
            return "0"
        if s in ("1", "S", "SI", "Y", "YES", "TRUE"):
            return "1"
        if s in ("0", "N", "NO"):
            return "0"
        if s[0].isdigit():
            return "0" if s[0] == "0" else "1"
        return "0"

    def _renta_map_for_kardex(
        self, kardex: Optional[str], idcontratantes: List[str]
    ) -> Dict[str, Dict]:
        """Última fila renta por contratante (MAX idrenta), kardex + idcontratante."""
        cleaned = sorted(
            {str(x).strip() for x in idcontratantes if x is not None and str(x).strip()}
        )
        if not kardex or not cleaned:
            return {}
        placeholders = ",".join(["%s"] * len(cleaned))
        sql = f"""
            SELECT r.idcontratante, r.pregu1, r.pregu2, r.pregu3
            FROM renta r
            INNER JOIN (
                SELECT idcontratante, MAX(idrenta) AS mx
                FROM renta
                WHERE kardex = %s AND idcontratante IN ({placeholders})
                GROUP BY idcontratante
            ) z ON z.idcontratante = r.idcontratante
                AND z.mx = r.idrenta
                AND r.kardex = %s
        """
        params = [kardex, *cleaned, kardex]
        try:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                out: Dict[str, Dict] = {}
                for row in cursor.fetchall():
                    ic = str(row[0]).strip()
                    out[ic] = {"pregu1": row[1], "pregu2": row[2], "pregu3": row[3]}
                return out
        except Exception as e:
            self.logger.warning("No se pudo cargar renta para kardex=%s: %s", kardex, e)
            return {}

    def _renta_impuesto_triplet_xml(
        self,
        participant: Dict,
        renta_map: Dict[str, Dict],
        use_db: bool,
    ) -> Tuple[str, str, str]:
        """pregu1→Renta3Cat, pregu2→CasaEnajenante, pregu3→ImpuestoCero."""
        if not use_db:
            return ("0", "0", "0")
        ic = str(participant.get("idcontratante") or "").strip()
        row = renta_map.get(ic)
        if not row:
            return ("0", "0", "0")
        return (
            self._normalize_pregunta_renta_xml(row.get("pregu1")),
            self._normalize_pregunta_renta_xml(row.get("pregu2")),
            self._normalize_pregunta_renta_xml(row.get("pregu3")),
        )

    def _get_valid_profession_code(self, code: str) -> str:
        """Get valid SISGEN profession code from database"""
        if not code:
            return "001"  # Default code
        
        try:
            with connection.cursor() as cursor:
                # Try to find the matching profession code
                cursor.execute("""
                    SELECT codprof 
                    FROM profesiones 
                    WHERE idprofesion = %s
                """, [code])
                result = cursor.fetchone()
                if result and result[0]:
                    return str(result[0]).zfill(3)
        except Exception as e:
            self.logger.error(f"Error getting profession code: {str(e)}")
        
        return "001"  # Default if not found or error

    def _cuantia_operacion_total(self, doc: Dict, participants: List[Dict]) -> float:
        """
        Monto total de la operación para <CuantiaOperacion> / <CuantiaPago>.

        xml_kardex.php toma `patrimonial.importetrans` por acto, no la suma de todas
        las filas de contratantesxacto. Sumar todos los `participants` duplica cuando
        hay varias filas cx para el mismo kardex (ítems/condiciones) o cuando varios
        roles llevan el mismo monto informado.
        """
        pat = self._resolve_patrimonial_for_doc(doc)
        if pat and pat.get("importetrans"):
            return float(pat["importetrans"])

        kardex = doc.get("kardex")
        codactos = (doc.get("codactos") or "").strip()

        # Una fila por combinación lógica en cx (reduce duplicados por JOIN repetido)
        seen = set()
        fallback = 0.0
        for p in participants:
            key = (
                p.get("idcontratante"),
                p.get("item"),
                p.get("idcondicion"),
                str(p.get("idtipoacto") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            fallback += self._safe_float(p.get("monto", "0.00"))

        self.logger.warning(
            "CuantiaOperacion sin patrimonial válido para kardex=%s codactos=%s; "
            "suma deduplicada por (idcontratante, item, idcondicion, idtipoacto), "
            "filas=%s",
            kardex,
            codactos,
            len(seen),
        )
        return fallback

    def _acto_code_for_objects(self, doc: Dict) -> str:
        """Use first 3 digits of codactos as current acto code."""
        codactos = (doc.get("codactos") or "").strip()
        if len(codactos) >= 3:
            return codactos[:3]
        return codactos

    def _load_bienes_for_doc(self, doc: Dict) -> Dict[str, List[Dict]]:
        """Load bienes from legacy tables for one kardex."""
        kardex = (doc.get("kardex") or "").strip()
        acto_code = self._acto_code_for_objects(doc)
        bienes = {
            "predios": [],
            "vehiculos_bienes": [],
            "vehiculos_detalle": [],
            "otros": [],
        }
        if not kardex:
            return bienes

        with connection.cursor() as cursor:
            # Predios urbanos (codbien 04)
            cursor.execute(
                """
                SELECT db.detbien, db.idtipacto, db.fechaconst, db.pregistral, db.idsedereg,
                       u.coddis, u.codprov, u.codpto
                FROM detallebienes db
                LEFT JOIN tipobien tb ON tb.idtipbien = db.idtipbien
                LEFT JOIN ubigeo u ON u.coddis = db.coddis
                WHERE db.kardex = %s AND tb.codbien = '04'
                """,
                [kardex],
            )
            cols = [c[0] for c in cursor.description]
            bienes["predios"] = [dict(zip(cols, r)) for r in cursor.fetchall()]

            # Vehiculos from detallebienes (codbien 09)
            cursor.execute(
                """
                SELECT db.detbien, db.idtipacto, db.npsm, db.pregistral, db.idsedereg
                FROM detallebienes db
                LEFT JOIN tipobien tb ON tb.idtipbien = db.idtipbien
                WHERE db.kardex = %s AND tb.codbien = '09'
                """,
                [kardex],
            )
            cols = [c[0] for c in cursor.description]
            bienes["vehiculos_bienes"] = [dict(zip(cols, r)) for r in cursor.fetchall()]

            # Vehiculos from detallevehicular
            cursor.execute(
                """
                SELECT detveh, idtipacto, idplaca, numplaca, clase, marca, anofab, modelo,
                       combustible, carroceria, color, motor, numcil, numserie, numrueda,
                       pregistral, idsedereg
                FROM detallevehicular
                WHERE kardex = %s
                """,
                [kardex],
            )
            cols = [c[0] for c in cursor.description]
            bienes["vehiculos_detalle"] = [dict(zip(cols, r)) for r in cursor.fetchall()]

            # Otros objetos (codbien 99)
            cursor.execute(
                """
                SELECT db.detbien, db.idtipacto, db.oespecific
                FROM detallebienes db
                LEFT JOIN tipobien tb ON tb.idtipbien = db.idtipbien
                WHERE db.kardex = %s AND tb.codbien = '99'
                """,
                [kardex],
            )
            cols = [c[0] for c in cursor.description]
            bienes["otros"] = [dict(zip(cols, r)) for r in cursor.fetchall()]

        # operation objects should align with current acto when possible
        if acto_code:
            for key in ("predios", "vehiculos_bienes", "otros"):
                bienes[key] = [
                    b
                    for b in bienes[key]
                    if str(b.get("idtipacto") or "").strip() in {acto_code, acto_code.zfill(6)}
                ]
        return bienes

    def _medios_pago_filas_enriquecidas(self, kardex: Optional[str]) -> List[Dict]:
        """
        Legado PHP: detallemediopago + patrimonial + mediospago + bancos por kardex.
        Si el JOIN falla (tablas/columnas distintas), cae al SELECT simple de detallemediopago.
        """
        if not kardex:
            return []
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        dmp.detmp,
                        dmp.codmepag,
                        dmp.fpago AS dmp_fpago,
                        dmp.importemp,
                        dmp.idmon AS dmp_idmon,
                        dmp.foperacion,
                        dmp.idbancos,
                        dmp.documentos,
                        dmp.itemmp,
                        mp.sunat AS mp_sunat,
                        mp.desmpagos AS mp_des,
                        pat.fpago AS pat_fpago,
                        pat.idoppago AS pat_idoppago,
                        pat.exhibiomp AS pat_exhibiomp,
                        ban.desbanco AS ban_des
                    FROM detallemediopago dmp
                    LEFT JOIN mediospago mp ON mp.codmepag = dmp.codmepag
                    LEFT JOIN patrimonial pat
                        ON pat.kardex = dmp.kardex
                        AND TRIM(IFNULL(pat.itemmp, '')) = TRIM(IFNULL(dmp.itemmp, ''))
                    LEFT JOIN bancos ban ON ban.idbancos = dmp.idbancos
                    WHERE dmp.kardex = %s
                    ORDER BY dmp.detmp
                    """,
                    [kardex],
                )
                cols = [c[0] for c in cursor.description]
                return [dict(zip(cols, row)) for row in cursor.fetchall()]
        except DatabaseError as e:
            self.logger.warning(
                "Medios de pago enriquecidos no disponibles kardex=%s: %s",
                kardex,
                e,
            )
            return self._detalle_mediopago_rows(kardex, None)

    NOMBRE_CONTRATO_MAX = 200

    def _forma_pago_codigo_fpago(self, fp_raw) -> Optional[str]:
        """Letra FormaPago desde fpago en BD (catálogo FORMAS_PAGO / detalle). Sin default."""
        if fp_raw is None or str(fp_raw).strip() == "":
            return None
        key = str(fp_raw).strip()
        meta = FORMAS_PAGO.get(key)
        if meta and meta.get("codigo"):
            cod = str(meta["codigo"]).strip()[:1]
            return cod if cod else None
        return self._forma_pago_sisgen(fp_raw)

    def _momento_pago_codigo(self, idoppago_raw) -> Optional[str]:
        """MomentoPago numérico desde patrimonial.idoppago (catálogo OPORTUNIDADES_PAGO)."""
        if idoppago_raw is None or str(idoppago_raw).strip() == "":
            return None
        try:
            idx = int(str(idoppago_raw).strip(), 10)
            meta = OPORTUNIDADES_PAGO.get(idx)
            if not meta or not str(meta.get("codoppago") or "").strip():
                return None
            co = str(meta["codoppago"]).strip()
            if co.isdigit():
                return str(int(co, 10))
            return co[:2] if co else None
        except (ValueError, TypeError):
            return None

    def _descripcion_momento_pago(self, idoppago_raw) -> str:
        if idoppago_raw is None or str(idoppago_raw).strip() == "":
            return ""
        try:
            idx = int(str(idoppago_raw).strip(), 10)
            meta = OPORTUNIDADES_PAGO.get(idx) or {}
            if not str(meta.get("codoppago") or "").strip():
                return ""
            return meta.get("desoppago", "") or ""
        except (ValueError, TypeError):
            return ""

    def _justificado_manifestado_medio(
        self, exhib_row, exhib_pat_fallback
    ) -> str:
        ex = (
            exhib_row
            if exhib_row is not None and str(exhib_row).strip() != ""
            else exhib_pat_fallback
        )
        s = str(ex or "").strip().upper()
        if s in ("0", "N", "NO"):
            return "0"
        return "1"

    def _entidad_financiera_codigo(self, row: Dict) -> Optional[str]:
        bid = row.get("idbancos")
        if bid is None or str(bid).strip() == "":
            return None
        try:
            return str(int(str(bid).strip(), 10)).zfill(5)
        except ValueError:
            s = str(bid).strip()
            return (s[:5]).zfill(5) if s else None

    def _id_pago_medio(self, row: Dict) -> Optional[str]:
        doc = str(row.get("documentos") or "").strip()
        if doc.isdigit():
            return doc[:15]
        det = row.get("detmp")
        if det is not None and str(det).strip():
            return str(det).strip()[:15]
        return None

    def _medio_pago_codigo(self, r: Dict) -> Optional[str]:
        """Código SISGEN desde mediospago.sunat o detallemediopago.codmepag (sin default)."""
        ms = r.get("mp_sunat")
        if ms is not None and str(ms).strip().isdigit():
            return str(int(str(ms).strip(), 10)).zfill(3)
        cm = r.get("codmepag")
        if cm is not None and str(cm).strip().isdigit():
            return str(int(str(cm).strip(), 10)).zfill(3)
        return None

    def _sisgen_codmon_from_idmon_optional(self, idmon) -> Optional[str]:
        if idmon is None or str(idmon).strip() in ("", "0"):
            return None
        try:
            k = int(idmon)
        except (TypeError, ValueError):
            return None
        meta = MONEDAS.get(k)
        if meta and meta.get("codmon"):
            return str(meta["codmon"]).zfill(2)
        return None

    def _nombre_contrato_sisgen(self, doc: Dict) -> str:
        """PHP: desacto (tiposdeacto) truncado; fallback texto contrato en kardex."""
        des = self._unescape_db_markup(doc.get("desacto"))
        if des and des.strip():
            return escape(des.strip()[: self.NOMBRE_CONTRATO_MAX])
        c = (doc.get("contrato") or "").strip().strip(" /")
        return escape(c[: self.NOMBRE_CONTRATO_MAX])

    def _fecha_minuta_sisgen(
        self,
        doc: Dict,
        pat_row: Optional[Dict],
        mp_rows: List[Dict],
    ) -> str:
        """PHP: patrimonial.nminuta o fecha operación detallemediopago; fallback fecha escritura."""
        candidates = []
        if pat_row:
            candidates.append(pat_row.get("nminuta"))
        if mp_rows:
            candidates.append(mp_rows[0].get("foperacion"))
        candidates.append(doc.get("fechaescritura"))
        for c in candidates:
            if c is None or str(c).strip() == "":
                continue
            fd = self._format_date(str(c).strip())
            if fd:
                return fd
        return self._format_date(str(doc.get("fechaescritura") or "").strip()) or ""

    def _tiposdeacto_mediospago_flag(self, doc: Dict) -> Optional[str]:
        """Flag tiposdeacto.mediospago (legado): S exige XML; N no."""
        cod_ancert = str(doc.get("cod_ancert") or "").strip()
        codactos = str(doc.get("codactos") or "").strip()
        candidates: List[str] = []
        if cod_ancert:
            candidates.append(cod_ancert)
        if len(codactos) >= 3:
            p3 = codactos[:3]
            candidates.extend([p3, p3.zfill(6)])
        if len(codactos) >= 6:
            candidates.append(codactos[:6])
        seen: Set[str] = set()
        ordered = []
        for c in candidates:
            c = c.strip()
            if c and c not in seen:
                seen.add(c)
                ordered.append(c)
        if not ordered:
            return None
        try:
            with connection.cursor() as cursor:
                for vid in ordered:
                    cursor.execute(
                        """
                        SELECT mediospago FROM tiposdeacto
                        WHERE TRIM(IFNULL(cod_ancert, '')) = TRIM(%s)
                           OR TRIM(idtipoacto) = TRIM(%s)
                        LIMIT 1
                        """,
                        [vid, vid],
                    )
                    row = cursor.fetchone()
                    if row and row[0] is not None and str(row[0]).strip() != "":
                        return str(row[0]).strip().upper()
        except Exception as e:
            self.logger.warning("tiposdeacto.mediospago no legible: %s", e)
        return None

    def _acto_requiere_medios_pago_xml(
        self, doc: Dict, pat_row: Optional[Dict]
    ) -> bool:
        """
        PHP xml_kardex: si tiposdeacto.mediospago = N no arma bloque; si S (o acto con
        cuantía) sí — SISGEN rechaza CodActoJuridico 0215 sin <MediosPagos>.
        """
        flag = self._tiposdeacto_mediospago_flag(doc)
        if flag == "N":
            return False
        if flag in ("S", "1"):
            return True
        if pat_row and float(pat_row.get("importetrans") or 0) > 0:
            return True
        return bool(str(doc.get("cod_ancert") or "").strip())

    def _lookup_mediospago_sunat_by_codmepag(self, codmepag: int) -> Optional[str]:
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT sunat, codmepag FROM mediospago
                    WHERE codmepag = %s LIMIT 1
                    """,
                    [codmepag],
                )
                row = cursor.fetchone()
        except DatabaseError:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT codmepag FROM mediospago WHERE codmepag = %s LIMIT 1",
                        [codmepag],
                    )
                    row = cursor.fetchone()
                    if row and row[0] is not None:
                        return str(int(row[0], 10)).zfill(3)
            except Exception:
                return None
            return None
        except Exception as e:
            self.logger.warning("mediospago codmepag=%s: %s", codmepag, e)
            return None
        if not row:
            return None
        sunat, cm = row[0], row[1]
        if sunat is not None and str(sunat).strip().isdigit():
            return str(int(str(sunat).strip(), 10)).zfill(3)
        if cm is not None and str(cm).strip().isdigit():
            return str(int(str(cm).strip(), 10)).zfill(3)
        return None

    def _lookup_mediospago_sunat_by_descripcion(self, fragment: str) -> Optional[str]:
        frag = (fragment or "").strip()
        if not frag:
            return None
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT sunat, codmepag FROM mediospago
                    WHERE UPPER(IFNULL(desmpagos, '')) LIKE UPPER(%s)
                    LIMIT 1
                    """,
                    [f"%{frag}%"],
                )
                row = cursor.fetchone()
        except DatabaseError:
            return None
        except Exception as e:
            self.logger.warning("mediospago descripcion %r: %s", frag, e)
            return None
        if not row:
            return None
        sunat, cm = row[0], row[1]
        if sunat is not None and str(sunat).strip().isdigit():
            return str(int(str(sunat).strip(), 10)).zfill(3)
        if cm is not None and str(cm).strip().isdigit():
            return str(int(str(cm).strip(), 10)).zfill(3)
        return None

    def _resolve_medio_pago_sunat_for_patrimonial(
        self, pat_row: Dict, doc: Dict
    ) -> Optional[str]:
        """
        Sin detallemediopago: mediospago.sunat desde catálogo según patrimonial.

        fpago 5 (NO APLICA) + idoppago vacío + exhibiomp No NO debe mapear a efectivo
        008/009 — eso era un fallthrough incorrecto. Efectivo solo aplica a fpago contado
        (u otras formas onerosas), no a actos gratuitos / NO APLICA.
        """
        del doc
        fp = str(pat_row.get("fpago") or "").strip()
        exhib = str(pat_row.get("exhibiomp") or "").strip().upper()

        def by_codmepag(*codes: int) -> Optional[str]:
            for cm in codes:
                cod = self._lookup_mediospago_sunat_by_codmepag(cm)
                if cod:
                    return cod
            return None

        def by_desc(*fragments: str) -> Optional[str]:
            for frag in fragments:
                cod = self._lookup_mediospago_sunat_by_descripcion(frag)
                if cod:
                    return cod
            return None

        # Forma de pago NO APLICA (fpago=5) — típico K2 / 0215 gratuito
        if fp == "5":
            return (
                by_desc("NO APLICA", "NO APLICA.", "N/A")
                or by_codmepag(99, 1)
            )

        if fp == "4":
            return by_desc("DONACION", "DONACI") or by_codmepag(99, 1)

        # Contado u otras formas onerosas sin detalle: efectivo solo si no exhibió medio
        if exhib in ("NO", "N", "0") and fp in ("1", "2", "3", ""):
            return by_codmepag(8, 9) or by_codmepag(1, 99)

        return by_codmepag(1, 99, 11, 10)

    def _synthetic_medio_row_from_patrimonial(
        self, pat_row: Dict, doc: Dict
    ) -> Optional[Dict]:
        sunat = self._resolve_medio_pago_sunat_for_patrimonial(pat_row, doc)
        if not sunat:
            return None
        fop = pat_row.get("nminuta") or doc.get("fechaescritura")
        return {
            "mp_sunat": sunat,
            "pat_fpago": pat_row.get("fpago"),
            "pat_idoppago": pat_row.get("idoppago"),
            "pat_exhibiomp": pat_row.get("exhibiomp"),
            "dmp_idmon": pat_row.get("idmon"),
            "importemp": pat_row.get("importetrans"),
            "foperacion": fop,
        }

    def _medio_pago_xml_block(
        self,
        r: Dict,
        *,
        fp_pat,
        idopp_pat,
        exhib_pat,
    ) -> Optional[str]:
        """
        Un bloque <MediosPago> por fila detallemediopago.
        Sin filas en BD o sin código de medio → no se emite nada inventado.
        """
        medio = self._medio_pago_codigo(r)
        if not medio:
            self.logger.warning(
                "detallemediopago sin codmepag/mediospago.sunat (detmp=%s)",
                r.get("detmp"),
            )
            return None

        fp_use = r.get("dmp_fpago") or r.get("pat_fpago") or fp_pat
        forma = self._forma_pago_codigo_fpago(fp_use)
        if not forma:
            self.logger.warning(
                "detallemediopago sin fpago válido (detmp=%s)", r.get("detmp")
            )
            return None

        mon_mp = self._sisgen_codmon_from_idmon_optional(r.get("dmp_idmon"))
        if not mon_mp:
            self.logger.warning(
                "detallemediopago sin idmon válido (detmp=%s)", r.get("detmp")
            )
            return None

        idopp_use = r.get("pat_idoppago")
        if idopp_use in (None, ""):
            idopp_use = idopp_pat
        momento = self._momento_pago_codigo(idopp_use)
        desc_mom = self._descripcion_momento_pago(idopp_use)
        cuant_mp = self._safe_float(str(r.get("importemp") or "0"), default=0.0)
        justif = self._justificado_manifestado_medio(
            r.get("pat_exhibiomp"), exhib_pat
        )
        fecha_op = self._format_date(str(r.get("foperacion") or "").strip())
        id_pago = self._id_pago_medio(r)
        entidad = self._entidad_financiera_codigo(r)

        parts = ["\t\t<MediosPago>\n"]
        parts.append(f"\t\t\t<MedioPago>{medio}</MedioPago>\n")
        parts.append(f"\t\t\t<FormaPago>{forma}</FormaPago>\n")
        if momento is not None:
            parts.append(f"\t\t\t<MomentoPago>{momento}</MomentoPago>\n")
        if desc_mom:
            parts.append(
                f"\t\t\t<DescripcionMomentoPago>"
                f"{escape(desc_mom[:200])}</DescripcionMomentoPago>\n"
            )
        parts.append(f"\t\t\t<CuantiaPago>{cuant_mp:.2f}</CuantiaPago>\n")
        parts.append(f"\t\t\t<TipoMonedaPago>{mon_mp}</TipoMonedaPago>\n")
        parts.append(
            f"\t\t\t<JustificadoManifestado>{justif}</JustificadoManifestado>\n"
        )
        if fecha_op:
            parts.append(f"\t\t\t<FechaPago>{fecha_op}</FechaPago>\n")
        if id_pago:
            parts.append(f"\t\t\t<IdPago>{escape(id_pago)}</IdPago>\n")
        if entidad:
            parts.append(
                f"\t\t\t<EntidadFinanciera>{entidad}</EntidadFinanciera>\n"
            )
        parts.append("\t\t</MediosPago>\n")
        return "".join(parts)

    def _medios_pagos_xml_for_doc(
        self,
        doc: Dict,
        pat_row: Optional[Dict],
        mp_rows: List[Dict],
        tipo_moneda_doc: str,
        total_monto: float,
    ) -> str:
        fp_pat = pat_row.get("fpago") if pat_row else None
        idopp_pat = pat_row.get("idoppago") if pat_row else None
        exhib_pat = pat_row.get("exhibiomp") if pat_row else None

        blocks: List[str] = []
        for r in mp_rows:
            block = self._medio_pago_xml_block(
                r,
                fp_pat=fp_pat,
                idopp_pat=idopp_pat,
                exhib_pat=exhib_pat,
            )
            if block:
                blocks.append(block)

        if not blocks and pat_row and self._acto_requiere_medios_pago_xml(doc, pat_row):
            synthetic = self._synthetic_medio_row_from_patrimonial(pat_row, doc)
            if synthetic:
                block = self._medio_pago_xml_block(
                    synthetic,
                    fp_pat=fp_pat,
                    idopp_pat=idopp_pat,
                    exhib_pat=exhib_pat,
                )
                if block:
                    blocks.append(block)
                else:
                    self.logger.warning(
                        "MediosPago patrimonial incompleto kardex=%s cod_ancert=%s",
                        doc.get("kardex"),
                        doc.get("cod_ancert"),
                    )
            else:
                self.logger.warning(
                    "Sin detallemediopago y sin codigo mediospago en catalogo "
                    "kardex=%s cod_ancert=%s fpago=%s",
                    doc.get("kardex"),
                    doc.get("cod_ancert"),
                    fp_pat,
                )

        if not blocks:
            return ""

        return "\t\t<MediosPagos>\n" + "".join(blocks) + "\t\t</MediosPagos>\n"

    def _collect_assembly_errors(self, doc: Dict) -> List[str]:
        """Validaciones de armado XML (legado PHP antes del envío)."""
        errs: List[str] = []
        cod_a = str(doc.get("cod_ancert") or "").strip()
        kardex = doc.get("kardex")

        # Mismo criterio que NumFolios en XML: _clean_folio + enteros (PHP/legado suele
        # guardar folios con sufijos o texto; int(float(...)) fallaba y bloqueaba el envío).
        try:
            fi_s = self._clean_folio(
                str(doc.get("folioini") if doc.get("folioini") is not None else "")
            )
            ff_s = self._clean_folio(
                str(doc.get("foliofin") if doc.get("foliofin") is not None else "")
            )
            fi = int(fi_s)
            ff = int(ff_s)
        except (TypeError, ValueError):
            errs.append("folios no numéricos")
        else:
            if ff < fi:
                errs.append("folio final menor que inicial")

        if cod_a != "0919":
            for p in doc.get("participants") or []:
                ic = p.get("idcontratante")
                if p.get("idcondicion") is None or str(p.get("idcondicion")).strip() == "":
                    errs.append(f"participante sin condición (idcontratante={ic})")
                if p.get("uif") is None or str(p.get("uif")).strip() == "":
                    errs.append(f"participante sin UIF (idcontratante={ic})")

            pat_row = self._resolve_patrimonial_for_doc(doc)
            mp_rows = self._medios_pago_filas_enriquecidas(doc.get("kardex"))
            if self._acto_requiere_medios_pago_xml(doc, pat_row):
                if not mp_rows:
                    if not pat_row:
                        errs.append(
                            "medios de pago: el acto exige MediosPagos pero no hay patrimonial"
                        )
                    elif not self._resolve_medio_pago_sunat_for_patrimonial(
                        pat_row, doc
                    ):
                        errs.append(
                            "medios de pago: sin filas en detallemediopago y sin "
                            "código en catálogo mediospago (fpago NO APLICA / donación)"
                        )

        num_esc = str(doc.get("numescritura") or "").strip()
        id_tip = doc.get("idtipkar")
        if kardex and num_esc:
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT COUNT(*) FROM kardex
                        WHERE TRIM(numescritura) = TRIM(%s)
                          AND kardex <> %s
                          AND IFNULL(idtipkar, -1) = IFNULL(%s, -1)
                        """,
                        [num_esc, kardex, id_tip],
                    )
                    row = cursor.fetchone()
                    if row and int(row[0]) > 0:
                        errs.append(
                            f"número de escritura duplicado ({num_esc}) en otro kardex "
                            "con el mismo tipo de instrumento"
                        )
            except Exception as e:
                self.logger.warning("Validación escritura duplicada no ejecutada: %s", e)

        return errs

    def _xml_seccion_documento(self, doc: Dict) -> str:
        """Bloque <Documento>...</Documento> reutilizable."""
        notary_data = doc.get("notary_data", {})
        cod_notario, cod_notaria = self._get_notary_codes(notary_data)
        parts = ["\t<Documento>\n"]
        parts.append(f"\t\t<CodNotario>{cod_notario}</CodNotario>\n")
        parts.append(f"\t\t<CodNotaria>{cod_notaria}</CodNotaria>\n")
        parts.append(f'\t\t<NumKardex>{doc.get("kardex", "")}</NumKardex>\n')
        parts.append(
            f'\t\t<FechaIngreso>{self._format_date(doc.get("fechaingreso", ""))}</FechaIngreso>\n'
        )
        parts.append(
            f"\t\t<TipoInstrumento>{self._tipo_instrumento_sisgen(doc)}</TipoInstrumento>\n"
        )
        parts.append(f'\t\t<NumDocumento>{doc.get("numescritura", "")}</NumDocumento>\n')
        parts.append(
            f'\t\t<FechaInstrumento>{doc.get("fechaescritura", "")}</FechaInstrumento>\n'
        )
        parts.append(
            f'\t\t<NumFolios>{self._calculate_num_folios(doc)}</NumFolios>\n'
        )
        if doc.get("fechaconclusion"):
            parts.append(
                f'\t\t<FechaConclusion>{self._format_date(doc.get("fechaconclusion", ""))}</FechaConclusion>\n'
            )
        parts.append("\t</Documento>\n")
        return "".join(parts)

    def _documento_notarial_xml_minimo_0919(self, doc: Dict) -> str:
        """Atajo PHP cod_ancert == 0919: XML reducido."""
        pat_row = self._resolve_patrimonial_for_doc(doc)
        tipo_moneda_doc = self._sisgen_codmon_from_idmon(
            pat_row.get("idmon") if pat_row else None
        )
        mp_rows = self._medios_pago_filas_enriquecidas(doc.get("kardex"))
        total_monto = self._cuantia_operacion_total(doc, doc.get("participants") or [])
        nombre_c = self._nombre_contrato_sisgen(doc)
        fecha_m = self._fecha_minuta_sisgen(doc, pat_row, mp_rows)

        parts = ["\t<DocumentoNotarial>\n"]
        parts.append(self._xml_seccion_documento(doc))
        parts.append("\t<Maestros>\n\t</Maestros>\n")
        parts.append("\t<Operaciones>\n")
        parts.append(f'\t\t<Operacion id="{doc.get("codactos", "")}">\n')
        parts.append(f'\t\t\t<CodActoJuridico>{doc.get("cod_ancert", "")}</CodActoJuridico>\n')
        parts.append("\t\t\t<Operantes>\n")
        parts.append("\t\t\t\t<Objetos>\n\t\t\t\t</Objetos>\n")
        parts.append("\t\t\t\t<Intervenciones>\n\t\t\t\t</Intervenciones>\n")
        parts.append("\t\t\t\t<NoIntervinientes>\n\t\t\t\t</NoIntervinientes>\n")
        parts.append("\t\t\t</Operantes>\n")
        parts.append("\t\t\t<CuantiaOperacion>\n")
        parts.append(f"\t\t\t\t<Cuantia>{total_monto:.2f}</Cuantia>\n")
        parts.append(f"\t\t\t\t<TipoMoneda>{tipo_moneda_doc}</TipoMoneda>\n")
        parts.append("\t\t\t</CuantiaOperacion>\n")
        parts.append(
            self._medios_pagos_xml_for_doc(
                doc, pat_row, mp_rows, tipo_moneda_doc, total_monto
            )
        )
        parts.append(f"\t\t\t<NombreContrato>{nombre_c}</NombreContrato>\n")
        parts.append(f"\t\t\t<FechaMinuta>{fecha_m}</FechaMinuta>\n")
        parts.append("\t\t</Operacion>\n")
        parts.append("\t</Operaciones>\n")
        parts.append("\t</DocumentoNotarial>\n")
        return "".join(parts)

    def generate_document_xml(self, documents: List[Dict]) -> Tuple[Optional[str], List[str]]:
        """
        Generate XML for SISGEN service.

        Returns (xml, issues). ``xml`` is None when nothing was emitted (solo shell
        ``DocumentosNotariales`` sin ``DocumentoNotarial``): SISGEN suele responder
        solo ``OK`` sin ``GUARDADO`` porque no hubo documentos en el CDATA.

        ``issues`` lista razones por cada documento omitido (validación / armado) y,
        si hay XML parcial, también incluye los que se saltaron en el mismo batch.
        """
        issues: List[str] = []
        try:
            # Validate documents have required data
            if not documents:
                self.logger.error("No documents provided")
                return None, ["No documents provided"]

            docs_emitted = 0

            # Start XML document
            xml = '<?xml version="1.0" ?>\n'
            xml += '<DocumentosNotariales xmlns="http://sisgen.notarios.org.pe/SISGEN/XML" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://sisgen.notarios.org.pe/SISGEN/XML C:\\SISGEN\\SISGEN_V2_RO\\documentos_notariales.xsd">\n'
            
            # Add GeneradorDatos section
            xml += '\t<GeneradorDatos>\n'
            xml += f'\t\t<NomProveedor>{APP_CONSTANTS["PROVIDER_NAME"]}</NomProveedor>\n'
            xml += f'\t\t<NomAplicacion>{APP_CONSTANTS["APP_NAME"]}</NomAplicacion>\n'
            xml += f'\t\t<VersionAplicacion>{APP_CONSTANTS["APP_VERSION"]}</VersionAplicacion>\n'
            xml += '\t</GeneradorDatos>\n'

            # Process each document
            for doc in documents:
                kdx = doc.get("kardex", "?")
                if not self._validate_document(doc):
                    msg = f"kardex {kdx}: datos incompletos (validación previa)"
                    issues.append(msg)
                    continue
                asm_errs = self._collect_assembly_errors(doc)
                if asm_errs:
                    for err in asm_errs:
                        self.logger.error(
                            "Armado XML omitido kardex=%s: %s",
                            doc.get("kardex"),
                            err,
                        )
                    issues.append(
                        f"kardex {kdx}: " + "; ".join(asm_errs)
                    )
                    continue
                if str(doc.get("cod_ancert") or "").strip() == "0919":
                    xml += self._documento_notarial_xml_minimo_0919(doc)
                    docs_emitted += 1
                    continue

                bienes = self._load_bienes_for_doc(doc)
                
                xml += '\t<DocumentoNotarial>\n'
                xml += self._xml_seccion_documento(doc)

                # Add Maestros section
                xml += '\t<Maestros>\n'
                
                # Process participants
                natural_persons = []
                juridical_persons = []
                for participant in doc.get('participants', []):
                    if participant.get('tipper') == 'J':
                        juridical_persons.append(participant)
                    elif participant.get('tipper') == 'N':
                        natural_persons.append(participant)

                if natural_persons:
                    xml += '\t\t<PersonasNaturales>\n'
                    for person in natural_persons:
                        xml += f'\t\t\t<PersonaNatural id="{person.get("idcliente", "")}">\n'
                        xml += '\t\t\t<DocsIdentificativos>\n'
                        xml += '\t\t\t\t<DocIdentificativo>\n'
                        tdoc_nat = self._tipo_doc_natural_para_xml(person, doc)
                        if tdoc_nat:
                            xml += f'\t\t\t\t\t<TipoDocIdentidad>{tdoc_nat}</TipoDocIdentidad>\n'
                        if person.get("numdoc"):
                            xml += f'\t\t\t\t\t<NumDocIdentificativo>{person.get("numdoc", "")}</NumDocIdentificativo>\n'
                        xml += '\t\t\t\t</DocIdentificativo>\n'
                        xml += '\t\t\t</DocsIdentificativos>\n'
                        
                        nombre_natural = self._persona_natural_nombre(person)
                        if nombre_natural:
                            xml += f'\t\t\t\t<Nombre>{self._xml_pcdata(nombre_natural)}</Nombre>\n'
                        if person.get("apepat"):
                            xml += f'\t\t\t\t<PrimerApellido>{person.get("apepat", "")}</PrimerApellido>\n'
                        if person.get("apemat"):
                            xml += f'\t\t\t\t<SegundoApellido>{person.get("apemat", "")}</SegundoApellido>\n'
                        sexo_val = person.get("sexo") or person.get("gen")
                        if sexo_val:
                            xml += f'\t\t\t\t<Genero>{"V" if sexo_val == "M" else "M"}</Genero>\n'
                        id_est = person.get("idestcivil")
                        if id_est not in (None, "", 0):
                            xml += f'\t\t\t\t<EstadoCivil>{id_est}</EstadoCivil>\n'
                        cony_id = (person.get("conyuge") or "").strip()
                        uif_role = (person.get("uif") or "").strip().upper()
                        if (
                            str(id_est) == "2"
                            and uif_role != "R"
                            and cony_id
                            and cony_id != "0"
                        ):
                            xml += f'\t\t\t\t<Conyuge>{escape(cony_id)}</Conyuge>\n'
                        nac_cod = self._pais_nacionalidad_codigo(person)
                        if nac_cod:
                            xml += f'\t\t\t\t<PaisNacionalidad>{escape(nac_cod)}</PaisNacionalidad>\n'
                        if person.get("cumpclie"):
                            xml += f'\t\t\t\t<FechaNacimiento>{self._format_date(person.get("cumpclie", ""))}</FechaNacimiento>\n'
                        prof_cod = self._profesion_cod_natural(person)
                        if prof_cod:
                            xml += f'\t\t\t\t<Profesion>{prof_cod}</Profesion>\n'
                        if prof_cod == "999":
                            det_prof = self._legacy_text_short(person.get("detaprofesion"), 50)
                            if det_prof:
                                xml += f'\t\t\t\t<OtraProfesion>{self._xml_pcdata(det_prof)}</OtraProfesion>\n'
                            else:
                                xml += '\t\t\t\t<OtraProfesion>OTROS</OtraProfesion>\n'
                        cargo_cod = self._cargo_cod_natural(person)
                        if cargo_cod:
                            xml += f'\t\t\t\t<Cargo>{escape(cargo_cod)}</Cargo>\n'
                        if cargo_cod == "999":
                            det_cargo = self._legacy_text_short(person.get("profocupa"), 50)
                            if det_cargo:
                                xml += f'\t\t\t\t<OtroCargo>{self._xml_pcdata(det_cargo)}</OtroCargo>\n'
                            else:
                                xml += '\t\t\t\t<OtroCargo>OTROS</OtroCargo>\n'
                        email_nat = (person.get("email") or "").strip()
                        if email_nat and self._email_ok(email_nat):
                            xml += f'\t\t\t\t<Correo>{escape(email_nat)}</Correo>\n'
                        telcel = (person.get("telcel") or "").strip()
                        if telcel and self._telefono_natural_legacy_ok(telcel):
                            tel_s = telcel[: self.JUR_TELEFONO_MAX]
                            xml += f'\t\t\t\t<Telefono>{escape(tel_s)}</Telefono>\n'
                        
                        # Add address if all required fields are present
                        if person.get("idubigeo") and person.get("direccion"):
                            xml += '\t\t\t\t<Direccion>\n'
                            xml += '\t\t\t\t\t<ResidePeru>1</ResidePeru>\n'
                            xml += '\t\t\t\t\t<PaisResidencia>PE</PaisResidencia>\n'
                            xml += '\t\t\t\t<DireccionNacional>\n'
                            ubigeo = self._solo_digitos(person.get("idubigeo"))
                            if len(ubigeo) == 6:
                                xml += f'\t\t\t\t\t<CodDepartamento>{ubigeo[:2]}</CodDepartamento>\n'
                                xml += f'\t\t\t\t\t<CodProvincia>{ubigeo[2:4]}</CodProvincia>\n'
                                xml += f'\t\t\t\t\t<CodDistrito>{ubigeo[4:6]}</CodDistrito>\n'
                            xml += f'\t\t\t\t\t<RestoDireccion>{person.get("direccion", "")}</RestoDireccion>\n'
                            xml += '\t\t\t\t</DireccionNacional>\n'
                            xml += '\t\t\t\t</Direccion>\n'
                        xml += '\t\t\t</PersonaNatural>\n'
                    xml += '\t\t</PersonasNaturales>\n'

                if juridical_persons:
                    xml += '\t\t<PersonasJuridicas>\n'
                    for person in juridical_persons:
                        xml += f'\t\t\t<PersonaJuridica id="{person.get("idcliente", "")}">\n'
                        xml += '\t\t\t<DocsIdentificativos>\n'
                        xml += '\t\t\t\t<DocIdentificativo>\n'
                        tdoc_jur = self._tipo_doc_juridico_para_xml(person, doc)
                        if tdoc_jur:
                            xml += f'\t\t\t\t\t<TipoDocIdentidad>{tdoc_jur}</TipoDocIdentidad>\n'
                        if person.get("numdoc"):
                            xml += f'\t\t\t\t\t<NumDocIdentificativo>{person.get("numdoc", "")}</NumDocIdentificativo>\n'
                        xml += '\t\t\t\t</DocIdentificativo>\n'
                        xml += '\t\t\t</DocsIdentificativos>\n'
                        
                        xml += '\t\t\t\t<RegistroFacultades>\n'
                        # PHP: sedereg vacío o "00" no emite sede
                        sedereg_raw = person.get("sedereg", person.get("idsedereg"))
                        sedereg_s = (
                            str(sedereg_raw).strip()
                            if sedereg_raw is not None
                            else ""
                        )
                        if sedereg_s and sedereg_s != "00":
                            xml += f'\t\t\t\t\t<SedeRegistral>{escape(sedereg_s)}</SedeRegistral>\n'
                        num_part_jur = person.get("numpartidareg") or person.get(
                            "numpartida"
                        )
                        if num_part_jur:
                            partida = str(num_part_jur).strip()[: self.JUR_PARTIDA_MAX]
                            xml += f'\t\t\t\t\t<PartidaRegistral>{escape(partida)}</PartidaRegistral>\n'
                        xml += '\t\t\t\t</RegistroFacultades>\n'

                        if person.get("razonsocial"):
                            xml += f'\t\t\t\t<RazonSocial>{self._xml_pcdata_trunc(person.get("razonsocial"), self.JUR_RAZON_SOCIAL_MAX)}</RazonSocial>\n'
                        # Sector económico: ciuu explícito, o actmunicipal = coddivi (A-Q) / dígitos SUNAT
                        sector_eco = self._persona_juridica_sector_economico(person)
                        if sector_eco:
                            xml += f'\t\t\t\t<SectorEconomico>{escape(sector_eco)}</SectorEconomico>\n'
                        else:
                            self.logger.warning(
                                "Persona jurídica id=%s (%s): sin valor para "
                                "<SectorEconomico>; cargue ciuu o actmunicipal como "
                                "coddivi (una letra, tabla ciiu) o código numérico SUNAT.",
                                person.get("idcliente"),
                                (person.get("razonsocial") or "")[:60],
                            )
                        otra_actividad = self._persona_juridica_otra_actividad_text(person)
                        if otra_actividad:
                            xml += f'\t\t\t\t<OtraActividad>{self._xml_pcdata_trunc(otra_actividad, self.JUR_OTRA_ACTIVIDAD_MAX)}</OtraActividad>\n'
                        correo_raw = (person.get("correoemp") or person.get("mailempresa") or "").strip()
                        if correo_raw and self._email_ok(correo_raw):
                            xml += f'\t\t\t\t<Correo>{escape(correo_raw)}</Correo>\n'
                        telempresa = (person.get("telempresa") or "").strip()
                        if telempresa:
                            tel_s = telempresa[: self.JUR_TELEFONO_MAX]
                            xml += f'\t\t\t\t<Telefono>{escape(tel_s)}</Telefono>\n'

                        # Dirección fiscal — PHP omite bloque si idubigeo es 999999; sin ResidePeru en jurídica
                        ubigeo_key = (person.get("idubigeo") or "").strip()
                        if (
                            ubigeo_key
                            and ubigeo_key != "999999"
                            and person.get("domfiscal")
                        ):
                            dep_u, prov_u, dist_u = self._persona_juridica_ubigeo_parts(
                                person
                            )
                            xml += '\t\t\t\t<Direccion>\n'
                            xml += '\t\t\t\t\t<PaisResidencia>PE</PaisResidencia>\n'
                            xml += '\t\t\t\t<DireccionNacional>\n'
                            if dep_u:
                                xml += f'\t\t\t\t\t<CodDepartamento>{escape(dep_u)}</CodDepartamento>\n'
                            if prov_u:
                                xml += f'\t\t\t\t\t<CodProvincia>{escape(prov_u)}</CodProvincia>\n'
                            if dist_u:
                                xml += f'\t\t\t\t\t<CodDistrito>{escape(dist_u)}</CodDistrito>\n'
                            xml += f'\t\t\t\t\t<RestoDireccion>{self._xml_pcdata_trunc(person.get("domfiscal"), self.JUR_RESTO_DIRECCION_MAX)}</RestoDireccion>\n'
                            xml += '\t\t\t\t</DireccionNacional>\n'
                            xml += '\t\t\t\t</Direccion>\n'
                        xml += '\t\t\t</PersonaJuridica>\n'
                    xml += '\t\t</PersonasJuridicas>\n'

                if bienes["predios"]:
                    xml += '\t\t<PrediosUrbanos>\n'
                    for predio in bienes["predios"]:
                        xml += f'\t\t\t<PredioUrbano id="{predio.get("detbien", "")}">\n'
                        xml += '\t\t\t\t<TipoConstruccion>6</TipoConstruccion>\n'
                        xml += '\t\t\t\t<IdentificacionPredio>\n'
                        if predio.get("idsedereg"):
                            xml += f'\t\t\t\t\t<SedeRegistral>{escape(str(predio.get("idsedereg", "")).strip())}</SedeRegistral>\n'
                        if predio.get("pregistral"):
                            xml += f'\t\t\t\t\t<PartidaRegistral>{escape(str(predio.get("pregistral", "")).strip())}</PartidaRegistral>\n'
                        xml += '\t\t\t\t</IdentificacionPredio>\n'
                        if predio.get("codpto"):
                            xml += '\t\t\t\t<DireccionUrbana>\n'
                            pcpto = self._solo_digitos(predio.get("codpto"))
                            pprov = self._solo_digitos(predio.get("codprov"))
                            pdis = self._solo_digitos(predio.get("coddis"))
                            if len(pdis) == 6:
                                pcpto, pprov, pdis = pdis[:2], pdis[2:4], pdis[4:6]
                            elif len(pcpto) == 6:
                                pcpto, pprov, pdis = pcpto[:2], pcpto[2:4], pcpto[4:6]

                            cod_dep_p = self._clip_cod_geo_dos(pcpto)
                            cod_prv_p = self._clip_cod_geo_dos(pprov)
                            cod_dis_p = self._clip_cod_geo_dos(pdis)
                            xml += f'\t\t\t\t\t<CodDepartamento>{escape(cod_dep_p)}</CodDepartamento>\n'
                            xml += f'\t\t\t\t\t<CodProvincia>{escape(cod_prv_p)}</CodProvincia>\n'
                            xml += f'\t\t\t\t\t<CodDistrito>{escape(cod_dis_p)}</CodDistrito>\n'
                            xml += '\t\t\t\t</DireccionUrbana>\n'
                        xml += '\t\t\t</PredioUrbano>\n'
                    xml += '\t\t</PrediosUrbanos>\n'

                vehiculos_all = bienes["vehiculos_bienes"] + bienes["vehiculos_detalle"]
                if vehiculos_all:
                    xml += '\t\t<Vehiculos>\n'
                    for veh in bienes["vehiculos_bienes"]:
                        xml += f'\t\t\t<Vehiculo id="{veh.get("detbien", "")}">\n'
                        xml += '\t\t\t\t<TipoVehiculo>4</TipoVehiculo>\n'
                        xml += '\t\t\t\t<TipoIdentificacionVehiculo>1</TipoIdentificacionVehiculo>\n'
                        if veh.get("npsm"):
                            xml += f'\t\t\t\t<NumPlaca>{escape(str(veh.get("npsm", "")).strip())}</NumPlaca>\n'
                        if veh.get("idsedereg"):
                            xml += f'\t\t\t\t<SedeRegistral>{escape(str(veh.get("idsedereg", "")).strip())}</SedeRegistral>\n'
                        if veh.get("pregistral"):
                            xml += f'\t\t\t\t<PartidaRegistral>{escape(str(veh.get("pregistral", "")).strip())}</PartidaRegistral>\n'
                        xml += '\t\t\t</Vehiculo>\n'

                    for veh in bienes["vehiculos_detalle"]:
                        xml += f'\t\t\t<Vehiculo id="{veh.get("detveh", "")}">\n'
                        xml += '\t\t\t\t<TipoVehiculo>4</TipoVehiculo>\n'
                        tipo_ident = "1" if (veh.get("idplaca") or "").strip() == "P" else "2"
                        xml += f'\t\t\t\t<TipoIdentificacionVehiculo>{tipo_ident}</TipoIdentificacionVehiculo>\n'
                        if veh.get("numplaca"):
                            xml += f'\t\t\t\t<NumPlaca>{escape(str(veh.get("numplaca", "")).strip())}</NumPlaca>\n'
                        for tag, key in (
                            ("Clase", "clase"),
                            ("Marca", "marca"),
                            ("AnoFabricacion", "anofab"),
                            ("Modelo", "modelo"),
                            ("Combustible", "combustible"),
                            ("Carroceria", "carroceria"),
                            ("Color", "color"),
                            ("Motor", "motor"),
                            ("NumCilindros", "numcil"),
                            ("NumSerie", "numserie"),
                            ("NumRueda", "numrueda"),
                        ):
                            if veh.get(key):
                                xml += f'\t\t\t\t<{tag}>{escape(str(veh.get(key, "")).strip())}</{tag}>\n'
                        if veh.get("idsedereg"):
                            xml += f'\t\t\t\t<SedeRegistral>{escape(str(veh.get("idsedereg", "")).strip())}</SedeRegistral>\n'
                        if veh.get("pregistral"):
                            xml += f'\t\t\t\t<PartidaRegistral>{escape(str(veh.get("pregistral", "")).strip())}</PartidaRegistral>\n'
                        xml += '\t\t\t</Vehiculo>\n'
                    xml += '\t\t</Vehiculos>\n'

                if bienes["otros"]:
                    xml += '\t\t<OtrosObjetos>\n'
                    for otro in bienes["otros"]:
                        xml += f'\t\t\t<OtroObjeto id="{otro.get("detbien", "")}">\n'
                        if otro.get("oespecific"):
                            xml += f'\t\t\t\t<Descripcion>{self._xml_pcdata(otro.get("oespecific"))}</Descripcion>\n'
                        xml += '\t\t\t\t<ClaseObjeto>7</ClaseObjeto>\n'
                        xml += '\t\t\t</OtroObjeto>\n'
                    xml += '\t\t</OtrosObjetos>\n'

                xml += '\t</Maestros>\n'

                pat_row = self._resolve_patrimonial_for_doc(doc)
                tipo_moneda_doc = self._sisgen_codmon_from_idmon(
                    pat_row.get("idmon") if pat_row else None
                )
                mp_rows = self._medios_pago_filas_enriquecidas(doc.get("kardex"))
                idc_for_renta = [
                    str(p.get("idcontratante")).strip()
                    for p in (doc.get("participants") or [])
                    if p.get("idcontratante") is not None and str(p.get("idcontratante")).strip()
                ]
                renta_map = self._renta_map_for_kardex(doc.get("kardex"), idc_for_renta)
                requires_renta_impuesto = self._doc_requires_renta_impuesto_xml(doc)

                # Add Operaciones section
                xml += '\t<Operaciones>\n'
                xml += f'\t\t<Operacion id="{doc.get("codactos", "")}">\n'
                xml += f'\t\t\t<CodActoJuridico>{doc.get("cod_ancert", "")}</CodActoJuridico>\n'
                xml += '\t\t<Operantes>\n'
                xml += '\t\t\t<Objetos>\n'
                for predio in bienes["predios"]:
                    xml += '\t\t\t\t<Objeto>\n'
                    xml += f'\t\t\t\t\t<IdMaestro>{predio.get("detbien", "")}</IdMaestro>\n'
                    if predio.get("fechaconst"):
                        xml += '\t\t\t\t\t<DetalleObjeto>\n'
                        xml += f'\t\t\t\t\t\t<FechaAdquisicion>{self._format_date(predio.get("fechaconst", ""))}</FechaAdquisicion>\n'
                        xml += '\t\t\t\t\t</DetalleObjeto>\n'
                    xml += '\t\t\t\t</Objeto>\n'
                for veh in bienes["vehiculos_bienes"]:
                    xml += '\t\t\t\t<Objeto>\n'
                    xml += f'\t\t\t\t\t<IdMaestro>{veh.get("detbien", "")}</IdMaestro>\n'
                    xml += '\t\t\t\t</Objeto>\n'
                for otro in bienes["otros"]:
                    xml += '\t\t\t\t<Objeto>\n'
                    xml += f'\t\t\t\t\t<IdMaestro>{otro.get("detbien", "")}</IdMaestro>\n'
                    xml += '\t\t\t\t</Objeto>\n'
                for veh in bienes["vehiculos_detalle"]:
                    xml += '\t\t\t\t<Objeto>\n'
                    xml += f'\t\t\t\t\t<IdMaestro>{veh.get("detveh", "")}</IdMaestro>\n'
                    xml += '\t\t\t\t</Objeto>\n'
                xml += '\t\t\t</Objetos>\n'
                xml += '\t\t\t<Intervenciones>\n'

                emitidos_sujeto_id_maestro: Set[str] = set()
                
                # Group participants by role and condition
                participants_by_role = {}
                for participant in doc.get('participants', []):
                    role = participant.get('uif', 'O')
                    condition = participant.get('idcondicion', '')
                    key = f"{role}_{condition}"
                    if key not in participants_by_role:
                        participants_by_role[key] = []
                    participants_by_role[key].append(participant)
                
                # Process each role group
                for key, participants in participants_by_role.items():
                    if not participants:
                        continue
                    
                    role = key.split('_')[0]
                    tipo_int, desc_int = self._get_tipo_intervencion_desc(
                        role=role,
                        acto_juridico=doc.get('cod_ancert'),
                        participant_data=participants[0]  # Pass the first participant as data
                    )
                    
                    xml += '\t\t\t\t<Intervencion>\n'
                    xml += f'\t\t\t\t\t<TipoIntervencion>{tipo_int}</TipoIntervencion>\n'
                    xml += f'\t\t\t\t\t<DescripcionIntervencion>{desc_int}</DescripcionIntervencion>\n'
                    xml += f'\t\t\t\t\t<RolRepresentante>{role}</RolRepresentante>\n'
                    xml += '\t\t\t\t\t<Sujetos>\n'
                    
                    for participant in participants:
                        xml += '\t\t\t\t\t\t<Sujeto>\n'
                        xml += f'\t\t\t\t\t\t\t<IdMaestro>{participant.get("idcliente", "")}</IdMaestro>\n'
                        _mid_s = str(participant.get("idcliente") or "").strip()
                        if _mid_s:
                            emitidos_sujeto_id_maestro.add(_mid_s)
                        
                        # Add OrigenFondos
                        if participant.get("ofondo"):
                            cuantia_o = self._cuantia_origen_participant(
                                participant, doc, pat_row
                            )
                            xml += '\t\t\t\t\t\t\t<OrigenFondos>\n'
                            xml += '\t\t\t\t\t\t\t\t<OrigenFondo>\n'
                            origen_u = self._legacy_text_short(
                                participant.get("ofondo"), self.ORIGEN_FONDOS_MAX
                            ).upper()
                            xml += (
                                "\t\t\t\t\t\t\t\t\t"
                                f"<Origen>{escape(origen_u)}</Origen>\n"
                            )
                            xml += f'\t\t\t\t\t\t\t\t\t<CuantiaOrigen>{cuantia_o:.2f}</CuantiaOrigen>\n'
                            xml += f'\t\t\t\t\t\t\t\t\t<TipoMonedaPago>{tipo_moneda_doc}</TipoMonedaPago>\n'
                            xml += '\t\t\t\t\t\t\t\t</OrigenFondo>\n'
                            xml += '\t\t\t\t\t\t\t</OrigenFondos>\n'
                        
                        xml += '\t\t\t\t\t\t\t<Derecho>\n'
                        if participant.get("porcentaje"):
                            xml += f'\t\t\t\t\t\t\t\t<PorcentajeDerecho>{self._safe_float(participant.get("porcentaje", "100")):.2f}</PorcentajeDerecho>\n'
                        xml += '\t\t\t\t\t\t\t</Derecho>\n'
                        
                        # Renta / impuestos (tabla renta.pregu1..3; PHP por kardex+idcontratante)
                        if role == 'O':
                            r3, ce, iz = self._renta_impuesto_triplet_xml(
                                participant,
                                renta_map,
                                use_db=requires_renta_impuesto,
                            )
                            xml += f'\t\t\t\t\t\t\t<Renta3Cat>{r3}</Renta3Cat>\n'
                            xml += f'\t\t\t\t\t\t\t<CasaEnajenante>{ce}</CasaEnajenante>\n'
                            xml += f'\t\t\t\t\t\t\t<ImpuestoCero>{iz}</ImpuestoCero>\n'
                        elif role == 'B' and requires_renta_impuesto:
                            r3, ce, iz = self._renta_impuesto_triplet_xml(
                                participant, renta_map, use_db=True
                            )
                            xml += f'\t\t\t\t\t\t\t<Renta3Cat>{r3}</Renta3Cat>\n'
                            xml += f'\t\t\t\t\t\t\t<CasaEnajenante>{ce}</CasaEnajenante>\n'
                            xml += f'\t\t\t\t\t\t\t<ImpuestoCero>{iz}</ImpuestoCero>\n'
                        
                        xml += self._representantes_bajo_sujeto_xml(
                            participant.get("idcontratante"),
                            doc.get("participants") or [],
                        )
                        
                        xml += self._fecha_firma_element_xml(
                            participant, "\t\t\t\t\t\t\t"
                        )
                        xml += '\t\t\t\t\t\t</Sujeto>\n'
                    xml += '\t\t\t\t\t</Sujetos>\n'
                    xml += '\t\t\t\t</Intervencion>\n'

                xml += '\t\t\t</Intervenciones>\n'
                
                # NoIntervinientes: marcadores PHP (repre/firma/visita 'N') + cónyuge casado
                ni_ids = self._coleccion_no_interviniente_ids(
                    doc.get("participants") or [],
                    emitidos_sujeto_id_maestro,
                )
                xml += '\t\t\t<NoIntervinientes>\n'
                for nid in ni_ids:
                    xml += '\t\t\t\t<NoInterviniente>\n'
                    xml += f'\t\t\t\t\t<IdMaestro>{nid}</IdMaestro>\n'
                    xml += '\t\t\t\t</NoInterviniente>\n'
                xml += '\t\t\t</NoIntervinientes>\n'
                xml += '\t\t</Operantes>\n'
                
                # Add CuantiaOperacion section
                xml += '\t\t<CuantiaOperacion>\n'
                participants_list = doc.get('participants', [])
                total_monto = self._cuantia_operacion_total(doc, participants_list)
                xml += f'\t\t\t<Cuantia>{total_monto:.2f}</Cuantia>\n'
                xml += f'\t\t\t<TipoMoneda>{tipo_moneda_doc}</TipoMoneda>\n'
                xml += '\t\t</CuantiaOperacion>\n'
                
                xml += self._medios_pagos_xml_for_doc(
                    doc, pat_row, mp_rows, tipo_moneda_doc, total_monto
                )

                nombre_contrato_xml = self._nombre_contrato_sisgen(doc)
                fecha_minuta_xml = self._fecha_minuta_sisgen(doc, pat_row, mp_rows)
                xml += f"\t\t\t<NombreContrato>{nombre_contrato_xml}</NombreContrato>\n"
                xml += f"\t\t\t<FechaMinuta>{fecha_minuta_xml}</FechaMinuta>\n"
                
                xml += '\t\t</Operacion>\n'
                xml += '\t</Operaciones>\n'
                xml += '\t</DocumentoNotarial>\n'
                docs_emitted += 1

            if docs_emitted == 0:
                self.logger.error(
                    "Ningún DocumentoNotarial emitido (%s documentos en batch); "
                    "no enviar a SISGEN (respuesta sería OK sin GUARDADO).",
                    len(documents),
                )
                if not issues:
                    issues.append(
                        "Ningún documento incluido en el XML (revisar logs de validación)."
                    )
                return None, issues

            xml += '</DocumentosNotariales>'
            
            # Clean XML content like PHP
            xml = (xml
                .replace("&", "&amp;")
                .replace("Ã'", "Ñ")
                .replace("Ï¿½", "Ñ")
                .replace("Ï¿Ï¿½", "Ñ"))
            
            # Write XML to file like PHP
            with open('textparaenviar-uno.xml', 'w') as f:
                f.write(xml)
            
            logger.debug("Generated XML content")
            return xml, issues

        except Exception as e:
            logger.error(f"Error generating XML: {str(e)}")
            return None, issues + [str(e)]
    
    def _validate_document(self, doc: Dict) -> bool:
        """Validate document has all required data"""
        # Validate basic document data
        required_fields = ['kardex', 'numescritura', 'idtipkar', 'fechaescritura']
        if not all(doc.get(field) for field in required_fields):
            self.logger.warning(f"Document missing required fields: {doc.get('kardex', 'Unknown')}")
            return False
            
        # Validate notary data
        notary_data = doc.get('notary_data', {})
        required_notary_fields = [
            'codnotario', 'codoficial', 'coduif', 
            'nombre_notario', 'direccion', 'distrito'
        ]
        if not all(notary_data.get(field) for field in required_notary_fields):
            self.logger.warning(f"Document missing required notary data: {doc.get('kardex', 'Unknown')}")
            return False
            
        return True