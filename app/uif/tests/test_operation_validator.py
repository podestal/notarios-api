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

    def test_gratuito_sin_detalle_medio_no_unconditional_missing_rows(self):
        """K2-style: act 053, fpago N, idoppago vacío, exhibiomp No — PHP does not block RO."""
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
        self.assertFalse(
            any(e["error_type"] == "missing_medio_pago_rows" for e in errors)
        )

    def test_exhibiomp_si_sin_detalle_medio_still_errors(self):
        """When medios are exhibited, missing detallemediopago rows is still an error."""
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
            exhibiomp="Si",
        )
        errors = validator.validate(
            staged=_staged(),
            act_description="COMPRA VENTA",
            patrimonial=pat,
            detalle_medio_pago_rows=[],
            fpago_codigo_map={"1": "C"},
        )
        self.assertTrue(
            any(e["error_type"] == "missing_medio_pago_rows" for e in errors)
        )
