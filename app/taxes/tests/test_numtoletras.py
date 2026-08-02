"""
Regression tests for monetary amount → Spanish words (SUNAT Note / PDF).

The old converter turned 88 into \"OCHO MIL OCHENTA Y OCHO\". These cases
must stay green — wrong letters on real money is not acceptable.
"""

from decimal import Decimal

from django.test import SimpleTestCase

from taxes.services.pdf.numtoletras import numtoletras


class NumToLetrasRegressionTests(SimpleTestCase):
    def test_eighty_eight_is_not_eight_thousand(self):
        text = numtoletras("88.00")
        self.assertEqual(text, "OCHENTA Y OCHO CON 00/100 SOLES")
        self.assertNotIn("MIL", text)

    def test_amounts_under_one_thousand_never_say_mil(self):
        for n in range(0, 1000):
            text = numtoletras(n)
            with self.subTest(n=n, text=text):
                self.assertNotIn("MIL", text)
                self.assertIn("CON", text)

    def test_eight_thousand_eighty_eight(self):
        self.assertEqual(
            numtoletras(8088),
            "OCHO MIL OCHENTA Y OCHO CON 00/100 SOLES",
        )


class NumToLetrasCoreCasesTests(SimpleTestCase):
    CASES = (
        (0, "CERO CON 00/100 SOLES"),
        (0.5, "CERO CON 50/100 SOLES"),
        (1, "UN SOL CON 00/100"),
        (1.05, "UN SOL CON 05/100"),
        (2, "DOS CON 00/100 SOLES"),
        (10, "DIEZ CON 00/100 SOLES"),
        (15, "QUINCE CON 00/100 SOLES"),
        (20, "VEINTE CON 00/100 SOLES"),
        (21, "VEINTIUNO CON 00/100 SOLES"),
        (22, "VEINTIDOS CON 00/100 SOLES"),
        (30, "TREINTA CON 00/100 SOLES"),
        (31, "TREINTA Y UNO CON 00/100 SOLES"),
        (88, "OCHENTA Y OCHO CON 00/100 SOLES"),
        (99, "NOVENTA Y NUEVE CON 00/100 SOLES"),
        (100, "CIEN CON 00/100 SOLES"),
        (101, "CIENTO UNO CON 00/100 SOLES"),
        (118, "CIENTO DIECIOCHO CON 00/100 SOLES"),
        (200, "DOSCIENTOS CON 00/100 SOLES"),
        (999, "NOVECIENTOS NOVENTA Y NUEVE CON 00/100 SOLES"),
        (1000, "MIL CON 00/100 SOLES"),
        (1001, "MIL UNO CON 00/100 SOLES"),
        (1100, "MIL CIEN CON 00/100 SOLES"),
        (2500, "DOS MIL QUINIENTOS CON 00/100 SOLES"),
        (1000000, "UN MILLON CON 00/100 SOLES"),
        (2000000, "DOS MILLONES CON 00/100 SOLES"),
        (1000001, "UN MILLON UNO CON 00/100 SOLES"),
    )

    def test_known_amounts(self):
        for value, expected in self.CASES:
            with self.subTest(value=value):
                self.assertEqual(numtoletras(value), expected)

    def test_input_types_agree(self):
        expected = "OCHENTA Y OCHO CON 00/100 SOLES"
        for value in (88, 88.0, "88", "88.00", Decimal("88.00"), "88,00"):
            with self.subTest(value=repr(value)):
                self.assertEqual(numtoletras(value), expected)

    def test_thousands_separator_string(self):
        self.assertEqual(
            numtoletras("1,234.56"),
            "MIL DOSCIENTOS TREINTA Y CUATRO CON 56/100 SOLES",
        )

    def test_rounding_half_up(self):
        self.assertEqual(
            numtoletras("10.005"),
            "DIEZ CON 01/100 SOLES",
        )

    def test_cents_padding(self):
        self.assertEqual(numtoletras("10.5"), "DIEZ CON 50/100 SOLES")
        self.assertEqual(numtoletras("10.05"), "DIEZ CON 05/100 SOLES")

    def test_invalid_falls_back_to_zero(self):
        self.assertEqual(numtoletras(None), "CERO CON 00/100 SOLES")
        self.assertEqual(numtoletras(""), "CERO CON 00/100 SOLES")
        self.assertEqual(numtoletras("nope"), "CERO CON 00/100 SOLES")

    def test_boleta_88_matches_xml_note_expectation(self):
        """The broken B001-3917 case: PayableAmount 88.00 must not say miles."""
        note = numtoletras(Decimal("88.00"))
        self.assertEqual(note, "OCHENTA Y OCHO CON 00/100 SOLES")
        self.assertFalse(note.startswith("OCHO MIL"))
