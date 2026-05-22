from decimal import Decimal
from unittest.mock import MagicMock

from django.test import SimpleTestCase

from uif.services.constants import SPECIAL_UIF_CODES, USD_THRESHOLD
from uif.services.generate_data import RoGenerateDataService
from uif.services.staging import RoStagedRecord


def _staged(uif="010", kardex="K1", cod="001"):
    return RoStagedRecord(
        id_kardex=1,
        kardex=kardex,
        id_tipo_kardex=1,
        tipo_instrumento="E",
        cod_acto=cod,
        uif_code=uif,
        numero_escritura="1",
        fecha_escritura=None,
        fecha_conclusion=None,
        tipo="I",
    )


class PassesThresholdTests(SimpleTestCase):
    def test_special_uif_code_always_passes(self):
        code = next(iter(SPECIAL_UIF_CODES))
        self.assertTrue(RoGenerateDataService.passes_threshold(code, None))

    def test_usd_above_threshold(self):
        pat = MagicMock(idmon=2, importetrans=Decimal("3000"), tipocambio=None)
        self.assertTrue(RoGenerateDataService.passes_threshold("010", pat))

    def test_usd_below_threshold(self):
        pat = MagicMock(idmon=2, importetrans=Decimal("1000"), tipocambio=None)
        self.assertFalse(RoGenerateDataService.passes_threshold("010", pat))

    def test_soles_converted_with_exchange(self):
        pat = MagicMock(idmon=1, importetrans=Decimal("9000"), tipocambio="3.5")
        self.assertTrue(RoGenerateDataService.passes_threshold("010", pat))

    def test_soles_without_exchange_uses_7500_threshold(self):
        pat = MagicMock(idmon=1, importetrans=Decimal("8000"), tipocambio="")
        self.assertTrue(RoGenerateDataService.passes_threshold("010", pat))
        pat_low = MagicMock(idmon=1, importetrans=Decimal("5000"), tipocambio="")
        self.assertFalse(RoGenerateDataService.passes_threshold("010", pat_low))


class PartitionTests(SimpleTestCase):
    def test_splits_eligible_and_below(self):
        staged = _staged()
        pat_ok = MagicMock(idmon=2, importetrans=Decimal(str(USD_THRESHOLD + 100)), tipocambio=None)
        pat_low = MagicMock(idmon=2, importetrans=Decimal("100"), tipocambio=None)
        patrimonial_map = {
            (staged.kardex, "001"): pat_ok,
        }
        staged_low = _staged(kardex="K2", cod="002")
        patrimonial_map[(staged_low.kardex, "002")] = pat_low

        eligible, below = RoGenerateDataService().partition_by_threshold(
            [staged, staged_low], patrimonial_map
        )
        self.assertEqual(len(eligible), 1)
        self.assertEqual(len(below), 1)
        self.assertEqual(eligible[0].kardex, "K1")
        self.assertEqual(below[0].kardex, "K2")
