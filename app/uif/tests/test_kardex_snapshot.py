from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from uif.services.kardex_snapshot import bulk_validate_kardex_numbers, validate_kardex_number


class KardexSnapshotTests(SimpleTestCase):
    def test_empty_kardex_returns_empty_result(self):
        result = validate_kardex_number("")
        self.assertFalse(result["has_uif_errors"])
        self.assertEqual(result["uif_errors"], [])

    @patch("uif.services.kardex_snapshot.models.Kardex")
    def test_missing_kardex_returns_empty(self, mock_kardex_model):
        mock_kardex_model.objects.filter.return_value.first.return_value = None
        result = validate_kardex_number("MISSING")
        self.assertFalse(result["has_uif_errors"])

    @patch("uif.services.kardex_snapshot.RoEligibleRowValidator")
    @patch("uif.services.kardex_snapshot.UifDashboardService")
    @patch("uif.services.kardex_snapshot.models.Tiposdeacto")
    @patch("uif.services.kardex_snapshot.models.Kardex")
    def test_validate_collects_errors(
        self, mock_kardex_model, mock_tipos, mock_dashboard_cls, mock_validator_cls
    ):
        kardex = MagicMock(
            idkardex=1,
            kardex="K1",
            codactos="094",
            idtipkar=1,
            numescritura="10",
            fechaescritura=None,
            fechaconclusion=None,
        )
        mock_kardex_model.objects.filter.return_value.first.return_value = kardex
        tipo = MagicMock(idtipoacto="094", actouif="010", desacto="ACTO")
        mock_tipos.objects.filter.return_value.exclude.return_value = [tipo]

        dashboard = mock_dashboard_cls.return_value
        dashboard._bulk_fetch_related.return_value = ({}, {}, {}, {}, {}, {})

        mock_validator_cls.return_value.validate_row.return_value = [
            {"error_type": "missing_escritura_number"}
        ]

        result = validate_kardex_number("K1")
        self.assertTrue(result["has_uif_errors"])
        self.assertEqual(len(result["uif_errors"]), 1)

    @patch("uif.services.kardex_snapshot.validate_kardex_number")
    def test_bulk_validate_maps_keys(self, mock_validate):
        mock_validate.side_effect = lambda k: {"kardex": k, "has_uif_errors": False, "uif_errors": [], "uif_observations": [], "patrimonial_data": {}}
        out = bulk_validate_kardex_numbers(["A", "B"])
        self.assertEqual(set(out.keys()), {"A", "B"})
