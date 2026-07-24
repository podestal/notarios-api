from django.test import SimpleTestCase

from notaria.services.participation_split import divide_evenly, parse_finite_decimal
from notaria.views import _sanitize_contratantesxacto_patch
from unittest.mock import MagicMock


class ParticipationSplitTest(SimpleTestCase):
    def test_three_way_money_split_24900(self):
        self.assertEqual(divide_evenly(3, 24900), [8300.0, 8300.0, 8300.0])

    def test_three_way_money_split_24900_string(self):
        self.assertEqual(divide_evenly(3, "24900.00"), [8300.0, 8300.0, 8300.0])

    def test_three_way_percent_split_100(self):
        self.assertEqual(divide_evenly(3, 100), [33.33, 33.33, 33.34])
        self.assertAlmostEqual(sum(divide_evenly(3, 100)), 100.0)

    def test_remainder_goes_to_first_slots(self):
        # 100.00 / 3 cents → 33.33 + 33.33 + 33.34
        self.assertEqual(divide_evenly(3, 100), [33.33, 33.33, 33.34])

    def test_single_participant_gets_all(self):
        self.assertEqual(divide_evenly(1, 24900), [24900.0])

    def test_zero_count(self):
        self.assertEqual(divide_evenly(0, 24900), [])

    def test_amounts_not_equal_to_pct_times_total(self):
        """Montos must not be derived as pct/100*total (legacy rounding bug)."""
        amounts = divide_evenly(3, 24900)
        pcts = divide_evenly(3, 100)
        for amt, pct in zip(amounts, pcts):
            legacy_monto = round(24900 * pct / 100, 2)
            if pct == 33.33:
                self.assertNotEqual(amt, legacy_monto)
            self.assertEqual(amt, 8300.0)

    def test_rejects_infinity_strings(self):
        for bad in ("inf", "Infinity", "-Infinity", "nan", float("inf")):
            with self.assertRaises(ValueError):
                parse_finite_decimal(bad, field="porcentaje")

    def test_strip_monto_when_editing_ofondo(self):
        instance = MagicMock(monto="8300.00", porcentaje="33.33", ofondo="OLD", opago="")
        payload = {"ofondo": "AHORROS", "monto": "8299.17", "porcentaje": "33.33"}
        cleaned = _sanitize_contratantesxacto_patch(payload, instance)
        self.assertEqual(cleaned["ofondo"], "AHORROS")
        self.assertNotIn("monto", cleaned)
        self.assertNotIn("porcentaje", cleaned)

    def test_strip_ofondo_when_editing_monto_only(self):
        instance = MagicMock(
            monto="8299.17",
            porcentaje="33.33",
            ofondo="AHORROS NUEVO",
            opago="",
        )
        payload = {
            "monto": "8300.00",
            "porcentaje": "33.33",
            "ofondo": "AHORROS VIEJO",
        }
        cleaned = _sanitize_contratantesxacto_patch(payload, instance)
        self.assertEqual(cleaned["monto"], "8300.00")
        self.assertNotIn("ofondo", cleaned)

    def test_keep_monto_when_not_uif_edit(self):
        instance = MagicMock(monto="8300.00", porcentaje="33.33", ofondo="", opago="")
        payload = {"monto": "8400.00", "porcentaje": "33.33"}
        cleaned = _sanitize_contratantesxacto_patch(payload, instance)
        self.assertEqual(cleaned["monto"], "8400.00")
