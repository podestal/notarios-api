from decimal import Decimal
from unittest.mock import MagicMock

from django.test import SimpleTestCase

from uif.services.operation_validator import RoOperationValidator
from uif.services.ro_validation_rules import RoValidationRulesRepository
from uif.services.staging import RoStagedRecord


def _staged(**kwargs):
    defaults = dict(
        id_kardex=1,
        kardex="K1",
        id_tipo_kardex=1,
        tipo_instrumento="E",
        cod_acto="001",
        uif_code="010",
        numero_escritura="10",
        fecha_escritura=None,
        fecha_conclusion="01/01/2026",
        tipo="I",
    )
    defaults.update(kwargs)
    return RoStagedRecord(**defaults)


class OperationValidatorTests(SimpleTestCase):
    def test_missing_fecha_conclusion_is_not_a_validation_error(self):
        """PHP parity: empty fechaconclusion → plane item 9 N, not lista_errores."""
        rules = RoValidationRulesRepository()
        rules._loaded = True
        rules._rules = {}
        validator = RoOperationValidator(rules)
        pat = MagicMock(
            fpago="1",
            idoppago="1",
            des_idoppago="",
            idmon=1,
            importetrans=Decimal("1000"),
            exhibiomp="No",
        )
        detalle = MagicMock(kardex="K1", tipacto="001", codmepag=1, importemp=1000)
        errors = validator.validate(
            staged=_staged(fecha_conclusion=None),
            act_description="COMPRA VENTA",
            patrimonial=pat,
            detalle_medio_pago_rows=[detalle],
            fpago_codigo_map={"1": "C"},
        )
        self.assertFalse(
            any(e["error_type"] == "missing_conclusion_date" for e in errors)
        )
        self.assertFalse(
            any("conclusión" in (e.get("error_description") or "").lower() for e in errors)
        )

    def test_invalid_forma_pago_when_codigo_missing(self):
        rules = RoValidationRulesRepository()
        rules._loaded = True
        rules._rules = {
            ("010", 46): MagicMock(
                data_value="C|P|S", detail_value="CONTADO|PLAZOS|SALDO"
            ),
        }
        validator = RoOperationValidator(rules)
        pat = MagicMock(
            fpago="99",
            idoppago="01",
            des_idoppago="",
            idmon=1,
            importetrans=Decimal("50000"),
            exhibiomp="No",
        )
        staged = _staged()
        errors = validator.validate(
            staged=staged,
            act_description="COMPRA VENTA",
            patrimonial=pat,
            detalle_medio_pago_rows=[],
            fpago_codigo_map={"99": ""},
        )
        self.assertTrue(any(e["error_type"] == "invalid_forma_pago" for e in errors))

    def test_oportunidad_vacio_id_10_passes_when_rule_expects_v(self):
        """Act 053-style rules: patrimonial.idoppago=10 (VACIO) validates as V."""
        rules = RoValidationRulesRepository()
        rules._loaded = True
        rules._rules = {
            ("053", 47): MagicMock(data_value="V", detail_value="VACIO"),
        }
        validator = RoOperationValidator(rules)
        pat = MagicMock(
            fpago="4",
            idoppago="10",
            des_idoppago="",
            idmon=1,
            importetrans=Decimal("137000"),
            exhibiomp="No",
        )
        staged = _staged(uif_code="053", cod_acto="119")
        errors = validator.validate(
            staged=staged,
            act_description="TRANSFERENCIA DE ACCIONES SOCIALES A TITULO GRATUITO",
            patrimonial=pat,
            detalle_medio_pago_rows=[],
            fpago_codigo_map={"4": "D"},
        )
        self.assertFalse(any(e["error_type"] == "invalid_oportunidad_pago" for e in errors))

    def test_gratuito_sin_detalle_medio_errors_like_php(self):
        """RoClass tipo I: no detallemediopago rows → 590 even if exhibiomp=No (K2-style)."""
        rules = RoValidationRulesRepository()
        rules._loaded = True
        rules._rules = {
            ("053", 46): MagicMock(data_value="N|D", detail_value="NO APLICA|DONACION"),
            ("053", 47): MagicMock(data_value="V", detail_value="VACIO"),
        }
        validator = RoOperationValidator(rules)
        pat = MagicMock(
            fpago="5",
            idoppago="",
            des_idoppago="",
            idmon=1,
            importetrans=Decimal("137000"),
            exhibiomp="No",
        )
        staged = _staged(uif_code="053", cod_acto="119")
        errors = validator.validate(
            staged=staged,
            act_description="TRANSFERENCIA DE ACCIONES SOCIALES A TITULO GRATUITO",
            patrimonial=pat,
            detalle_medio_pago_rows=[],
            fpago_codigo_map={"5": "N"},
        )
        missing = [e for e in errors if e["error_type"] == "missing_medio_pago_rows"]
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0]["codeElement"], 590)

    def test_sin_detalle_medio_errors_regardless_of_exhibiomp(self):
        """PHP does not gate missing medios on patrimonial.exhibiomp."""
        rules = RoValidationRulesRepository()
        rules._loaded = True
        rules._rules = {}
        validator = RoOperationValidator(rules)
        for exhibiomp in ("No", "Si", ""):
            pat = MagicMock(
                fpago="1",
                idoppago="1",
                des_idoppago="",
                idmon=1,
                importetrans=Decimal("1000"),
                exhibiomp=exhibiomp,
            )
            errors = validator.validate(
                staged=_staged(),
                act_description="COMPRA VENTA",
                patrimonial=pat,
                detalle_medio_pago_rows=[],
                fpago_codigo_map={"1": "C"},
            )
            self.assertTrue(
                any(e["error_type"] == "missing_medio_pago_rows" for e in errors),
                msg=f"expected error for exhibiomp={exhibiomp!r}",
            )

    def test_complementary_skips_missing_medio_rows_check(self):
        """tipo C (información complementaria) — PHP does not emit 590 in that branch."""
        rules = RoValidationRulesRepository()
        rules._loaded = True
        rules._rules = {}
        validator = RoOperationValidator(rules)
        pat = MagicMock(
            fpago="1",
            idoppago="1",
            des_idoppago="",
            idmon=1,
            importetrans=Decimal("1000"),
            exhibiomp="No",
        )
        errors = validator.validate(
            staged=_staged(tipo="C"),
            act_description="COMPRA VENTA",
            patrimonial=pat,
            detalle_medio_pago_rows=[],
            fpago_codigo_map={"1": "C"},
        )
        self.assertFalse(
            any(e["error_type"] == "missing_medio_pago_rows" for e in errors)
        )

    def test_empty_medio_uif_validates_as_v_like_php(self):
        """RoClass: IF(mediospago.uif = '', 'V', mediospago.uif) before field-44 REGEXP."""
        rules = RoValidationRulesRepository()
        rules._loaded = True
        rules._field_labels = {44: "Código de tipo de fondo"}
        rules._rules = {
            ("053", 44): MagicMock(data_value="V", detail_value="VACIO"),
        }
        validator = RoOperationValidator(rules)
        pat = MagicMock(
            fpago="5",
            idoppago="10",
            des_idoppago="",
            idmon=1,
            importetrans=Decimal("137000"),
            exhibiomp="No",
        )
        detalle = MagicMock(kardex="K2-2026", tipacto="119", codmepag=99, importemp=137000)
        validator._resolve_medio_pago_uif = MagicMock(return_value="")

        errors = validator.validate(
            staged=_staged(
                kardex="K2-2026",
                uif_code="053",
                cod_acto="119",
            ),
            act_description="TRANSFERENCIA DE ACCIONES SOCIALES A TITULO GRATUITO",
            patrimonial=pat,
            detalle_medio_pago_rows=[detalle],
            fpago_codigo_map={"5": "N"},
        )
        self.assertFalse(
            any(e["error_type"] == "invalid_medio_pago_codigo" for e in errors)
        )

    def test_field_53_monto_tipo_fondo_not_enforced_on_dashboard(self):
        """Field 53 ro_validation_by_act is not a hard stop — do not block the dashboard."""
        rules = RoValidationRulesRepository()
        rules._loaded = True
        rules._field_labels = {53: "Monto tipo de fondo"}
        rules._rules = {
            ("053", 53): MagicMock(
                data_value=r"^[0]*[.][0]{2}|V$",
                detail_value="En Blanco",
            ),
        }
        validator = RoOperationValidator(rules)
        pat = MagicMock(
            fpago="5",
            idoppago="10",
            des_idoppago="",
            idmon=1,
            importetrans=Decimal("137000"),
            exhibiomp="No",
        )
        detalle = MagicMock(
            kardex="K2-2026",
            tipacto="119",
            codmepag=99,
            importemp=Decimal("137000"),
        )
        errors = validator.validate(
            staged=_staged(
                kardex="K2-2026",
                uif_code="053",
                cod_acto="119",
            ),
            act_description="TRANSFERENCIA DE ACCIONES SOCIALES A TITULO GRATUITO",
            patrimonial=pat,
            detalle_medio_pago_rows=[detalle],
            fpago_codigo_map={"5": "N"},
        )
        self.assertFalse(
            any(e["error_type"] == "invalid_monto_tipo_fondo" for e in errors)
        )
