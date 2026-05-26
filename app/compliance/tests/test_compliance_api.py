from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from compliance.services.payload import (
    build_payload,
    build_sisgen_block,
    build_uif_block,
    counts_from_payload,
    filter_payload_sources,
    serialize_cache_row,
    SOURCE_UIF,
)


class PayloadShapeTests(SimpleTestCase):
    def test_example_payload_shape(self):
        uif = build_uif_block(
            {
                "has_uif_errors": True,
                "uif_errors": [
                    {
                        "kardex": "K1-2026",
                        "fieldNumber": 47,
                        "error_type": "invalid_oportunidad_pago",
                        "error_description": "Oportunidad invalida",
                    }
                ],
                "uif_observations": [],
                "patrimonial_data": {"094": {"importetrans": 15000}},
            }
        )
        sisgen = build_sisgen_block(
            errores=["Falta campo requerido: fechaescritura"],
            observaciones=["Falta domicilio fiscal"],
            personas=["DNI invalido: 123"],
        )
        payload = build_payload(
            kardex="K1-2026",
            idkardex="99",
            idtipkar=1,
            kardex_meta={"contrato": "COMPRAVENTA"},
            uif_block=uif,
            sisgen_block=sisgen,
        )
        self.assertEqual(payload["version"], 1)
        self.assertTrue(payload["summary"]["has_errors"])
        self.assertEqual(payload["summary"]["by_source"]["uif"], 1)
        self.assertEqual(payload["summary"]["by_source"]["sisgen"], 2)
        self.assertEqual(payload["sources"]["pdt"]["status"], "pending")

    def test_filter_payload_by_source_uif(self):
        payload = build_payload(
            kardex="K1",
            idkardex="1",
            idtipkar=1,
            kardex_meta={},
            uif_block=build_uif_block(
                {"has_uif_errors": True, "uif_errors": [{"a": 1}], "uif_observations": []}
            ),
            sisgen_block=build_sisgen_block(errores=["x"], observaciones=[], personas=[]),
        )
        filtered = filter_payload_sources(payload, SOURCE_UIF)
        self.assertIn("uif", filtered["sources"])
        self.assertNotIn("sisgen", filtered["sources"])


class RefreshServiceTests(SimpleTestCase):
    @patch("compliance.services.refresh_service.collect_sisgen_issues")
    @patch("compliance.services.refresh_service.collect_uif_issues")
    @patch("compliance.services.refresh_service.models.Kardex")
    @patch("compliance.services.refresh_service.KardexComplianceCache")
    def test_refresh_kardex_upserts(
        self, mock_cache_model, mock_kardex_model, mock_uif, mock_sisgen
    ):
        from compliance.services.refresh_service import ComplianceRefreshService

        kardex = MagicMock()
        kardex.kardex = "K1-2026"
        kardex.idkardex = 10
        kardex.idtipkar = 1
        kardex.numescritura = "100"
        kardex.codactos = "094"
        kardex.contrato = "TEST"
        kardex.fechaescritura = "2026-04-15"
        kardex.fechaconclusion = ""
        mock_kardex_model.objects.filter.return_value.first.return_value = kardex

        mock_uif.return_value = build_uif_block(
            {"has_uif_errors": False, "uif_errors": [], "uif_observations": []}
        )
        mock_sisgen.return_value = build_sisgen_block(errores=[], observaciones=[], personas=[])

        row = MagicMock()
        row.kardex = "K1-2026"
        mock_cache_model.objects.update_or_create.return_value = (row, True)

        result = ComplianceRefreshService().refresh_kardex("K1-2026")
        self.assertEqual(result, row)
        mock_cache_model.objects.update_or_create.assert_called_once()
        defaults = mock_cache_model.objects.update_or_create.call_args[1]["defaults"]
        self.assertEqual(defaults["uif_error_count"], 0)


class SerializeCacheRowTests(SimpleTestCase):
    def test_serialize_includes_counts(self):
        row = MagicMock()
        row.kardex = "K1"
        row.idkardex = "1"
        row.idtipkar = 1
        row.fechaescritura = None
        row.has_errors = True
        row.uif_error_count = 2
        row.sisgen_error_count = 1
        row.sisgen_observation_count = 0
        row.total_error_count = 3
        row.updated_at = MagicMock(isoformat=lambda: "2026-05-19T00:00:00")
        row.payload = {"validated_at": "2026-05-19T12:00:00Z", "summary": {}, "kardex_meta": {}}
        data = serialize_cache_row(row, include_payload=False)
        self.assertEqual(data["counts"]["total"], 3)
