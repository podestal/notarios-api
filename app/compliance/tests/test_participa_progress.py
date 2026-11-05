from django.test import SimpleTestCase

from compliance.services.participa_progress import evaluate_participa


def _eval(**overrides):
    base = dict(
        started=True,
        ofondo_gaps=[],
        monto_gaps=[],
        renta_required=True,
        question_gaps=[],
        formulario_gaps=[],
    )
    base.update(overrides)
    return evaluate_participa(**base)


class ParticipaProgressTests(SimpleTestCase):
    def test_not_started_is_idle(self):
        result = _eval(started=False, ofondo_gaps=["Ana"], question_gaps=["Ana"])
        self.assertEqual(result["status"], "idle")
        self.assertTrue(all(step["status"] == "idle" and step["issues"] == [] for step in result["steps"]))

    def test_missing_origen_and_monto(self):
        result = _eval(ofondo_gaps=["Ana"], monto_gaps=["Ana"])
        self.assertEqual(result["status"], "error")
        texts = [item["text"] for item in result["steps"][0]["issues"]]
        self.assertIn("Falta el origen de fondos de Ana", texts)
        self.assertIn("Monto inválido de Ana", texts)

    def test_renta_not_required_is_done(self):
        result = _eval(renta_required=False, question_gaps=["Ana"])
        self.assertEqual(result["steps"][1]["status"], "done")
        self.assertEqual(result["steps"][1]["issues"], [])
        self.assertEqual(result["status"], "done")

    def test_missing_formulario_when_impuesto_is_not_zero(self):
        result = _eval(formulario_gaps=["Ana"])
        self.assertEqual(result["steps"][1]["status"], "error")
        self.assertIn("formulario", result["steps"][1]["issues"][0]["text"])
        self.assertEqual(result["status"], "error")

    def test_complete(self):
        result = _eval()
        self.assertEqual(result["status"], "done")
        self.assertEqual(result["steps"][1]["status"], "done")
