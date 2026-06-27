from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from compliance.services.user_monthly_service import (
    ComplianceUserMonthlyService,
    parse_year_month,
)


class ParseYearMonthTests(SimpleTestCase):
    def test_explicit_month(self):
        y, m, start, end = parse_year_month(2026, 6)
        self.assertEqual((y, m), (2026, 6))
        self.assertEqual(start.isoformat(), "2026-06-01")
        self.assertEqual(end.isoformat(), "2026-06-30")

    def test_invalid_month(self):
        with self.assertRaises(ValueError):
            parse_year_month(2026, 13)


class ComplianceUserMonthlyServiceTests(SimpleTestCase):
    def _kardex_models(self):
        return [
            MagicMock(kardex="K1-2026", idusuario=3, idkardex="1"),
            MagicMock(kardex="K2-2026", idusuario=3, idkardex="2"),
            MagicMock(kardex="K3-2026", idusuario=5, idkardex="3"),
        ]

    @patch("compliance.services.user_monthly_service.get_user_model")
    @patch("compliance.services.user_monthly_service.bulk_collect_compliance_error_counts")
    @patch("compliance.services.user_monthly_service.models.Kardex")
    def test_live_default_aggregates_counts_by_user(
        self, mock_kardex_model, mock_bulk, mock_get_user_model
    ):
        mock_kardex_model.objects.filter.return_value.exclude.return_value.exclude.return_value.exclude.return_value = (
            self._kardex_models()
        )
        mock_bulk.return_value = {
            "K1-2026": {"sisgen": 2, "uif": 1},
            "K2-2026": {"sisgen": 0, "uif": 0},
            "K3-2026": {"sisgen": 1, "uif": 2},
        }
        user3 = MagicMock(idusuario=3, first_name="Ana", last_name="Lopez", username="ana")
        user5 = MagicMock(idusuario=5, first_name="Bob", last_name="", username="bob")
        mock_get_user_model.return_value.filter.return_value = [user3, user5]

        report = ComplianceUserMonthlyService().build_report(year=2026, month=6)

        self.assertEqual(report["source"]["source"], "live_validation")
        self.assertEqual(report["summary"]["total_kardex"], 3)
        self.assertEqual(len(report["users"]), 2)
        top = report["users"][0]
        self.assertEqual(top["idusuario"], 5)
        self.assertEqual(top["counts"]["total"], 3)

        user3_row = next(u for u in report["users"] if u["idusuario"] == 3)
        self.assertEqual(user3_row["counts"]["sisgen"], 2)
        self.assertEqual(user3_row["counts"]["uif"], 1)
        self.assertEqual(user3_row["counts"]["total"], 3)
        mock_bulk.assert_called_once()

    @patch("compliance.services.user_monthly_service.get_user_model")
    @patch("compliance.services.user_monthly_service.KardexComplianceCache")
    @patch("compliance.services.user_monthly_service.models.Kardex")
    def test_cache_mode_reads_compliance_cache(
        self, mock_kardex_model, mock_cache_model, mock_get_user_model
    ):
        mock_kardex_model.objects.filter.return_value.exclude.return_value.exclude.return_value.exclude.return_value = (
            self._kardex_models()
        )
        cache_k1 = MagicMock(
            kardex="K1-2026",
            uif_error_count=1,
            payload={"sources": {"sisgen": {"errores": ["a", "b"]}}},
        )
        mock_cache_model.objects.filter.return_value.only.return_value = [cache_k1]
        mock_get_user_model.return_value.filter.return_value = []

        report = ComplianceUserMonthlyService().build_report(
            year=2026, month=6, use_cache=True
        )

        self.assertEqual(report["source"]["source"], "kardex_compliance_cache")
        self.assertEqual(report["source"]["cached"], 1)
        self.assertEqual(report["source"]["missing"], 2)


