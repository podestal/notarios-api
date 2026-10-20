from datetime import date, datetime

from django.test import SimpleTestCase

from notaria.services.pdt_dates import format_pdt_writing_date


class FormatPdtWritingDateTests(SimpleTestCase):
    def test_string_yyyy_mm_dd(self):
        self.assertEqual(format_pdt_writing_date("2026-04-01"), "2026-04-01")

    def test_string_dd_mm_yyyy(self):
        self.assertEqual(format_pdt_writing_date("01/04/2026"), "2026-04-01")

    def test_date_and_datetime(self):
        self.assertEqual(format_pdt_writing_date(date(2026, 4, 1)), "2026-04-01")
        self.assertEqual(
            format_pdt_writing_date(datetime(2026, 4, 1, 12, 30)),
            "2026-04-01",
        )

    def test_empty(self):
        self.assertIsNone(format_pdt_writing_date(None))
        self.assertIsNone(format_pdt_writing_date(""))
