from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from compliance.services.user_monthly_service import (
    months_window,
    shift_year_month,
)
from compliance.views import ComplianceMyKardexErrorsView, ComplianceMyKardexView


class MonthsWindowTests(SimpleTestCase):
    def test_shift_across_year(self):
        self.assertEqual(shift_year_month(2026, 1, -1), (2025, 12))
        self.assertEqual(shift_year_month(2025, 12, 1), (2026, 1))

    def test_window_newest_first(self):
        self.assertEqual(
            months_window(2026, 7, months_back=2),
            [(2026, 7), (2026, 6), (2026, 5)],
        )


class ComplianceMyKardexViewTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = MagicMock(is_authenticated=True, idusuario=10, pk=10)

    @patch("compliance.views.ComplianceUserMonthlyService")
    def test_uses_rolling_report_for_logged_in_user(self, mock_service_cls):
        mock_service_cls.return_value.build_my_kardex_rolling_report.return_value = {
            "year": 2026,
            "month": 7,
            "user": {"idusuario": 10, "name": "Ana", "username": "ana"},
            "months": [
                {"year": 2026, "month": 7, "counts": {"total": 1}, "kardex": []},
                {"year": 2026, "month": 6, "counts": {"total": 2}, "kardex": []},
                {"year": 2026, "month": 5, "counts": {"total": 0}, "kardex": []},
            ],
            "rolling_summary": {
                "months_included": 3,
                "counts": {"sisgen": 0, "uif": 3, "pdt": 0, "total": 3},
            },
            "total_kardex": 1,
            "kardex_with_errors": 1,
            "error_rate": 1.0,
            "kardex_count": 1,
            "counts": {"sisgen": 0, "uif": 1, "pdt": 0, "total": 1},
            "kardex": [{"kardex": "K1-2026", "counts": {"total": 1}}],
            "users": [],
        }

        request = self.factory.get("/compliance/me/kardex/?year=2026&month=7")
        force_authenticate(request, user=self.user)
        response = ComplianceMyKardexView.as_view()(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"]["idusuario"], 10)
        self.assertEqual(len(response.data["months"]), 3)
        self.assertEqual(response.data["rolling_summary"]["counts"]["total"], 3)
        mock_service_cls.return_value.build_my_kardex_rolling_report.assert_called_once_with(
            year=2026,
            month=7,
            use_cache=False,
            force_live=False,
            idusuario=10,
            errors_only=True,
            months_back=2,
        )

    @patch("compliance.views.ComplianceUserMonthlyService")
    def test_empty_focus_month_still_returns_months(self, mock_service_cls):
        mock_service_cls.return_value.build_my_kardex_rolling_report.return_value = {
            "year": 2026,
            "month": 7,
            "user": None,
            "months": [
                {"year": 2026, "month": 7, "counts": {"total": 0}, "kardex": []},
                {"year": 2026, "month": 6, "counts": {"total": 0}, "kardex": []},
                {"year": 2026, "month": 5, "counts": {"total": 0}, "kardex": []},
            ],
            "rolling_summary": {
                "months_included": 3,
                "counts": {"sisgen": 0, "uif": 0, "pdt": 0, "total": 0},
            },
            "total_kardex": 0,
            "kardex_with_errors": 0,
            "error_rate": 0.0,
            "kardex_count": 0,
            "counts": {"sisgen": 0, "uif": 0, "pdt": 0, "total": 0},
            "kardex": [],
            "users": [],
        }

        request = self.factory.get("/compliance/me/kardex/")
        force_authenticate(request, user=self.user)
        response = ComplianceMyKardexView.as_view()(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["user"])
        self.assertEqual(response.data["kardex"], [])
        self.assertEqual(len(response.data["months"]), 3)


class ComplianceMyKardexErrorsViewTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = MagicMock(is_authenticated=True, idusuario=10, pk=10)

    @patch("compliance.views.KardexComplianceDetailService")
    def test_delegates_to_build_detail_for_user(self, mock_service_cls):
        mock_service_cls.return_value.build_detail_for_user.return_value = {
            "kardex": "K1-2026",
            "has_errors": True,
            "counts": {"total": 1},
        }

        request = self.factory.get("/compliance/me/kardex/K1-2026/errors/")
        force_authenticate(request, user=self.user)
        response = ComplianceMyKardexErrorsView.as_view()(request, kardex="K1-2026")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_service_cls.return_value.build_detail_for_user.assert_called_once_with(
            self.user,
            "K1-2026",
            use_cache=False,
            source_filter=None,
        )

    @patch("compliance.views.KardexComplianceDetailService")
    def test_not_found_when_not_owned(self, mock_service_cls):
        from compliance.services.kardex_detail_service import KardexNotFoundError

        mock_service_cls.return_value.build_detail_for_user.side_effect = KardexNotFoundError(
            "Kardex not found: K1-2026"
        )

        request = self.factory.get("/compliance/me/kardex/K1-2026/errors/")
        force_authenticate(request, user=self.user)
        response = ComplianceMyKardexErrorsView.as_view()(request, kardex="K1-2026")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
