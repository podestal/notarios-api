from datetime import date
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from uif.services.load_data import RoLoadDataService, _parse_act_codes


class ParseActCodesTests(SimpleTestCase):
    def test_splits_three_char_codes(self):
        self.assertEqual(_parse_act_codes("001002"), ["001", "002"])

    def test_empty(self):
        self.assertEqual(_parse_act_codes(""), [])


class RoLoadDataServiceTests(SimpleTestCase):
    @patch("uif.services.load_data.models")
    def test_acts_without_uif_go_to_ro_not(self, models_mock):
        kardex = MagicMock(
            idkardex=1,
            kardex="KAR-1",
            idtipkar=1,
            codactos="999",
            numescritura="1",
            fechaescritura=date(2024, 1, 15),
            fechaconclusion=date(2024, 1, 20),
        )
        models_mock.Kardex.objects.filter.return_value.exclude.return_value.order_by.return_value = [
            kardex
        ]
        tipo_qs_uif = MagicMock()
        tipo_qs_uif.exclude.return_value = []
        tipo_qs_all = MagicMock()
        tipo_qs_all.__iter__ = lambda self: iter([])
        models_mock.Tiposdeacto.objects.filter.side_effect = [tipo_qs_uif, tipo_qs_all]
        models_mock.Contratantes.objects.exclude.return_value.exclude.return_value.only.return_value = []

        loader = RoLoadDataService()
        loader._act_descriptions = {}
        ro, ro_not = loader.load(date(2024, 1, 1), date(2024, 1, 31))

        self.assertEqual(len(ro), 0)
        self.assertEqual(len(ro_not), 1)
        self.assertEqual(ro_not[0].cod_acto, "999")
