from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from sisgen.services.send_preview_service import (
    extract_search_filters,
    verify_documents_against_filters,
)


class SendPreviewServiceTests(SimpleTestCase):
    def test_extract_search_filters_ignores_pagination(self):
        data = {
            "fechaDesde": "01/04/2026",
            "fechaHasta": "30/04/2026",
            "tipoInstrumento": 1,
            "estado": 0,
            "page": 2,
            "search_id": "x",
            "documents": [{"kardex": "K1"}],
        }
        filters = extract_search_filters(data)
        self.assertEqual(filters["fechaDesde"], "01/04/2026")
        self.assertNotIn("page", filters)
        self.assertNotIn("documents", filters)

    @patch("sisgen.services.send_preview_service.resolve_documents_from_filters")
    def test_verify_documents_against_filters(self, mock_resolve):
        mock_resolve.return_value = {
            "K2-2026": "99",
            "K3-2026": "100",
        }
        filters = {
            "fechaDesde": "01/04/2026",
            "fechaHasta": "30/04/2026",
            "tipoInstrumento": 1,
            "estado": 0,
        }
        docs = [
            {"kardex": "K2-2026", "idkardex": "99"},
            {"kardex": "K9-2026", "idkardex": "1"},
        ]
        normalized, invalid = verify_documents_against_filters(filters, docs)
        self.assertEqual(len(normalized), 1)
        self.assertEqual(normalized[0]["kardex"], "K2-2026")
        self.assertEqual(invalid, ["K9-2026"])
