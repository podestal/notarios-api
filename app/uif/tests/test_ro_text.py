from django.test import SimpleTestCase

from uif.services.ro_text import remplace_string_ro


class RoTextNormalizationTests(SimpleTestCase):
    def test_strips_accents_to_ascii(self):
        self.assertEqual(remplace_string_ro("José"), "Jose")
        self.assertEqual(remplace_string_ro("ASOCIACIÓN"), "ASOCIACION")
        self.assertEqual(remplace_string_ro("GONZÁLEZ"), "GONZALEZ")

    def test_enye_becomes_hash(self):
        self.assertEqual(remplace_string_ro("MUÑOZ"), "MU#OZ")
        self.assertEqual(remplace_string_ro("SEÑOR"), "SE#OR")
        self.assertEqual(remplace_string_ro("Peña"), "Pe#a")

    def test_repairs_common_mojibake(self):
        self.assertEqual(remplace_string_ro("MUÃ‘OZ"), "MU#OZ")

    def test_type_person_three_keeps_punctuation_until_second_pass(self):
        raw = remplace_string_ro("S & V TRANSPORTES E.I.R.L.", 3)
        self.assertEqual(raw, "S & V TRANSPORTES E.I.R.L.")
        self.assertEqual(remplace_string_ro(raw, 1), "S  V TRANSPORTES EIRL")

    def test_strips_punctuation_for_natural_person(self):
        self.assertEqual(remplace_string_ro('ACME "TEST" (S.A.)', 1), "ACME TEST SA")

    def test_strips_apostrophes_in_names(self):
        self.assertEqual(remplace_string_ro("d'añari", 1), "da#ari")
        self.assertEqual(remplace_string_ro("D'AÑARI", 1), "DA#ARI")
        self.assertEqual(remplace_string_ro("O'BRIEN", 1), "OBRIEN")
        self.assertEqual(remplace_string_ro("d\u2019añari", 1), "da#ari")
