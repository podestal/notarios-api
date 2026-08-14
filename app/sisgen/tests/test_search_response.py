from django.test import SimpleTestCase

from sisgen.services.search_response import (
    count_sisgen_errors,
    count_sisgen_observaciones,
    count_sisgen_personas,
    slim_search_document_row,
    slim_search_pagination,
    slim_sisgen_last_submission,
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

    def test_slim_document_row_keeps_only_ui_fields(self):
        row = {
            "kardex": "K2-2026",
            "idkardex": "99",
            "contrato": "ACTO",
            "estado_sisgen": "Pendiente",
            "idtipkar": 1,
            "numescritura": "1234",
            "fechaescritura": "06/08/2026",
            "fechaingreso": "01/08/2026",
            "fechaconclusion": "15/04/2026",
            "notary_data": {"codnotario": "x"},
            "errores": ["e1"],
            "observaciones": ["warn"],
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
                "errors": [{"error_description": "Medio inválido"}],
            },
            "pdt_validation": {"has_errors": True, "errors": ["pdt"]},
        }

        slim = slim_search_document_row(row)

        self.assertEqual(
            set(slim.keys()),
            {
                "kardex",
                "idkardex",
                "numero_instrumento",
                "fecha_escritura",
                "contrato",
                "estado_sisgen",
                "idtipkar",
                "sisgen_error_count",
                "sisgen_observaciones_count",
                "sisgen_personas_count",
                "sisgen_status",
                "sisgen_last_submission",
            },
        )
        self.assertEqual(slim["numero_instrumento"], "1234")
        self.assertEqual(slim["fecha_escritura"], "06/08/2026")
        self.assertNotIn("fecha_ingreso", slim)
        self.assertNotIn("fecha_conclusion", slim)
        self.assertEqual(slim["sisgen_error_count"], 1)
        self.assertEqual(slim["sisgen_observaciones_count"], 1)
        self.assertEqual(slim["sisgen_personas_count"], 1)
        self.assertNotIn("errores", slim)
        self.assertNotIn("uif_validation", slim)
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

    def test_sisgen_counts_are_per_bucket(self):
        row = {
            "errores": ["sisgen doc error"],
            "observaciones": ["warning only"],
            "personas": ["person error"],
        }
        self.assertEqual(count_sisgen_errors(row), 1)
        self.assertEqual(count_sisgen_observaciones(row), 1)
        self.assertEqual(count_sisgen_personas(row), 1)
