from django.test import SimpleTestCase

from compliance.services.patrimonial_progress import evaluate_patrimonial


def _eval(**overrides):
    base = dict(
        started=True,
        cuantia_required=True,
        medios_required=True,
        bien_required=True,
        exhibe_medios=True,
        missing_moneda=False,
        missing_monto=False,
        missing_fpago=False,
        missing_oportunidad=False,
        has_medio_rows=True,
        medio_sin_tipo=False,
        medio_sin_monto=False,
        has_valid_bien=True,
        bien_incompleto=False,
    )
    base.update(overrides)
    return evaluate_patrimonial(**base)


class PatrimonialProgressTests(SimpleTestCase):
    def test_not_started_is_idle(self):
        result = _eval(started=False, has_medio_rows=False, has_valid_bien=False)
        self.assertEqual(result["status"], "idle")
        self.assertTrue(all(step["status"] == "idle" for step in result["steps"]))
        self.assertTrue(all(step["issues"] == [] for step in result["steps"]))

    def test_started_without_cuantia_and_medio(self):
        result = _eval(missing_moneda=True, missing_monto=True, has_medio_rows=False)
        self.assertEqual(result["status"], "error")
        fields = {item["field"] for item in result["steps"][0]["issues"]}
        self.assertIn("moneda", fields)
        self.assertIn("cuantia", fields)
        self.assertEqual(result["steps"][1]["status"], "error")

    def test_medios_not_required_stay_idle(self):
        result = _eval(medios_required=False, has_medio_rows=False, exhibe_medios=False)
        self.assertEqual(result["steps"][1]["status"], "idle")
        self.assertEqual(result["status"], "done")

    def test_cuantia_not_required_does_not_flag_empty_amounts(self):
        result = _eval(
            cuantia_required=False,
            missing_moneda=True,
            missing_monto=True,
            missing_fpago=True,
            missing_oportunidad=True,
        )
        self.assertEqual(result["steps"][0]["issues"], [])
        self.assertEqual(result["status"], "done")

    def test_incomplete_bien(self):
        result = _eval(has_valid_bien=False, bien_incompleto=True)
        self.assertEqual(result["steps"][2]["status"], "error")
        self.assertIn("tipo de bien", result["steps"][2]["issues"][0]["text"])
