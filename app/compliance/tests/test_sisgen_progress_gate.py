from types import SimpleNamespace

from django.test import SimpleTestCase

from compliance.services.sisgen_progress_gate import should_report_sisgen_issues


class SisgenProgressGateTests(SimpleTestCase):
    def test_sent_kardex_does_not_report_sisgen(self):
        row = SimpleNamespace(estado_sisgen="1", numescritura="100")
        self.assertFalse(should_report_sisgen_issues(row))

    def test_pending_escrituracion_does_not_report_sisgen(self):
        row = SimpleNamespace(estado_sisgen="0", numescritura="")
        self.assertFalse(should_report_sisgen_issues(row))

    def test_open_kardex_with_instrumento_reports_sisgen(self):
        row = SimpleNamespace(estado_sisgen="0", numescritura="100")
        self.assertTrue(should_report_sisgen_issues(row))
