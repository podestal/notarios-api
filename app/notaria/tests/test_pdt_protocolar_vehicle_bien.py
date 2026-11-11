from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from notaria.services.pdt_protocolar_mixin import fetch_bulk_protocolar_context


class VehicleBienContextTests(SimpleTestCase):
    @patch("notaria.services.pdt_protocolar_mixin.connection")
    def test_detallevehicular_counts_as_bien(self, _mock_connection):
        cursor = MagicMock()

        def execute(sql, params=None):
            sql_l = sql.lower()
            if "from detallebienes" in sql_l:
                cursor.fetchall.return_value = []
            elif "from detallemediopago" in sql_l:
                cursor.fetchall.return_value = []
            elif "from detallevehicular" in sql_l:
                cursor.fetchall.return_value = [
                    ("A346-2026", None, "094", "000499"),
                ]
            elif "from renta" in sql_l and "formulario" in sql_l:
                cursor.fetchall.return_value = []
            elif "from renta" in sql_l:
                cursor.fetchall.return_value = []
            elif "from contratantesxacto" in sql_l:
                cursor.fetchall.return_value = []
            else:
                cursor.fetchall.return_value = []

        cursor.execute.side_effect = execute
        ctx = fetch_bulk_protocolar_context(cursor, ["A346-2026"])
        self.assertIn(("A346-2026", "094"), ctx["bienes_by_acto"])
        self.assertIn(("A346-2026", "000499"), ctx["bienes_by_item"])
