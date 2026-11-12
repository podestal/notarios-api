from django.test import SimpleTestCase

from sisgen.services.instrumento_stats import build_instrumento_stats, parse_instrumento_int


class InstrumentoStatsTests(SimpleTestCase):
    def test_parse_instrumento_int(self):
        self.assertEqual(parse_instrumento_int("03"), 3)
        self.assertEqual(parse_instrumento_int(" 12 "), 12)
        self.assertIsNone(parse_instrumento_int(""))
        self.assertIsNone(parse_instrumento_int("abc"))

    def test_correlative_ok(self):
        docs = [
            {"kardex": "A1", "numero_instrumento": "10"},
            {"kardex": "A2", "numero_instrumento": "11"},
            {"kardex": "A3", "numero_instrumento": "12"},
            {"kardex": "A4", "numero_instrumento": "13"},
            {"kardex": "A5", "numero_instrumento": "14"},
        ]
        stats = build_instrumento_stats(docs)
        self.assertEqual(stats["kardex_count"], 5)
        self.assertEqual(stats["instrumento_first"], 10)
        self.assertEqual(stats["instrumento_last"], 14)
        self.assertEqual(stats["instrumento_expected"], 5)
        self.assertTrue(stats["correlative_ok"])
        self.assertEqual(stats["gaps"], [])

    def test_gap_fails(self):
        docs = [
            {"kardex": "A1", "numero_instrumento": "1"},
            {"kardex": "A2", "numero_instrumento": "2"},
            {"kardex": "A3", "numero_instrumento": "3"},
            {"kardex": "A4", "numero_instrumento": "5"},
            {"kardex": "A5", "numero_instrumento": "6"},
        ]
        stats = build_instrumento_stats(docs)
        self.assertEqual(stats["instrumento_first"], 1)
        self.assertEqual(stats["instrumento_last"], 6)
        self.assertEqual(stats["instrumento_expected"], 6)
        self.assertEqual(stats["gaps"], [4])
        self.assertFalse(stats["correlative_ok"])

    def test_missing_and_duplicate_fail(self):
        docs = [
            {"kardex": "A1", "numero_instrumento": "1"},
            {"kardex": "A2", "numero_instrumento": ""},
            {"kardex": "A3", "numero_instrumento": "1"},
        ]
        stats = build_instrumento_stats(docs)
        self.assertEqual(stats["missing_instrumento"], 1)
        self.assertEqual(stats["duplicates"], [1])
        self.assertFalse(stats["correlative_ok"])
