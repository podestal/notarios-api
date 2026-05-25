"""
RoClass generateData participant field validations (items 10–38, 21–22 extras).
"""

import logging
from datetime import date, datetime
from typing import Dict, List, Optional, Set, Tuple

from notaria.models import (
    Cargoprofe,
    Cliente2,
    Contratantes,
    Contratantesxacto,
    Nacionalidades,
    Profesiones,
    Tipodocumento,
    Tipoestacivil,
    Ubigeo,
)
from uif.models import Ciiu
from uif.services.complementary import (
    escritura_before_range,
    firma_in_report_range,
    group_medios_for_act,
    has_medios_for_act,
)
from uif.services.conyuge_fields import resolve_conyuge_fields
from uif.services.constants import (
    ACTS_CONSTITUCION_RUC_CORRECTABLE,
    ACTS_EXEMPT_BENEFICIARIO_AMOUNT,
    ACTS_EXEMPT_OTORGANTE_AMOUNT,
    DOCUMENT_TYPES_PERU,
    PLANE_PARTICIPANT_ROLES,
    ROLE_BENEFICIARIO,
    ROLE_OTORGANTE,
    ROLE_REPRESENTANTE,
)
from uif.services.errors import (
    CODE_ELEMENT_MISSING_PAYMENT_ROWS,
    ROW_TYPE_PARTICIPANT,
    build_ro_error,
)
from uif.services.ro_validation_rules import (
    FIELD_APELLIDO_MATERNO,
    FIELD_APELLIDO_RAZON,
    FIELD_CARGO,
    FIELD_CIIU,
    FIELD_CONDICION_RESIDENCIA,
    FIELD_DEPARTAMENTO,
    FIELD_DIRECCION,
    FIELD_DISTRITO,
    FIELD_ESTADO_CIVIL,
    FIELD_FECHA_FIRMA,
    FIELD_PARTICIPACION_CONYUGE,
    FIELD_APELLIDO_PATERNO_CONYUGE,
    FIELD_APELLIDO_MATERNO_CONYUGE,
    FIELD_NOMBRES_CONYUGE,
    FIELD_NACIONALIDAD,
    FIELD_NOMBRES,
    FIELD_NUMERO_DOCUMENTO,
    FIELD_NUMERO_RUC,
    FIELD_OBJETO_SOCIAL,
    FIELD_PARTIDA_REGISTRAL,
    FIELD_PERSONA_AFAVOR,
    FIELD_PERSONA_OPERACION,
    FIELD_PERSONA_QUE_REPRESENTA,
    FIELD_PROFESION,
    FIELD_PROVINCIA,
    FIELD_REPRESENTANTE,
    FIELD_TIPO_DOCUMENTO,
    FIELD_TIPO_PERSONA,
    FIELD_TIPO_REPRESENTACION,
    FIELD_ZONA_REGISTRAL,
    RoValidationRulesRepository,
    validation_code,
)

logger = logging.getLogger(__name__)


def _participant_name(cliente: Optional[Cliente2], contratante_id: str) -> str:
    if not cliente:
        return f"Contratante {contratante_id}"
    if (cliente.tipper or "N").upper() == "J":
        return (cliente.razonsocial or "").strip() or f"Contratante {contratante_id}"
    parts = [cliente.apepat, cliente.apemat, cliente.prinom, cliente.segnom]
    name = " ".join(p for p in parts if p).strip()
    return name or f"Contratante {contratante_id}"


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
    return ""


