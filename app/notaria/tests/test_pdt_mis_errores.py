from datetime import date
from unittest import mock

from django.test import SimpleTestCase

from notaria.services.pdt_mis_errores_service import (
    parse_year,
    urgency_for_writing_date,
)


class PdtMisErroresHelpersTests(SimpleTestCase):
    def test_parse_year_defaults_and_clamps(self):
        current = date.today().year
        self.assertEqual(parse_year(None), current)
        self.assertEqual(parse_year("1999"), current)
        self.assertEqual(parse_year("abc"), current)
        self.assertEqual(parse_year("2024"), 2024)

    def test_urgency_windows_match_legacy_js(self):
        today = date(2026, 10, 20)
        self.assertEqual(
            urgency_for_writing_date("2026-09-01", today=today)["tone"],
            "red",
        )
        self.assertEqual(
            urgency_for_writing_date("2026-10-02", today=today)["label"],
            "TE QUEDAN 2 dias",
        )
        self.assertEqual(
            urgency_for_writing_date("2026-10-10", today=today)["tone"],
            "green",
        )
        self.assertEqual(
            urgency_for_writing_date("2026-09-30", today=today)["tone"],
            "tomato",
        )

    @mock.patch("notaria.services.pdt_mis_errores_service.connection")
    def test_list_errors_maps_php_payload(self, mock_connection):
        from notaria.services.pdt_mis_errores_service import list_errors_for_user

        cursor = mock.MagicMock()
        mock_connection.cursor.return_value.__enter__.return_value = cursor

        def execute_side_effect(sql, params=None):
            sql_l = sql.lower()
            if "renta" in sql_l and "pregu1" in sql_l:
                cursor.description = [
                    ("id_kardex",),
                    ("kardex_esc",),
                    ("acto",),
                    ("responsable",),
                    ("fechaescritura",),
                    ("contratante",),
                ]
                cursor.fetchall.return_value = [
                    (10, "K10-2026", "COMPRA/VENTA", "jperez", "2026-10-01", "ANA RUIZ")
                ]
            elif "detallebienes" in sql_l:
                cursor.description = [
                    ("id_kardex",),
                    ("kardex_esc",),
                    ("acto",),
                    ("responsable",),
                    ("fechaescritura",),
                ]
                cursor.fetchall.return_value = [
                    (11, "K11-2026", "DONACION", "jperez", "2026-10-01")
                ]
            elif "ofondo" in sql_l:
                cursor.description = [
                    ("id_kardex",),
                    ("kardex_esc",),
                    ("acto",),
                    ("responsable",),
                    ("fechaescritura",),
                    ("contratante",),
                ]
                cursor.fetchall.return_value = []
            else:
                cursor.description = [
                    ("id_kardex",),
                    ("kardex_esc",),
                    ("acto",),
                    ("responsable",),
                    ("fechaescritura",),
                ]
                cursor.fetchall.return_value = []

        cursor.execute.side_effect = execute_side_effect
        out = list_errors_for_user("jperez", 2026)
        self.assertEqual(out["counts"]["renta"], 1)
        self.assertEqual(out["counts"]["bien"], 1)
        self.assertIn("Ingrese renta de tercera categoria", out["renta"][0]["error"])
        self.assertEqual(out["bien"][0]["error"], "No existe bien, ingrese un bien")
        self.assertEqual(out["renta"][0]["contrato"], "COMPRAVENTA")
        self.assertEqual(out["total"], 2)

    def test_count_errors_by_kardex_empty(self):
        from notaria.services.pdt_mis_errores_service import count_errors_by_kardex

        self.assertEqual(count_errors_by_kardex([]), {})

    @mock.patch("notaria.services.pdt_mis_errores_service.connection")
    def test_list_errors_for_kardex_maps_php_messages(self, mock_connection):
        from notaria.services.pdt_mis_errores_service import list_errors_for_kardex

        cursor = mock.MagicMock()
        mock_connection.cursor.return_value.__enter__.return_value = cursor

        def execute_side_effect(sql, params=None):
            sql_l = sql.lower()
            if "renta" in sql_l and "pregu1" in sql_l:
                cursor.description = [
                    ("id_kardex",),
                    ("kardex_esc",),
                    ("acto",),
                    ("responsable",),
                    ("fechaescritura",),
                    ("contratante",),
                ]
                cursor.fetchall.return_value = [
                    (10, "K10-2026", "COMPRA/VENTA", "jperez", "2026-10-01", "ANA RUIZ")
                ]
            else:
                cursor.description = [
                    ("id_kardex",),
                    ("kardex_esc",),
                    ("acto",),
                    ("responsable",),
                    ("fechaescritura",),
                ]
                cursor.fetchall.return_value = []

        cursor.execute.side_effect = execute_side_effect
        items = list_errors_for_kardex("K10-2026")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["kind"], "renta")
        self.assertIn("Ingrese renta de tercera categoria", items[0]["error_description"])
        self.assertEqual(items[0]["kardex"], "K10-2026")
