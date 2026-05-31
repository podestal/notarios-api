from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from sisgen.services.sisgen_errors_service import collect_kardex_sisgen_errors


class SisgenErrorsServiceTests(SimpleTestCase):
    @patch("sisgen.services.sisgen_errors_service.DocumentSearchService")
    def test_collect_returns_sisgen_messages_only(self, mock_service_cls):
        service = MagicMock()
        mock_service_cls.return_value = service
        service._execute_batch_query.return_value = [{"kardex": "K2-2026", "idkardex": 99}]
        service._process_documents.return_value = [
            {
                "kardex": "K2-2026",
                "idkardex": 99,
                "errores": ["detallemediopago: moneda informada sin importe válido"],
                "observaciones": ["Falta código ANCERT"],
                "personas": ["EMPRESA SA (RUC: 20610484949): Falta información registral"],
                "uif_validation": {"has_errors": True, "errors": [{"error_description": "uif"}]},
                "pdt_validation": {"has_errors": True, "errors": ["pdt"]},
            }
        ]

        result = collect_kardex_sisgen_errors("K2-2026")

        self.assertEqual(result["error"], 0)
        self.assertEqual(result["kardex"], "K2-2026")
        self.assertEqual(result["idkardex"], "99")
        self.assertEqual(result["sisgen_error_count"], 1)
        self.assertEqual(result["sisgen_observaciones_count"], 1)
        self.assertEqual(result["sisgen_personas_count"], 1)
        self.assertNotIn("uif_validation", result)
        self.assertNotIn("pdt_validation", result)

    @patch("sisgen.services.sisgen_errors_service.DocumentSearchService")
    def test_collect_returns_none_when_kardex_missing(self, mock_service_cls):
        mock_service_cls.return_value._execute_batch_query.return_value = []
        self.assertIsNone(collect_kardex_sisgen_errors("MISSING"))
