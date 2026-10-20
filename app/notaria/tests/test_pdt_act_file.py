from django.test import SimpleTestCase

from notaria.services.pdt_file_service import (
    format_act_line,
    php_str_pad,
    replace_string_pdt,
)


def _base_act(**overrides):
    row = {
        "idtipkar": 1,
        "numescritura": "12",
        "fechaescritura": "2026-04-15",
        "fechaconclusion": "20/04/2026",
        "actosunat": "01",
        "secuencial": 3,
        "idmon": 1,
        "importetrans": "15000.00",
        "tipocambio": None,
        "desacto": "COMPRA VENTA",
        "nminuta": "10/04/2026",
        "exhibiomp": "SI",
    }
    row.update(overrides)
    return row


class PdtActLineTests(SimpleTestCase):
    def test_actfilepdt_has_fourteen_fields(self):
        line = format_act_line(_base_act())
        self.assertEqual(len(line.split("|")), 14)

    def test_php_padding_matches_generate_file_act(self):
        line = format_act_line(_base_act())
        parts = line.split("|")
        self.assertEqual(parts[0], "1")
        self.assertEqual(parts[1], "   12")
        self.assertEqual(parts[2], "15/04/2026")
        self.assertEqual(parts[3], "20/04/2026")
        self.assertEqual(parts[4], "          ")
        self.assertEqual(parts[5], "01")
        self.assertEqual(parts[6], "3    ")
        self.assertEqual(parts[7], "2")
        self.assertEqual(len(parts[8]), 15)
        self.assertTrue(parts[8].startswith("15000.00"))
        self.assertEqual(len(parts[11]), 30)
        self.assertEqual(parts[12], "          ")
        self.assertEqual(parts[13], " ")

    def test_minuta_and_exhibio_only_for_php_arr_acts(self):
        with_minuta = format_act_line(_base_act(actosunat="04")).split("|")
        self.assertEqual(with_minuta[12], "10/04/2026")
        self.assertEqual(with_minuta[13], "1")

        without = format_act_line(_base_act(actosunat="01")).split("|")
        self.assertEqual(without[12].strip(), "")
        self.assertEqual(without[13], " ")

    def test_garantia_uses_legalization_date(self):
        parts = format_act_line(_base_act(idtipkar=4)).split("|")
        self.assertEqual(parts[0], "5")
        self.assertEqual(parts[2].strip(), "")
        self.assertEqual(parts[3].strip(), "")
        self.assertEqual(parts[4], "15/04/2026")

    def test_nombre_contrato_only_acto_14(self):
        named = format_act_line(_base_act(actosunat="14", desacto="OTROS ACTOS")).split("|")
        self.assertTrue(named[11].startswith("OTROS ACTOS"))
        other = format_act_line(_base_act(actosunat="01", desacto="OTROS ACTOS")).split("|")
        self.assertEqual(other[11].strip(), "")

    def test_currency_mapping_and_foreign_importe(self):
        soles = format_act_line(_base_act(idmon=1)).split("|")
        self.assertEqual(soles[7], "2")
        dollars = format_act_line(_base_act(idmon=2)).split("|")
        self.assertEqual(dollars[7], "1")
        foreign = format_act_line(
            _base_act(idmon=3, importetrans="100", tipocambio="3.5")
        ).split("|")
        self.assertEqual(foreign[7], "1")
        self.assertTrue(foreign[8].startswith("350.0"))

    def test_replace_string_pdt_matches_php(self):
        self.assertEqual(replace_string_pdt("Ñandú"), "Nand ")
        self.assertEqual(php_str_pad(12, 5, side="left"), "   12")
        self.assertEqual(php_str_pad(3, 5, side="right"), "3    ")
