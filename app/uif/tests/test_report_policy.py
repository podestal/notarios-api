from django.test import SimpleTestCase

from uif.services.report_data import (
    normalize_report_policy,
    select_report_records,
)


class ReportPolicyTests(SimpleTestCase):
    def test_normalize_policy_aliases(self):
        self.assertEqual(normalize_report_policy(None), "all")
        self.assertEqual(normalize_report_policy("legacy"), "all")
        self.assertEqual(normalize_report_policy("php"), "all")
        self.assertEqual(normalize_report_policy("clean"), "clean")
        self.assertEqual(normalize_report_policy("valid"), "clean")

    def test_select_all_includes_records_with_errors(self):
        payload = {
            "lista_kardex_ro": [{"kardex": "K-clean"}],
            "lista_kardex_report": [
                {"kardex": "K-clean", "has_validation_errors": False},
                {"kardex": "K-err", "has_validation_errors": True},
            ],
        }
        all_records = select_report_records(payload, "all")
        clean_records = select_report_records(payload, "clean")
        self.assertEqual(len(all_records), 2)
        self.assertEqual(len(clean_records), 1)
        self.assertEqual(clean_records[0]["kardex"], "K-clean")
