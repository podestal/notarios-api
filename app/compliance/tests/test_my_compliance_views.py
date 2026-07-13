from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from compliance.services.user_monthly_service import (
    months_window,
    shift_year_month,
)
from compliance.views import (
    ComplianceMyKardexErrorsView,
    ComplianceMyKardexMonthView,
    ComplianceMyKardexView,
)


class MonthsWindowTests(SimpleTestCase):
    def test_shift_across_year(self):
        self.assertEqual(shift_year_month(2026, 1, -1), (2025, 12))
        self.assertEqual(shift_year_month(2025, 12, 1), (2026, 1))

    def test_window_current_and_past(self):
        self.assertEqual(
            months_window(2026, 7, months_back=1),
            [(2026, 7), (2026, 6)],
        )


class ComplianceMyKardexViewTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = MagicMock(is_authenticated=True, idusuario=10, pk=10)

    @patch("compliance.views.ComplianceUserMonthlyService")
    def test_returns_counts_summary_two_months(self, mock_service_cls):
        mock_service_cls.return_value.build_my_kardex_summary.return_value = {
            "year": 2026,
            "month": 7,
            "idusuario": 10,
            "months": [
                {
                    "year": 2026,
                    "month": 7,
                    "total_kardex": 12,
                    "kardex_with_errors": 3,
                    "counts": {"sisgen": 5, "uif": 2, "pdt": 0, "total": 7},
                },
                {
                    "year": 2026,
                    "month": 6,
                    "total_kardex": 15,
                    "kardex_with_errors": 4,
                    "counts": {"sisgen": 1, "uif": 8, "pdt": 0, "total": 9},
                },
            ],
        }

        request = self.factory.get("/compliance/me/kardex/?year=2026&month=7")
        force_authenticate(request, user=self.user)
        response = ComplianceMyKardexView.as_view()(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["months"]), 2)
        self.assertNotIn("kardex", response.data)
        mock_service_cls.return_value.build_my_kardex_summary.assert_called_once_with(
            year=2026,
            month=7,
            use_cache=False,
            force_live=False,
            idusuario=10,
            errors_only=True,
            months_back=1,
        )


class ComplianceMyKardexMonthViewTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = MagicMock(is_authenticated=True, idusuario=10, pk=10)

    @patch("compliance.views.ComplianceUserMonthlyService")
    def test_returns_kardex_list_for_month(self, mock_service_cls):
        mock_service_cls.return_value.build_user_kardex_report.return_value = {
            "year": 2026,
            "month": 6,
            "period": {},
            "source": {},
            "errors_only": True,
            "summary": {},
            "users": [
                {
                    "idusuario": 10,
                    "name": "Ana",
                    "username": "ana",
                    "total_kardex": 2,
                    "kardex_with_errors": 1,
                    "kardex_count": 1,
                    "error_rate": 0.5,
                    "counts": {"sisgen": 0, "uif": 2, "pdt": 0, "total": 2},
                    "kardex": [
                        {
                            "kardex": "K1-2026",
                            "counts": {"sisgen": 0, "uif": 2, "pdt": 0, "total": 2},
                        }
                    ],
                }
            ],
        }

        request = self.factory.get("/compliance/me/kardex/month/?year=2026&month=6")
        force_authenticate(request, user=self.user)
        response = ComplianceMyKardexMonthView.as_view()(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["kardex"][0]["kardex"], "K1-2026")
        mock_service_cls.return_value.build_user_kardex_report.assert_called_once_with(
            year=2026,
            month=6,
            use_cache=False,
            force_live=False,
            idusuario=10,
            errors_only=True,
        )


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
