from django.test import SimpleTestCase

from uif.services.ro_text import remplace_string_ro


class RoTextNormalizationTests(SimpleTestCase):
    def test_preserves_tildes_and_enye(self):
        self.assertEqual(remplace_string_ro("ASOCIACIÓN"), "ASOCIACIÓN")
        self.assertEqual(remplace_string_ro("SEÑOR"), "SEÑOR")

    def test_repairs_common_mojibake_for_accents(self):
        self.assertEqual(remplace_string_ro("MUÃ‘OZ"), "MUÑOZ")
