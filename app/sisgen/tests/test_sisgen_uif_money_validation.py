from django.test import SimpleTestCase

from sisgen.services.document_search_service import DocumentSearchService


class SisgenUifMoneyValidationTests(SimpleTestCase):
    def _empty_otorgante_rows(self):
        return [
            ("O", 0, "", "LUIS MIGUEL PACO CHOQUE", "N", "46514491"),
            ("O", None, None, "RUTH MERY HUAMANI RUDAS", "N", "47905169"),
        ]

    def test_no_contencioso_skips_monto_origen_errors(self):
        svc = DocumentSearchService()
        doc = {"kardex": "NC1-2026", "cod_ancert": "0215", "idtipkar": 2}
        svc._validate_uif_data(doc, uif_records=self._empty_otorgante_rows())
        self.assertEqual(svc.kardex_errors.get("NC1-2026", []), [])

    def test_testamento_skips_monto_origen_errors(self):
        svc = DocumentSearchService()
        doc = {"kardex": "T1-2026", "cod_ancert": "0215", "idtipkar": 5}
        svc._validate_uif_data(doc, uif_records=self._empty_otorgante_rows())
        self.assertEqual(svc.kardex_errors.get("T1-2026", []), [])

    def test_escritura_still_requires_monto_origen(self):
        svc = DocumentSearchService()
        doc = {"kardex": "K1-2026", "cod_ancert": "0215", "idtipkar": 1}
        svc._validate_uif_data(doc, uif_records=self._empty_otorgante_rows())
        errors = svc.kardex_errors.get("K1-2026", [])
        self.assertTrue(any("Monto inválido" in e for e in errors))
        self.assertTrue(any("origen de fondos" in e.lower() for e in errors))

    def test_vehicular_still_requires_monto_origen(self):
        svc = DocumentSearchService()
        doc = {"kardex": "A1-2026", "cod_ancert": "0215", "idtipkar": 3}
        svc._validate_uif_data(doc, uif_records=self._empty_otorgante_rows())
        errors = svc.kardex_errors.get("A1-2026", [])
        self.assertTrue(any("Monto inválido" in e for e in errors))
        self.assertTrue(any("origen de fondos" in e.lower() for e in errors))
