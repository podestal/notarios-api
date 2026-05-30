import json
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from uif.services.corrections import (
    CARGO_OTROS_ID,
    CARGO_OTROS_LABEL,
    CATEGORY_CARGO,
    CATEGORY_CONSTITUCION_RUC,
    CATEGORY_PROFESION,
    PROFESION_OTROS_ID,
    PROFESION_OTROS_LABEL,
    TIPDOC_SIN_RUC,
    UifCorrectionService,
)


class UifCorrectionServiceTests(SimpleTestCase):
    def test_parse_corrections_payload_django_shape(self):
        payload = {"corrections": [{"categoryCorrect": 2, "idContractor": "1"}]}
        self.assertEqual(
            UifCorrectionService.parse_corrections_payload(payload),
            [{"categoryCorrect": 2, "idContractor": "1"}],
        )

    def test_parse_corrections_payload_legacy_list_error(self):
        row = {"categoryCorrect": 3, "idContractor": "161"}
        payload = {"listError": json.dumps([row])}
        self.assertEqual(UifCorrectionService.parse_corrections_payload(payload), [row])

    def test_category_1_updates_cliente2_like_php(self):
        service = UifCorrectionService()
        mock_qs = MagicMock()
        mock_qs.update.return_value = 1
        with patch("uif.services.corrections.models.Cliente2.objects.filter", return_value=mock_qs):
            result = service.apply(
                [{"categoryCorrect": 1, "idContractor": "0000000161", "kardex": "K1"}]
            )
        mock_qs.update.assert_called_once_with(idtipdoc=TIPDOC_SIN_RUC, numdoc="")
        self.assertEqual(result["total_applied"], 1)
        self.assertEqual(result["errorDescription"], "Se afectaron 1 registros.")
        self.assertEqual(result["applied"][0]["categoryCorrect"], CATEGORY_CONSTITUCION_RUC)

    def test_category_2_updates_profesion_otros(self):
        service = UifCorrectionService()
        mock_qs = MagicMock()
        mock_qs.update.return_value = 1
        with patch("uif.services.corrections.models.Cliente2.objects.filter", return_value=mock_qs):
            result = service.apply([{"categoryCorrect": "2", "idContratante": "161"}])
        mock_qs.update.assert_called_once_with(
            idprofesion=PROFESION_OTROS_ID,
            detaprofesion=PROFESION_OTROS_LABEL,
        )
        self.assertEqual(result["total_applied"], 1)
        self.assertEqual(result["applied"][0]["categoryCorrect"], CATEGORY_PROFESION)

    def test_category_3_updates_cargo_otros(self):
        service = UifCorrectionService()
        mock_qs = MagicMock()
        mock_qs.update.return_value = 1
        with patch("uif.services.corrections.models.Cliente2.objects.filter", return_value=mock_qs):
            result = service.apply([{"categoryCorrect": 3, "idContractor": "162"}])
        mock_qs.update.assert_called_once_with(
            idcargoprofe=CARGO_OTROS_ID,
            profocupa=CARGO_OTROS_LABEL,
        )
        self.assertEqual(result["total_applied"], 1)
        self.assertEqual(result["applied"][0]["categoryCorrect"], CATEGORY_CARGO)

    def test_category_skipped_when_cliente2_missing(self):
        service = UifCorrectionService()
        mock_qs = MagicMock()
        mock_qs.update.return_value = 0
        with patch("uif.services.corrections.models.Cliente2.objects.filter", return_value=mock_qs):
            result = service.apply([{"categoryCorrect": 2, "idContractor": "999"}])
        self.assertEqual(result["total_applied"], 0)
        self.assertEqual(result["errorDescription"], "Se afectaron 0 registros.")
        self.assertEqual(result["skipped"][0]["reason"], "cliente2 no encontrado")
