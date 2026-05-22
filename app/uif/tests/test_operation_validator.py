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