class ComplianceUserKardexReportTests(SimpleTestCase):
    @patch("compliance.services.user_monthly_service._load_month_kardex_and_counts")
    def test_build_user_kardex_report_errors_only(self, mock_load):
        mock_load.return_value = {
            "year": 2026,
            "month": 6,
            "period": {"start": "2026-06-01", "end": "2026-06-30", "date_field": "fechaingreso"},
            "source_meta": {"source": "live_validation", "excluded_sisgen_sent": 1},
            "users_by_id": {3: MagicMock(first_name="Ana", last_name="L", username="ana")},
            "all_kardex_rows": [
                {
                    "kardex": "K1",
                    "idkardex": "1",
                    "idusuario": 3,
                    "numescritura": "10",
                    "fechaingreso": "2026-06-05",
                    "fechaescritura": "2026-06-10",
                    "idtipkar": 1,
                },
                {
                    "kardex": "K2",
                    "idkardex": "2",
                    "idusuario": 3,
                    "numescritura": "11",
                    "fechaingreso": "2026-06-06",
                    "fechaescritura": "2026-06-11",
                    "idtipkar": 1,
                },
                {
                    "kardex": "K-SENT",
                    "idkardex": "3",
                    "idusuario": 3,
                    "numescritura": "12",
                    "fechaingreso": "2026-06-07",
                    "fechaescritura": "2026-06-12",
                    "idtipkar": 1,
                },
            ],
            "eligible_kardex_rows": [
                {
                    "kardex": "K1",
                    "idkardex": "1",
                    "idusuario": 3,
                    "numescritura": "10",
                    "fechaingreso": "2026-06-05",
                    "fechaescritura": "2026-06-10",
                    "idtipkar": 1,
                },
                {
                    "kardex": "K2",
                    "idkardex": "2",
                    "idusuario": 3,
                    "numescritura": "11",
                    "fechaingreso": "2026-06-06",
                    "fechaescritura": "2026-06-11",
                    "idtipkar": 1,
                },
            ],
            "kardex_rows": [],
            "counts_by_kardex": {
                "K1": {"sisgen": 2, "uif": 1},
                "K2": {"sisgen": 0, "uif": 0},
            },
        }

        report = ComplianceUserMonthlyService().build_user_kardex_report(
            year=2026, month=6, errors_only=True
        )

        self.assertEqual(len(report["users"]), 1)
        self.assertEqual(report["users"][0]["total_kardex"], 3)
        self.assertEqual(report["users"][0]["kardex_with_errors"], 1)
        self.assertEqual(report["users"][0]["error_rate"], round(1 / 3, 4))
        self.assertEqual(report["users"][0]["kardex_count"], 1)
        self.assertEqual(report["users"][0]["kardex"][0]["kardex"], "K1")
        self.assertEqual(report["users"][0]["kardex"][0]["counts"]["total"], 3)
        self.assertEqual(report["summary"]["total_kardex"], 3)
        self.assertEqual(report["summary"]["kardex_with_errors"], 1)


class ComplianceUserMonthlyTotalsTests(SimpleTestCase):
    @patch("compliance.services.user_monthly_service._load_month_kardex_and_counts")
    @patch("compliance.services.user_monthly_service.get_user_model")
    def test_total_kardex_includes_sisgen_sent(self, mock_get_user_model, mock_load):
        mock_load.return_value = {
            "year": 2026,
            "month": 6,
            "period": {},
            "source_meta": {"excluded_sisgen_sent": 1},
            "users_by_id": {3: MagicMock(first_name="Ana", last_name="L", username="ana")},
            "all_kardex_rows": [
                {"kardex": "K1", "idusuario": 3},
                {"kardex": "K-SENT", "idusuario": 3},
            ],
            "eligible_kardex_rows": [{"kardex": "K1", "idusuario": 3}],
            "counts_by_kardex": {"K1": {"sisgen": 2, "uif": 0}},
        }
        mock_get_user_model.return_value.filter.return_value = [
            MagicMock(idusuario=3, first_name="Ana", last_name="L", username="ana")
        ]

        report = ComplianceUserMonthlyService().build_report(year=2026, month=6)
        user3 = report["users"][0]
        self.assertEqual(user3["total_kardex"], 2)
        self.assertEqual(user3["kardex_with_errors"], 1)
        self.assertEqual(user3["error_rate"], 0.5)
        self.assertEqual(report["summary"]["total_kardex"], 2)