class ParticipantFieldsValidator:
    """Field-level RO errors for contratantes O/B/R (tipo envío I)."""

    def __init__(self, rules: Optional[RoValidationRulesRepository] = None):
        self.rules = rules or RoValidationRulesRepository()
        self.rules.load()
        self._tipodoc_map: Optional[Dict[int, str]] = None
        self._prof_map: Optional[Dict[int, bool]] = None
        self._cargo_map: Optional[Dict[int, bool]] = None
        self._civil_map: Optional[Dict[int, bool]] = None
        self._nacion_map: Optional[Dict[str, str]] = None
        self._ciiu_keys: Optional[Set[str]] = None
        self._ubigeo_cache: Dict[str, Optional[Ubigeo]] = {}

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
    def prof_map(self) -> Dict[int, bool]:
        if self._prof_map is None:
            self._prof_map = {p.idprofesion: True for p in Profesiones.objects.all()}
        return self._prof_map

    @property
    def cargo_map(self) -> Dict[int, bool]:
        if self._cargo_map is None:
            self._cargo_map = {c.idcargoprofe: True for c in Cargoprofe.objects.all()}
        return self._cargo_map

    @property
    def civil_map(self) -> Dict[int, bool]:
        if self._civil_map is None:
            self._civil_map = {t.idestcivil: True for t in Tipoestacivil.objects.all()}
        return self._civil_map

    @property
    def nacion_map(self) -> Dict[str, str]:
        if self._nacion_map is None:
            self._nacion_map = {}
            for n in Nacionalidades.objects.all():
                self._nacion_map[str(n.idnacionalidad)] = (n.codnacion or "")[:2]
        return self._nacion_map

    @property
    def ciiu_keys(self) -> Set[str]:
        if self._ciiu_keys is None:
            self._ciiu_keys = {c.coddivi for c in Ciiu.objects.all()}
        return self._ciiu_keys

    def validate(
        self,
        *,
        staged,
        act_description: str,
        contratantes_map: Dict,
        clientes_map: Dict,
        contratantesxacto_map: Dict,
        detalle_medio_pago_rows: Optional[List] = None,
        range_start: Optional[date] = None,
        range_end: Optional[date] = None,
    ) -> List[dict]:
        tipo = str(getattr(staged, "tipo", "I"))
        if tipo not in ("I", "C"):
            return []

        kardex = staged.kardex
        cod_acto = staged.cod_acto
        uif_code = (staged.uif_code or "").strip()
        id_kardex = staged.id_kardex
        detalle_rows = detalle_medio_pago_rows or []

        if tipo == "C":
            if range_start is None or range_end is None:
                return []
            if not escritura_before_range(kardex, range_start):
                return [
                    build_ro_error(
                        id_kardex=id_kardex,
                        kardex=kardex,
                        act=act_description,
                        codacto=cod_acto,
                        uif_code=uif_code,
                        error_type="complementary_escritura_in_range",
                        error_description=(
                            "Información complementaria: la escritura debe ser anterior "
                            "al periodo del reporte"
                        ),
                        field_number=6,
                        row_type=ROW_TYPE_PARTICIPANT,
                        is_correctable=False,
                    )
                ]
            if not has_medios_for_act(kardex, cod_acto, detalle_rows):
                return []
            _, tipo_acto_medio = group_medios_for_act(kardex, cod_acto, detalle_rows)
            cod_acto_spouse = str(tipo_acto_medio or cod_acto).strip()
            participants = self._collect_participants_complementary(
                kardex,
                tipo_acto_medio,
                range_start,
                range_end,
                contratantes_map,
                clientes_map,
                contratantesxacto_map,
            )
            if not participants:
                return []
        else:
            participants = self._collect_participants(
                kardex, cod_acto, contratantes_map, clientes_map, contratantesxacto_map
            )
            if not participants:
                return [
                    build_ro_error(
                        id_kardex=id_kardex,
                        kardex=kardex,
                        act=act_description,
                        codacto=cod_acto,
                        uif_code=uif_code,
                        error_type="missing_participants",
                        error_description="El kardex no tiene fila de Contratantes",
                        field_number=1,
                        code_element=CODE_ELEMENT_MISSING_PAYMENT_ROWS,
                        row_type=ROW_TYPE_PARTICIPANT,
                        is_correctable=False,
                    )
                ]

        errors: List[dict] = []
        has_o = False
        has_b = False
        include_structural_roles = tipo == "I"
        cod_acto_spouse = str(cod_acto or "").strip()

        for item in participants:
            role = item["role"]
            if role == ROLE_OTORGANTE:
                has_o = True
            elif role == ROLE_BENEFICIARIO:
                has_b = True
            errors.extend(
                self._validate_one(
                    item=item,
                    staged=staged,
                    act_description=act_description,
                    uif_code=uif_code,
                    cod_acto_spouse=cod_acto_spouse,
                )
            )

        if include_structural_roles:
            errors.extend(
                self._structural_role_errors(
                    staged=staged,
                    act_description=act_description,
                    uif_code=uif_code,
                    has_o=has_o,
                    has_b=has_b,
                )
            )
        return errors

    def _collect_participants_complementary(
        self,
        kardex: str,
        cod_acto: str,
        range_start: date,
        range_end: date,
        contratantes_map: Dict,
        clientes_map: Dict,
        contratantesxacto_map: Dict,
    ) -> List[dict]:
        act_variants = {cod_acto, str(cod_acto).zfill(3), str(cod_acto).lstrip("0")}
        act_padded = str(cod_acto).zfill(3)
        result = []

        for contratante in contratantes_map.get(kardex, []):
            if not firma_in_report_range(contratante.fechafirma, range_start, range_end):
                continue
            cxa = contratantesxacto_map.get(
                f"{kardex}_{cod_acto}_{contratante.idcontratante}"
            ) or contratantesxacto_map.get(
                f"{kardex}_{act_padded}_{contratante.idcontratante}"
            )
            if not cxa or str(cxa.idtipoacto or "") not in act_variants:
                continue
            role = (cxa.uif or "").strip().upper()
            if role not in PLANE_PARTICIPANT_ROLES:
                continue
            cliente = clientes_map.get(contratante.idcontratante)
            if not cliente:
                continue
            result.append(
                {
                    "role": role,
                    "cxa": cxa,
                    "cliente": cliente,
                    "contratante": contratante,
                    "nombre": _participant_name(cliente, contratante.idcontratante),
                }
            )
        result.sort(key=lambda x: x["role"], reverse=True)
        return result

    def _collect_participants(
        self,
        kardex: str,
        cod_acto: str,
        contratantes_map: Dict,
        clientes_map: Dict,
        contratantesxacto_map: Dict,
    ) -> List[dict]:
        act_variants = {cod_acto, str(cod_acto).zfill(3), str(cod_acto).lstrip("0")}
        act_padded = str(cod_acto).zfill(3)
        result = []

        for contratante in contratantes_map.get(kardex, []):
            cxa = contratantesxacto_map.get(
                f"{kardex}_{cod_acto}_{contratante.idcontratante}"
            ) or contratantesxacto_map.get(
                f"{kardex}_{act_padded}_{contratante.idcontratante}"
            )
            if not cxa:
                continue
            role = (cxa.uif or "").strip().upper()
            if role not in PLANE_PARTICIPANT_ROLES:
                continue
            cliente = clientes_map.get(contratante.idcontratante)
            if not cliente:
                continue
            result.append(
                {
                    "role": role,
                    "cxa": cxa,
                    "cliente": cliente,
                    "contratante": contratante,
                    "nombre": _participant_name(cliente, contratante.idcontratante),
                }
            )

        result.sort(key=lambda x: x["role"], reverse=True)
        return result

    def _validate_one(
        self,
        *,
        item: dict,
        staged,
        act_description: str,
        uif_code: str,
        cod_acto_spouse: str = "",
    ) -> List[dict]:
        errors: List[dict] = []
        role = item["role"]
        cliente = item["cliente"]
        contratante = item["contratante"]
        nombre = item["nombre"]
        tipper = (cliente.tipper or "").strip().upper()
        base = {
            "id_kardex": staged.id_kardex,
            "kardex": staged.kardex,
            "act": act_description,
            "codacto": staged.cod_acto,
            "uif_code": uif_code,
            "row_type": ROW_TYPE_PARTICIPANT,
            "id_contratante": contratante.idcontratante,
            "details_error": nombre,
        }

        def add(
            field_number: int,
            error_type: str,
            description: str,
            *,
            code_element: int = 0,
            is_correctable: bool = False,
            type_of_correction: str = "",
            category_correct: str = "RO",
        ):
            errors.append(
                build_ro_error(
                    **base,
                    error_type=error_type,
                    error_description=description,
                    field_number=field_number,
                    code_element=code_element,
                    is_correctable=is_correctable,
                    type_of_correction=type_of_correction,
                    category_correct=category_correct,
                )
            )

        uif_val = (item["cxa"].uif or "").strip()
        if not uif_val:
            add(FIELD_REPRESENTANTE, "missing_uif_role", f"{nombre}: rol UIF vacío")
            add(FIELD_PERSONA_OPERACION, "missing_uif_role", f"{nombre}: rol UIF vacío")
            add(FIELD_PERSONA_AFAVOR, "missing_uif_role", f"{nombre}: rol UIF vacío")

        if role == ROLE_REPRESENTANTE:
            id_rp = (contratante.idcontratanterp or "").strip()
            if not id_rp:
                add(
                    FIELD_PERSONA_QUE_REPRESENTA,
                    "missing_persona_que_representa",
                    f"{nombre}: persona que representa requerida",
                )
            elif not self._resolve_persona_que_representa(id_rp):
                add(
                    FIELD_PERSONA_QUE_REPRESENTA,
                    "missing_persona_que_representa",
                    f"{nombre}: persona que representa requerida",
                )
            inscrito = contratante.inscrito
            if inscrito is None or str(inscrito).strip() == "":
                add(
                    FIELD_TIPO_REPRESENTACION,
                    "missing_tipo_representacion",
                    f"{nombre}: tipo de representación requerido",
                )

        residente = str(cliente.residente or "").strip()
        if residente.upper() == "NULL":
            add(
                FIELD_CONDICION_RESIDENCIA,
                "invalid_condicion_residencia",
                f"{nombre}: condición de residencia inválida",
            )

        if not tipper:
            add(FIELD_TIPO_PERSONA, "missing_tipo_persona", f"{nombre}: tipo de persona requerido")

        if tipper == "N":
            if not cliente.idtipdoc or cliente.idtipdoc not in self.tipodoc_map:
                add(
                    FIELD_TIPO_DOCUMENTO,
                    "missing_tipo_documento",
                    f"{nombre}: tipo de documento requerido",
                )
            if not (cliente.numdoc or "").strip():
                add(
                    FIELD_NUMERO_DOCUMENTO,
                    "missing_numero_documento",
                    f"{nombre}: número de documento requerido",
                )
            cod_nacion = self.nacion_map.get(str(cliente.nacionalidad or "").strip(), "")
            cod_tipo_doc = self.tipodoc_map.get(cliente.idtipdoc, "")
            if cod_nacion and cod_tipo_doc:
                if (cod_nacion == "PE" and cod_tipo_doc not in DOCUMENT_TYPES_PERU) or (
                    cod_nacion != "PE" and cod_tipo_doc in DOCUMENT_TYPES_PERU
                ):
                    add(
                        FIELD_TIPO_DOCUMENTO,
                        "nacionalidad_documento_mismatch",
                        f"{nombre}, la nacionalidad no corresponde al tipo del documento",
                    )
            numdoc = (cliente.numdoc or "").strip()
            if cliente.idtipdoc == 1 and numdoc:
                if len(numdoc) != 8 or not numdoc.isdigit():
                    add(
                        FIELD_NUMERO_DOCUMENTO,
                        "invalid_dni",
                        f"{nombre}, su DNI es incorrecto",
                    )
            if not (cliente.apepat or "").strip():
                add(
                    FIELD_APELLIDO_RAZON,
                    "missing_apellido_paterno",
                    f"{nombre}: apellido paterno o razón social requerido",
                )
            if not (cliente.prinom or "").strip() and not (cliente.segnom or "").strip():
                add(
                    FIELD_NOMBRES,
                    "missing_nombres",
                    f"{nombre}: nombres requeridos",
                )
            nat_id = str(cliente.nacionalidad or "").strip()
            if nat_id and nat_id not in self.nacion_map:
                add(
                    FIELD_NACIONALIDAD,
                    "missing_nacionalidad",
                    f"{nombre}: nacionalidad requerida",
                )
            if cliente.idestcivil not in self.civil_map:
                add(
                    FIELD_ESTADO_CIVIL,
                    "missing_estado_civil",
                    f"{nombre}: estado civil requerido",
                )
            if cliente.idprofesion and cliente.idprofesion not in self.prof_map:
                add(
                    FIELD_PROFESION,
                    "missing_profesion",
                    f"{nombre}: profesión requerida",
                    is_correctable=True,
                    type_of_correction="MANUAL",
                    category_correct="2",
                )
            elif cliente.idprofesion is None:
                add(
                    FIELD_PROFESION,
                    "missing_profesion",
                    f"{nombre}: profesión requerida",
                    is_correctable=True,
                    type_of_correction="MANUAL",
                    category_correct="2",
                )
            if cliente.idcargoprofe and cliente.idcargoprofe not in self.cargo_map:
                add(
                    FIELD_CARGO,
                    "missing_cargo",
                    f"{nombre}: cargo requerido",
                    is_correctable=True,
                    type_of_correction="MANUAL",
                    category_correct="3",
                )
            elif cliente.idcargoprofe is None:
                add(
                    FIELD_CARGO,
                    "missing_cargo",
                    f"{nombre}: cargo requerido",
                    is_correctable=True,
                    type_of_correction="MANUAL",
                    category_correct="3",
                )
            if not (cliente.direccion or "").strip():
                add(
                    FIELD_DIRECCION,
                    "missing_direccion",
                    f"{nombre}: dirección requerida",
                )
        elif tipper == "J":
            if cliente.idtipdoc == 8 and not (cliente.numdoc or "").strip():
                add(
                    FIELD_NUMERO_RUC,
                    "missing_numero_ruc",
                    f"{nombre}: RUC requerido",
                )
            if not (cliente.razonsocial or "").strip():
                add(
                    FIELD_APELLIDO_RAZON,
                    "missing_razon_social",
                    f"{nombre}: razón social requerida",
                )
            if not (cliente.contacempresa or "").strip():
                add(
                    FIELD_OBJETO_SOCIAL,
                    "missing_objeto_social",
                    f"{nombre}: objeto social requerido",
                )
            act_key = str(cliente.actmunicipal or "").strip()
            if act_key and act_key not in self.ciiu_keys:
                add(
                    FIELD_CIIU,
                    "missing_ciiu",
                    f"{nombre}: código CIIU requerido",
                )
            elif not act_key:
                add(
                    FIELD_CIIU,
                    "missing_ciiu",
                    f"{nombre}: código CIIU requerido",
                )
            numdoc = (cliente.numdoc or "").strip()
            if tipper == "J" and cliente.idtipdoc != 10 and numdoc:
                if len(numdoc) != 11 or not numdoc.isdigit():
                    err = build_ro_error(
                        **base,
                        error_type="invalid_ruc",
                        error_description=f"{nombre}, su RUC es incorrecto",
                        field_number=FIELD_NUMERO_DOCUMENTO,
                    )
                    if uif_code in ACTS_CONSTITUCION_RUC_CORRECTABLE:
                        err["isCorrectable"] = 1
                        err["typeOfCorrection"] = "MANUAL"
                        err["categoryCorrect"] = "1"
                        err["idContratante"] = contratante.idcontratante
                    errors.append(err)
            if not (cliente.domfiscal or "").strip():
                add(
                    FIELD_DIRECCION,
                    "missing_direccion",
                    f"{nombre}: domicilio fiscal requerido",
                )

        if role == ROLE_REPRESENTANTE and str(contratante.inscrito or "") == "1":
            if not str(contratante.idsedereg or "").strip() or str(contratante.idsedereg) == "0":
                add(
                    FIELD_ZONA_REGISTRAL,
                    "missing_zona_registral",
                    f"{nombre}: zona registral requerida",
                )
            if not (contratante.numpartida or "").strip():
                add(
                    FIELD_PARTIDA_REGISTRAL,
                    "missing_partida_registral",
                    f"{nombre}: número de partida registral requerido",
                )

        ubi = self._ubigeo(cliente.idubigeo)
        if not ubi:
            if not (cliente.idubigeo or "").strip():
                add(
                    FIELD_DISTRITO,
                    "missing_ubigeo",
                    f"{nombre}: EL UBIGEO ES INCORRECTO, SELECIONE UN UBIGEO VALIDO",
                )
            else:
                add(
                    FIELD_DEPARTAMENTO,
                    "missing_departamento",
                    f"{nombre}: departamento requerido",
                )
                add(
                    FIELD_PROVINCIA,
                    "missing_provincia",
                    f"{nombre}: provincia requerida",
                )
                add(
                    FIELD_DISTRITO,
                    "missing_distrito",
                    f"{nombre}: distrito requerido",
                )

        # RoClass does not block export when firma/fechafirma are missing on tipo I:
        # it only sets item 9 conclusion to N for PN (see plane_rows._participant_fields).
        # Complementaria (C) already limits participants via firma_in_report_range at collection.
        fecha_firma = _format_date_ddmmyyyy(contratante.fechafirma)
        if not fecha_firma and contratante.fechafirma:
            add(
                FIELD_FECHA_FIRMA,
                "invalid_fecha_firma",
                f"{nombre}: fecha de firma inválida",
            )

        errors.extend(
            self._validate_conyuge_fields(
                cliente=cliente,
                role=role,
                nombre=nombre,
                kardex=staged.kardex,
                cod_acto=cod_acto_spouse or staged.cod_acto,
                uif_code=uif_code,
                base=base,
                add=add,
            )
        )

        return errors

    def _validate_conyuge_fields(
        self,
        *,
        cliente,
        role: str,
        nombre: str,
        kardex: str,
        cod_acto: str,
        uif_code: str,
        base: dict,
        add,
    ) -> List[dict]:
        """RoClass items 40–43: participación + nombre del cónyuge en el acto."""
        errors: List[dict] = []
        participacion, ap_pat, ap_mat, nom_con = resolve_conyuge_fields(
            cliente, role, kardex, cod_acto
        )
        conyuge_id = str(cliente.conyuge or "").strip()

        if conyuge_id and role != ROLE_REPRESENTANTE and participacion == "N":
            for field_no, err_type, desc in (
                (
                    FIELD_PARTICIPACION_CONYUGE,
                    "spouse_not_in_act",
                    f"{nombre}: el cónyuge no participa en el acto",
                ),
                (
                    FIELD_APELLIDO_PATERNO_CONYUGE,
                    "missing_apellido_paterno_conyuge",
                    f"{nombre}: apellido paterno del cónyuge requerido",
                ),
                (
                    FIELD_APELLIDO_MATERNO_CONYUGE,
                    "missing_apellido_materno_conyuge",
                    f"{nombre}: apellido materno del cónyuge requerido",
                ),
                (
                    FIELD_NOMBRES_CONYUGE,
                    "missing_nombres_conyuge",
                    f"{nombre}: nombres del cónyuge requeridos",
                ),
            ):
                add(field_no, err_type, desc)
            return []

        field_values = (
            (FIELD_PARTICIPACION_CONYUGE, participacion, "invalid_participacion_conyuge"),
            (FIELD_APELLIDO_PATERNO_CONYUGE, ap_pat, "invalid_apellido_paterno_conyuge"),
            (FIELD_APELLIDO_MATERNO_CONYUGE, ap_mat, "invalid_apellido_materno_conyuge"),
            (FIELD_NOMBRES_CONYUGE, nom_con, "invalid_nombres_conyuge"),
        )
        for field_no, value, err_type in field_values:
            rule = self.rules.get(uif_code, field_no)
            if not rule or not rule.data_value:
                continue
            if validation_code(str(value or ""), rule.data_value):
                errors.append(
                    build_ro_error(
                        **base,
                        error_type=err_type,
                        error_description=(
                            f"{nombre}: {self.rules.field_label(field_no)} inválido"
                        ),
                        field_number=field_no,
                        detail_value=rule.detail_value or rule.data_value or "",
                    )
                )
        return errors

    def _structural_role_errors(
        self,
        *,
        staged,
        act_description: str,
        uif_code: str,
        has_o: bool,
        has_b: bool,
    ) -> List[dict]:
        errors = []
        base = {
            "id_kardex": staged.id_kardex,
            "kardex": staged.kardex,
            "act": act_description,
            "codacto": staged.cod_acto,
            "uif_code": uif_code,
        }
        if not has_o and uif_code not in ACTS_EXEMPT_OTORGANTE_AMOUNT:
            errors.append(
                build_ro_error(
                    **base,
                    error_type="missing_otorgante_role",
                    error_description="Falta participante otorgante (O) en el acto",
                    field_number=FIELD_PERSONA_OPERACION,
                    row_type=ROW_TYPE_PARTICIPANT,
                )
            )
        if not has_b and uif_code not in ACTS_EXEMPT_BENEFICIARIO_AMOUNT:
            errors.append(
                build_ro_error(
                    **base,
                    error_type="missing_beneficiario_role",
                    error_description="Falta participante beneficiario (B) en el acto",
                    field_number=FIELD_PERSONA_AFAVOR,
                    row_type=ROW_TYPE_PARTICIPANT,
                )
            )
        return errors

    def _resolve_persona_que_representa(self, id_contratante_rp: str) -> Optional[str]:
        rep = (
            Contratantesxacto.objects.filter(idcontratante=str(id_contratante_rp).strip())
            .exclude(uif__isnull=True)
            .exclude(uif="")
            .filter(uif__in=["B", "O", "G", "F", "N", "R"])
            .first()
        )
        if not rep or not rep.uif:
            return None
        return "N" if rep.uif == "R" else rep.uif

    def _ubigeo(self, coddis: str) -> Optional[Ubigeo]:
        key = str(coddis or "").strip()
        if not key:
            return None
        if key not in self._ubigeo_cache:
            self._ubigeo_cache[key] = Ubigeo.objects.filter(coddis=key).first()
        return self._ubigeo_cache[key]
