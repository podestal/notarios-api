from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from compliance.services.contratantes_progress import (
    ContratantesProgressService,
    UIF_CONTRATANTE_FIELDS,
    local_contratante_issues,
)


def _issues(**overrides):
    base = dict(
        idcontratante="1",
        label="Perez Juan",
        tipper="N",
        prinom="Juan",
        apepat="Perez",
        razonsocial="",
        nombre="Perez Juan",
        numdoc="12345678",
        idtipdoc=1,
        idubigeo="150101",
        ubigeo_ok=True,
        has_condicion=True,
        has_cliente=True,
    )
    base.update(overrides)
    return local_contratante_issues(**base)


class LocalContratanteIssuesTests(SimpleTestCase):
    def test_complete_natural_person_has_no_issues(self):
        self.assertEqual(_issues(), [])

    def test_missing_name_ubigeo_and_condicion(self):
        fields = {item["field"] for item in _issues(
            prinom="",
            apepat="",
            ubigeo_ok=False,
            idubigeo="",
            has_condicion=False,
        )}
        self.assertIn("nombre", fields)
        self.assertIn("ubigeo", fields)
        self.assertIn("condicion", fields)

    def test_incorrect_dni(self):
        texts = [item["text"] for item in _issues(numdoc="12")]
        self.assertTrue(any("DNI no es correcto" in text for text in texts))

    def test_juridica_without_razon_social(self):
        texts = [item["text"] for item in _issues(
            tipper="J",
            label="Contratante 2",
            prinom="",
            apepat="",
            razonsocial="",
            numdoc="20123456789",
            idtipdoc=8,
        )]
        self.assertTrue(any("razón social" in text for text in texts))

    def test_bad_display_name(self):
        texts = [item["text"] for item in _issues(nombre="12")]
        self.assertTrue(any("no es correcto" in text for text in texts))


class ContratantesUifMappingTests(SimpleTestCase):
    def test_zona_and_partida_are_contratante_uif_fields(self):
        self.assertEqual(UIF_CONTRATANTE_FIELDS["missing_zona_registral"], "zona_registral")
        self.assertEqual(
            UIF_CONTRATANTE_FIELDS["missing_partida_registral"], "partida_registral"
        )

    @patch("compliance.services.contratantes_progress.collect_pdt_issues")
    @patch("compliance.services.contratantes_progress.collect_uif_issues")
    @patch(
        "compliance.services.sisgen_progress_gate.should_report_sisgen_issues",
        return_value=False,
    )
    def test_from_collectors_keeps_zona_partida(self, _gate, mock_uif, mock_pdt):
        mock_uif.return_value = {
            "errors": [
                {
                    "error_type": "missing_zona_registral",
                    "error_description": "LUMBA: zona registral requerida",
                    "idContratante": "0000001395",
                },
                {
                    "error_type": "missing_partida_registral",
                    "error_description": "LUMBA: número de partida registral requerido",
                    "idContratante": "0000001395",
                },
            ]
        }
        mock_pdt.return_value = {"errors": []}
        extra = ContratantesProgressService()._from_collectors(
            "A344-2026", [], kardex_row=MagicMock()
        )
        fields = {item["field"] for item in extra}
        self.assertEqual(fields, {"zona_registral", "partida_registral"})
        self.assertTrue(all(item["source"] == "uif" for item in extra))
