from django.test import SimpleTestCase

from compliance.services.instrumento_progress import evaluate_instrumento


def _eval(**overrides):
    base = dict(
        digitized=False,
        escritura_started=False,
        missing_numero=True,
        missing_conclusion=True,
    )
    base.update(overrides)
    return evaluate_instrumento(**base)


class InstrumentoProgressTests(SimpleTestCase):
    def test_nothing_saved_is_idle_with_no_errors(self):
        result = _eval()
        self.assertEqual(result["steps"][0]["status"], "idle")
        self.assertEqual(result["steps"][0]["issues"], [])
        self.assertEqual(result["steps"][1]["status"], "idle")
        self.assertEqual(result["steps"][1]["issues"], [])

    def test_digitacion_done_never_has_issues(self):
        result = _eval(digitized=True)
        self.assertEqual(result["steps"][0]["status"], "done")
        self.assertEqual(result["steps"][0]["issues"], [])

    def test_escritura_started_without_number_or_conclusion(self):
        result = _eval(escritura_started=True)
        self.assertEqual(result["steps"][1]["status"], "error")
        texts = [item["text"] for item in result["steps"][1]["issues"]]
        self.assertIn("Número de escritura faltante", texts)
        self.assertIn("Falta concluir el instrumento con la firma de los contratantes", texts)

    def test_escritura_complete(self):
        result = _eval(escritura_started=True, missing_numero=False, missing_conclusion=False)
        self.assertEqual(result["steps"][1]["status"], "done")
        self.assertEqual(result["steps"][1]["issues"], [])
