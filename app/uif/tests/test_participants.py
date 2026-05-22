from decimal import Decimal
from unittest.mock import MagicMock

from django.test import SimpleTestCase

from uif.services.participants import PatrimonialParticipantValidator
from uif.services.ro_validation_rules import RoValidationRulesRepository


class ParticipantAmountTests(SimpleTestCase):
    def setUp(self):
        rules = RoValidationRulesRepository()
        rules._loaded = True
        rules._rules = {}
        self.validator = PatrimonialParticipantValidator(rules)

    def _patrimonial(self, importe="150000", idmon=1):
        p = MagicMock()
        p.idmon = idmon
        p.importetrans = Decimal(importe)
        p.tipocambio = "3.5"
        p.kardex = "K1"
        return p

    def _cxa(self, role, monto):
        c = MagicMock()
        c.uif = role
        c.monto = monto
        return c

    def test_only_o_and_b_included_in_amount_sum(self):
        """Non O/B roles must not trigger amount_mismatch (Phase 1 bug)."""
        patrimonial_map = {("K1", "001"): self._patrimonial()}
        contratante_o = MagicMock(idcontratante="1")
        contratante_r = MagicMock(idcontratante="2")
        contratantes_map = {"K1": [contratante_o, contratante_r]}
        clientes_map = {
            "1": MagicMock(nombre="Otorgante", razonsocial=None),
            "2": MagicMock(nombre="Rep", razonsocial=None),
        }
        contratantesxacto_map = {
            "K1_001_1": self._cxa("O", "150000"),
            "K1_001_2": self._cxa("R", "999999"),
        }

        errors = self.validator.validate(
            "K1",
            "001",
            "COMPRA VENTA",
            "010",
            1,
            patrimonial_map,
            contratantes_map,
            clientes_map,
            contratantesxacto_map,
        )
        amount_errors = [e for e in errors if e["error_type"] == "amount_mismatch"]
        self.assertEqual(amount_errors, [])

    def test_otorgante_mismatch_when_sum_differs(self):
        patrimonial_map = {("K1", "001"): self._patrimonial()}
        contratante = MagicMock(idcontratante="1")
        contratantes_map = {"K1": [contratante]}
        clientes_map = {"1": MagicMock(nombre="Juan", razonsocial=None)}
        contratantesxacto_map = {"K1_001_1": self._cxa("O", "200000")}

        errors = self.validator.validate(
            "K1",
            "001",
            "COMPRA VENTA",
            "010",
            1,
            patrimonial_map,
            contratantes_map,
            clientes_map,
            contratantesxacto_map,
        )
        self.assertTrue(any(e["error_type"] == "amount_mismatch" for e in errors))
        self.assertIn("otorgantes", errors[0]["error_description"])
