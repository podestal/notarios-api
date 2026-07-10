from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from compliance.services.kardex_detail_service import KardexComplianceDetailService
from compliance.services.payload import (
    build_payload,
    build_sisgen_block,
    build_uif_block,
    serialize_kardex_errors_detail,
)


class SerializeKardexErrorsDetailTests(SimpleTestCase):
    def test_counts_sisgen_errores_only_in_total(self):
        kardex_row = MagicMock(
            kardex="K1",
            idkardex="1",
            idtipkar=1,
            numescritura="10",
            fechaingreso="2026-06-01",
            fechaescritura="2026-06-05",
        )
        payload = build_payload(
            kardex="K1",
            idkardex="1",
            idtipkar=1,
            kardex_meta={},
            uif_block=build_uif_block(
                {
                    "has_uif_errors": True,
                    "uif_errors": [{"error_type": "x", "error_description": "bad"}],
                    "uif_observations": [],
                }
            ),
            sisgen_block=build_sisgen_block(
                errores=["Falta fecha"],
                observaciones=["Falta ANCERT"],
                personas=["Juan: sin DNI"],
            ),
        )
        detail = serialize_kardex_errors_detail(
            kardex_row=kardex_row,
            payload=payload,
            source="live_validation",
        )
        self.assertEqual(detail["counts"]["sisgen"], 1)
        self.assertEqual(detail["counts"]["uif"], 1)
        self.assertEqual(detail["counts"]["total"], 2)
        self.assertEqual(len(detail["errors"]["sisgen"]["personas"]), 1)
        self.assertEqual(len(detail["errors"]["sisgen"]["observaciones"]), 1)


class KardexComplianceDetailServiceTests(SimpleTestCase):
    @patch("compliance.services.kardex_detail_service.collect_sisgen_issues")
    @patch("compliance.services.kardex_detail_service.collect_uif_issues")
    @patch("compliance.services.kardex_detail_service.models.Kardex")
    def test_live_detail(self, mock_kardex_model, mock_uif, mock_sisgen):
        kardex = MagicMock(
            kardex="K1-2026",
            idkardex=1,
            idtipkar=1,
            numescritura="10",
            codactos="094",
            contrato="TEST",
            fechaescritura="2026-06-01",
            fechaconclusion="",
            fechaingreso="2026-06-01",
        )
        mock_kardex_model.objects.filter.return_value.first.return_value = kardex
        mock_uif.return_value = build_uif_block(
            {"has_uif_errors": False, "uif_errors": [], "uif_observations": []}
        )
        mock_sisgen.return_value = build_sisgen_block(
            errores=["err"], observaciones=[], personas=[]
        )

        detail = KardexComplianceDetailService().build_detail("K1-2026")
        self.assertEqual(detail["source"], "live_validation")
        self.assertEqual(detail["errors"]["sisgen"]["errores"], ["err"])
        mock_uif.assert_called_once_with("K1-2026")
        mock_sisgen.assert_called_once_with("K1-2026")

    @patch("compliance.services.kardex_detail_service.collect_sisgen_issues")
    @patch("compliance.services.kardex_detail_service.collect_uif_issues")
    @patch("compliance.services.kardex_detail_service.models.Kardex")
    def test_sent_to_sisgen_still_returns_uif(self, mock_kardex_model, mock_uif, mock_sisgen):
        kardex = MagicMock(
            kardex="K1-2026",
            idkardex=1,
            idtipkar=1,
            numescritura="10",
            codactos="094",
            contrato="TEST",
            fechaescritura="2026-06-01",
            fechaconclusion="",
            fechaingreso="2026-06-01",
            estado_sisgen=1,
        )
        mock_kardex_model.objects.filter.return_value.first.return_value = kardex
        mock_uif.return_value = build_uif_block(
            {
                "has_uif_errors": True,
                "uif_errors": [{"error_type": "x", "error_description": "bad"}],
                "uif_observations": [],
            }
        )

        detail = KardexComplianceDetailService().build_detail("K1-2026")
        self.assertTrue(detail["sisgen_sent"])
        self.assertEqual(detail["counts"]["uif"], 1)
        self.assertEqual(detail["counts"]["sisgen"], 0)
        self.assertTrue(detail["has_errors"])
        mock_uif.assert_called_once_with("K1-2026")
        mock_sisgen.assert_not_called()

    @patch("compliance.services.kardex_detail_service.collect_sisgen_issues")
    @patch("compliance.services.kardex_detail_service.collect_uif_issues")
    @patch("compliance.services.kardex_detail_service.models.Kardex")
    def test_pending_escrituracion_still_returns_uif(
        self, mock_kardex_model, mock_uif, mock_sisgen
    ):
        kardex = MagicMock(
            kardex="K1-2026",
            idkardex=1,
            idtipkar=1,
            numescritura="",
            codactos="094",
            contrato="TEST",
            fechaescritura="2026-06-01",
            fechaconclusion="",
            fechaingreso="2026-06-01",
            estado_sisgen=0,
        )
        mock_kardex_model.objects.filter.return_value.first.return_value = kardex
        mock_uif.return_value = build_uif_block(
            {
                "has_uif_errors": True,
                "uif_errors": [{"error_type": "x", "error_description": "bad"}],
                "uif_observations": [],
            }
        )

        detail = KardexComplianceDetailService().build_detail("K1-2026")
        self.assertTrue(detail["escrituracion_pending"])
        self.assertEqual(detail["counts"]["uif"], 1)
        self.assertEqual(detail["counts"]["sisgen"], 0)
        mock_sisgen.assert_not_called()

    @patch("compliance.services.kardex_detail_service.collect_sisgen_issues")
    @patch("compliance.services.kardex_detail_service.collect_uif_issues")
    @patch("compliance.services.kardex_detail_service.kardex_owned_by_user")
    def test_build_detail_for_user_uses_ownership(self, mock_owned, mock_uif, mock_sisgen):
        kardex = MagicMock(
            kardex="K1-2026",
            idkardex=1,
            idtipkar=1,
            numescritura="10",
            codactos="094",
            contrato="TEST",
            fechaescritura="2026-06-01",
            fechaconclusion="",
            fechaingreso="2026-06-01",
            estado_sisgen=0,
        )
        mock_owned.return_value = kardex
        user = MagicMock(is_authenticated=True, idusuario=5, pk=5)
        mock_uif.return_value = build_uif_block(
            {"has_uif_errors": False, "uif_errors": [], "uif_observations": []}
        )
        mock_sisgen.return_value = build_sisgen_block(
            errores=["err"], observaciones=[], personas=[]
        )

        detail = KardexComplianceDetailService().build_detail_for_user(user, "K1-2026")

        mock_owned.assert_called_once_with(kardex="K1-2026", user=user)
        self.assertEqual(detail["source"], "live_validation")

    @patch("compliance.services.kardex_detail_service.kardex_owned_by_user")
    def test_build_detail_for_user_not_owned(self, mock_owned):
        from compliance.services.kardex_detail_service import KardexNotFoundError

        mock_owned.return_value = None
        user = MagicMock(is_authenticated=True, idusuario=5, pk=5)

        with self.assertRaises(KardexNotFoundError):
            KardexComplianceDetailService().build_detail_for_user(user, "K1-2026")
