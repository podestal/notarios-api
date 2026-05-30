import json
import os
import unittest

from django.test import TestCase

from uif.services.parity import (
    ParityManifest,
    build_python_parity_bundle,
    compare_plane_lines,
    error_signature,
    normalize_errors_for_compare,
    normalize_plane_text,
    resolve_fixture_dir,
    validate_plane_structure,
)


@unittest.skipUnless(
    resolve_fixture_dir() is not None,
    "Add app/uif/tests/fixtures/php_parity/<period>/manifest.json + plane.php.txt",
)
class PhpParityIntegrationTests(TestCase):
    """Compare Python UIF output to legacy PHP golden files for one real period."""

    databases = {"default"}

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        period = os.environ.get("UIF_PARITY_PERIOD")
        cls.fixture_dir = resolve_fixture_dir(period)
        cls.manifest = ParityManifest.load(cls.fixture_dir / "manifest.json")
        cls.php_plane_lines = normalize_plane_text(
            (cls.fixture_dir / "plane.php.txt").read_text(encoding="utf-8", errors="replace")
        )

    def test_python_plane_structure(self):
        bundle = build_python_parity_bundle(
            self.manifest.initial_date,
            self.manifest.final_date,
            report_policy=self.manifest.report_policy,
        )
        issues = validate_plane_structure(bundle["plane_lines"])
        self.assertEqual(issues, [], msg=f"Python plane structure: {issues}")

    def test_plane_matches_php_golden(self):
        bundle = build_python_parity_bundle(
            self.manifest.initial_date,
            self.manifest.final_date,
            report_policy=self.manifest.report_policy,
        )
        diff = compare_plane_lines(bundle["plane_lines"], self.php_plane_lines)
        if diff["match"]:
            return

        msg = (
            f"Plane mismatch at line {diff['first_diff_index']}: "
            f"python={diff.get('python_sample')!r} php={diff.get('php_sample')!r} "
            f"(counts python={diff['python_line_count']} php={diff['php_line_count']})"
        )
        self.fail(msg)

    def test_summary_counts_match_php_when_golden_present(self):
        summary_path = self.fixture_dir / "summary.php.json"
        if not summary_path.is_file():
            self.skipTest("summary.php.json not provided")

        php_summary = json.loads(summary_path.read_text(encoding="utf-8"))
        bundle = build_python_parity_bundle(
            self.manifest.initial_date,
            self.manifest.final_date,
            report_policy=self.manifest.report_policy,
        )
        py_summary = bundle["summary"]

        for key in (
            "total_kardex",
            "total_errors",
            "total_report_ro",
            "total_no_envian",
        ):
            if key in php_summary:
                self.assertEqual(
                    py_summary.get(key),
                    php_summary[key],
                    msg=f"summary.{key}",
                )

    def test_errors_match_php_when_golden_present(self):
        errors_path = self.fixture_dir / "errors.php.json"
        if not errors_path.is_file():
            self.skipTest("errors.php.json not provided")

        php_errors = json.loads(errors_path.read_text(encoding="utf-8"))
        bundle = build_python_parity_bundle(
            self.manifest.initial_date,
            self.manifest.final_date,
            report_policy=self.manifest.report_policy,
        )
        py_sigs = normalize_errors_for_compare(bundle["errors"])
        php_sigs = normalize_errors_for_compare(php_errors)

        if py_sigs == php_sigs:
            return

        only_py = set(py_sigs) - set(php_sigs)
        only_php = set(php_sigs) - set(py_sigs)
        self.fail(
            f"Error set mismatch: only_python={len(only_py)} only_php={len(only_php)} "
            f"sample_py={list(only_py)[:3]} sample_php={list(only_php)[:3]}"
        )


class PhpParityHelperTests(unittest.TestCase):
    def test_compare_plane_lines_reports_first_diff(self):
        diff = compare_plane_lines(["H", "A"], ["H", "B"])
        self.assertFalse(diff["match"])
        self.assertEqual(diff["first_diff_index"], 1)

    def test_error_signature_stable(self):
        sig = error_signature(
            {
                "kardex": "K1",
                "codacto": "094",
                "fieldNumber": 52,
                "error_type": "invalid_monto_participante",
                "idContratante": "1",
            }
        )
        self.assertEqual(sig[2], 52)
