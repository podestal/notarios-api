from django.test import SimpleTestCase

from compliance.services.kardex_list_progress import list_tone, score_stages


def _step(step_id, status="done", issues=None):
    return {"id": step_id, "status": status, "issues": issues or []}


def _stages(**overrides):
    base = dict(
        tipkar=1,
        contratantes={"status": "done", "issues": []},
        patrimonial={
            "status": "done",
            "steps": [
                _step("patrimonial"),
                _step("medio-pago"),
                _step("detalle-bien"),
            ],
        },
        participa={
            "status": "done",
            "steps": [_step("participa"), _step("preguntas-uif")],
        },
        instrumento={
            "status": "done",
            "steps": [_step("digitacion"), _step("escrituracion")],
        },
    )
    base.update(overrides)
    return score_stages(**base)


class ListToneTests(SimpleTestCase):
    def test_errors_cannot_reach_complete(self):
        self.assertEqual(list_tone(["done"] * 6, 1, 0), "incomplete")

    def test_warnings_stay_a_warning_when_stages_are_finished(self):
        self.assertEqual(list_tone(["done"] * 5 + ["warning"], 0, 2), "warning")

    def test_clean_is_complete(self):
        self.assertEqual(list_tone(["done"] * 6, 0, 0), "complete")

    def test_an_idle_stage_is_incomplete(self):
        self.assertEqual(list_tone(["done"] * 5 + ["idle"], 0, 1), "incomplete")


class ScoreStagesTests(SimpleTestCase):
    def test_finished_kardex_is_complete(self):
        self.assertEqual(_stages(), "complete")

    def test_contact_warnings_match_modal_warning_tone(self):
        self.assertEqual(
            _stages(
                contratantes={
                    "status": "warning",
                    "issues": [
                        {"level": "warning", "text": "Falta información de contacto"},
                        {"level": "warning", "text": "Falta información de contacto"},
                    ],
                }
            ),
            "warning",
        )

    def test_medio_error_is_incomplete(self):
        self.assertEqual(
            _stages(
                patrimonial={
                    "status": "error",
                    "steps": [
                        _step("patrimonial", "error"),
                        _step(
                            "medio-pago",
                            "error",
                            [{"level": "error", "text": "invalid medio"}],
                        ),
                        _step("detalle-bien"),
                    ],
                }
            ),
            "incomplete",
        )

    def test_idle_leaf_is_incomplete(self):
        self.assertEqual(
            _stages(
                instrumento={
                    "status": "idle",
                    "steps": [_step("digitacion", "idle"), _step("escrituracion", "idle")],
                }
            ),
            "incomplete",
        )

    def test_types_without_patrimonial_can_still_complete(self):
        self.assertEqual(
            _stages(tipkar=2, patrimonial=None, participa=None),
            "complete",
        )
