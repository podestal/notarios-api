from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from compliance.services.patrimonial_progress import (
    _merge_collectors,
    count_invalid_medio_pago_codigo,
    evaluate_patrimonial,
)


def _eval(**overrides):
    base = dict(
        started=True,
        medios_required=True,
        bien_required=True,
        exhibe_medios=True,
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

    def test_started_without_medio_is_error(self):
        result = _eval(has_medio_rows=False)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["steps"][1]["status"], "error")
        self.assertEqual(result["steps"][0]["issues"], [])

    def test_cuantia_gaps_are_not_invented_locally(self):
        """Empty oportunidad / forma / moneda stay clean until UIF or SISGEN say so."""
        result = _eval()
        self.assertEqual(result["steps"][0]["issues"], [])
        self.assertEqual(result["status"], "done")

    def test_medios_not_required_are_done(self):
        result = _eval(medios_required=False, has_medio_rows=False, exhibe_medios=False)
        self.assertEqual(result["steps"][1]["status"], "done")
        self.assertEqual(result["status"], "done")

    def test_bien_not_required_is_done(self):
        result = _eval(bien_required=False, has_valid_bien=False)
        self.assertEqual(result["steps"][2]["status"], "done")
        self.assertEqual(result["steps"][2]["issues"], [])

    def test_incomplete_bien(self):
        result = _eval(has_valid_bien=False, bien_incompleto=True)
        self.assertEqual(result["steps"][2]["status"], "error")
        self.assertIn("tipo de bien", result["steps"][2]["issues"][0]["text"])


class PatrimonialPdtMergeTests(SimpleTestCase):
    @patch(
        "compliance.services.sisgen_progress_gate.should_report_sisgen_issues",
        return_value=False,
    )
    @patch("compliance.services.uif_collector.collect_uif_issues")
    @patch("compliance.services.pdt_collector.collect_pdt_issues")
    def test_medio_pago_pdt_lands_on_medio_pago_step(self, mock_pdt, mock_uif, _gate):
        mock_uif.return_value = {"errors": []}
        mock_pdt.return_value = {
            "errors": [
                {
                    "kind": "medio_pago",
                    "error": "Ingrese documentos del medio de pago.",
                }
            ]
        }
        result = evaluate_patrimonial(
            started=True,
            medios_required=True,
            bien_required=False,
            exhibe_medios=True,
            has_medio_rows=True,
            medio_sin_tipo=False,
            medio_sin_monto=False,
            has_valid_bien=False,
            bien_incompleto=False,
        )
        merged = _merge_collectors("K155-2026", result, kardex_row=SimpleNamespace())
        medio = next(step for step in merged["steps"] if step["id"] == "medio-pago")
        self.assertEqual(medio["status"], "error")
        self.assertTrue(
            any("documentos del medio de pago" in i["text"] for i in medio["issues"])
        )


class InvalidMedioPagoCodigoTests(SimpleTestCase):
    def test_vacio_catalog_code_is_invalid_when_rule_rejects_v(self):
        rule = SimpleNamespace(data_value="01|02|03|04|05|06|07|08|99")
        rules = SimpleNamespace(get=lambda code, field: rule)
        count = count_invalid_medio_pago_codigo(
            tipos=[SimpleNamespace(idtipoacto="096", actouif="016")],
            medios=[SimpleNamespace(tipacto="096", codmepag=97)],
            medios_uif_by_code={97: ""},
            rules=rules,
        )
        self.assertEqual(count, 1)

    def test_valid_transfer_code_passes(self):
        rule = SimpleNamespace(data_value="01|02|03|04|05|06|07|08|99")
        rules = SimpleNamespace(get=lambda code, field: rule)
        count = count_invalid_medio_pago_codigo(
            tipos=[SimpleNamespace(idtipoacto="096", actouif="016")],
            medios=[SimpleNamespace(tipacto="096", codmepag=3)],
            medios_uif_by_code={3: "04"},
            rules=rules,
        )
        self.assertEqual(count, 0)
