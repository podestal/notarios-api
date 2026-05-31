from django.test import SimpleTestCase

from sisgen.services.search_response import (
    count_sisgen_errors,
    slim_search_document_row,
    slim_search_pagination,
    slim_sisgen_last_submission,
    slim_uif_validation,
)


class SearchResponseSlimTests(SimpleTestCase):
    def test_slim_pagination_keeps_only_ui_fields(self):
        slim = slim_search_pagination(
            {
                "search_id": "abc",
                "total_documents": 42,
                "current_page": 2,
                "has_next": True,
            }
        )
        self.assertEqual(slim, {"search_id": "abc", "total_documents": 42})

    def test_slim_document_row_drops_unused_metadata(self):
        row = {
            "kardex": "K2-2026",
            "idkardex": "99",
            "contrato": "ACTO",
            "estado_sisgen": "Pendiente",
            "idtipkar": 1,
            "numescritura": "1234",
            "notary_data": {"codnotario": "x"},
            "errores": ["e1"],
            "observaciones": [],
            "personas": ["p1"],
            "sisgen_status": {
                "status_ui": "pendiente",
                "needs_resubmit": False,
                "can_send": True,
                "estado_sisgen_label": "Pendiente",
                "estado_sisgen_code": 0,
                "submission_stale": False,
                "last_submission": {"exists": False},
            },
            "sisgen_last_submission": {
                "exists": False,
                "status_ui": "pendiente",
                "can_send": True,
            },
            "uif_validation": {
                "has_errors": True,
                "errors": [
                    {
                        "error_type": "invalid_medio_pago_codigo",
                        "error_description": "Medio inválido",
                        "field_number": 44,
                    }
                ],
                "observations": ["obs"],
                "patrimonial_data": {"119": {"importetrans": "100"}},
            },
            "pdt_validation": {"has_errors": False, "errors": []},
        }

        slim = slim_search_document_row(row)

        self.assertEqual(set(slim.keys()), {
            "kardex",
            "idkardex",
            "contrato",
            "estado_sisgen",
            "idtipkar",
            "sisgen_error_count",
            "errores",
            "observaciones",
            "personas",
            "sisgen_status",
            "sisgen_last_submission",
            "uif_validation",
            "pdt_validation",
        })
        self.assertEqual(slim["sisgen_error_count"], 2)
        self.assertNotIn("numescritura", slim)
        self.assertEqual(
            slim["uif_validation"]["errors"],
            [{"error_description": "Medio inválido"}],
        )
        self.assertNotIn("patrimonial_data", slim["uif_validation"])
        self.assertEqual(slim["sisgen_last_submission"], {"exists": False})

    def test_slim_last_submission_when_exists(self):
        slim = slim_sisgen_last_submission(
            {
                "exists": True,
                "status_ui": "fallido",
                "errors": ["SOAP error"],
                "created_at": "2026-01-01",
            }
        )
        self.assertEqual(
            slim,
            {"exists": True, "status_ui": "fallido", "errors": ["SOAP error"]},
        )

    def test_slim_uif_validation_skips_empty_descriptions(self):
        slim = slim_uif_validation(
            {
                "has_errors": True,
                "errors": [{"error_type": "x"}, "plain"],
                "observations": [],
            }
        )
        self.assertEqual(
            slim["errors"],
            [{"error_description": "plain"}],
        )

    def test_sisgen_error_count_excludes_uif_pdt_and_observaciones(self):
        row = {
            "errores": ["sisgen doc error"],
            "observaciones": ["warning only"],
            "personas": ["person error"],
            "uif_validation": {
                "has_errors": True,
                "errors": [{"error_description": "uif"}],
            },
            "pdt_validation": {"has_errors": True, "errors": ["pdt"]},
        }
        self.assertEqual(count_sisgen_errors(row), 2)
