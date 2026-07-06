from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from compliance.views import ComplianceMyKardexErrorsView, ComplianceMyKardexView


class ComplianceMyKardexViewTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = MagicMock(is_authenticated=True, idusuario=10, pk=10)

    @patch("compliance.views.ComplianceUserMonthlyService")
    def test_uses_logged_in_idusuario(self, mock_service_cls):
        mock_service_cls.return_value.build_user_kardex_report.return_value = {
            "year": 2026,
            "month": 6,
            "users": [
                {
                    "idusuario": 10,
                    "name": "Ana",
                    "username": "ana",
                    "total_kardex": 1,
                    "kardex_with_errors": 1,
                    "error_rate": 1.0,
                    "kardex_count": 1,
                    "counts": {"sisgen": 1, "uif": 0, "pdt": 0, "total": 1},
                    "kardex": [{"kardex": "K1-2026", "counts": {"total": 1}}],
                }
            ],
        }

        request = self.factory.get("/compliance/me/kardex/")
        force_authenticate(request, user=self.user)
        response = ComplianceMyKardexView.as_view()(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"]["idusuario"], 10)
        mock_service_cls.return_value.build_user_kardex_report.assert_called_once_with(
            year=None,
            month=None,
            use_cache=False,
            idusuario=10,
            errors_only=True,
        )

    @patch("compliance.views.ComplianceUserMonthlyService")
    def test_empty_users_block(self, mock_service_cls):
        mock_service_cls.return_value.build_user_kardex_report.return_value = {
            "year": 2026,
            "month": 6,
            "users": [],
        }

        request = self.factory.get("/compliance/me/kardex/")
        force_authenticate(request, user=self.user)
        response = ComplianceMyKardexView.as_view()(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["user"])
        self.assertEqual(response.data["kardex"], [])


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
