from unittest.mock import patch

from django.test import SimpleTestCase

from uif.services.reports import UifReportService


class ReportTransformTests(SimpleTestCase):
    def test_transform_uses_patrimonial_from_dashboard_record(self):
        service = UifReportService()
        record = {
            "kardex": "K1-2026",
            "idkardex": 1,
            "idtipkar": 1,
            "codacto": "094",
            "uif_code": "010",
            "numescritura": "100",
            "fechaescritura": "2026-04-15",
            "fechaconclusion": "15/04/2026",
            "tipo": "I",
            "tipo_moneda": "SOLES",
            "tipo_cambio": 3.75,
            "patrimonial": 150000,
        }
        row = service._transform_record_for_excel(record, row_index=1)
        self.assertEqual(row["item_51"], "150000.00")
        self.assertEqual(row["item_50"], "PEN")
        self.assertEqual(row["item_45"], "010")

    def test_plane_row_has_expected_width(self):
        service = UifReportService()
        specs = [
            type("Spec", (), {"number_of_data": 1, "column_length": 8})(),
            type("Spec", (), {"number_of_data": 2, "column_length": 8})(),
            type("Spec", (), {"number_of_data": 3, "column_length": 1})(),
        ]
        row_values = {"item_1": "1", "item_2": "1", "item_3": "I"}
        line = service._format_plane_row(row_values, specs)
        self.assertEqual(len(line), 17)

    def test_report_records_prefers_active_list(self):
        service = UifReportService()
        data = {
            "lista_kardex_ro": [{"kardex": "A"}],
            "lista_kardex_report_active": [{"kardex": "A"}, {"kardex": "B"}],
        }
        self.assertEqual(len(service._report_records(data)), 2)

    @patch.object(UifReportService, "_report_records", return_value=[{"kardex": "K1", "tipo": "I", "codacto": "094"}])
    @patch.object(UifReportService, "_add_excel_headers")
    @patch("uif.services.reports.PlaneRowBuilder")
    def test_excel_uses_report_records_not_only_clean_ro(
        self, mock_builder_cls, _headers, mock_records
    ):
        mock_builder_cls.return_value.build_rows.return_value = [
            {"kardex": "K1", "item_1": "1", "item_2": "1", "item_3": "I"}
        ]
        service = UifReportService()
        data = {"summary": {"date_range": {}}, "lista_kardex_ro": []}
        response = service.generate_excel_report(data, "01/04/2026", "30/04/2026")
        self.assertEqual(response.status_code, 200)
        mock_records.assert_called_once()
