from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from notaria.serializers import (
    KardexSerializer,
    _fktemplate_is_blank,
    _normalize_fktemplate,
)


class FktemplateHelpersTests(SimpleTestCase):
    def test_blank_values(self):
        self.assertTrue(_fktemplate_is_blank(None))
        self.assertTrue(_fktemplate_is_blank(""))
        self.assertTrue(_fktemplate_is_blank(0))
        self.assertTrue(_fktemplate_is_blank("0"))
        self.assertFalse(_fktemplate_is_blank(337))
        self.assertFalse(_fktemplate_is_blank("337"))

    def test_normalize(self):
        self.assertEqual(_normalize_fktemplate("337"), 337)
        self.assertEqual(_normalize_fktemplate(0), 0)
        self.assertEqual(_normalize_fktemplate(None), 0)


class KardexSerializerFktemplateTests(SimpleTestCase):
    @patch.object(KardexSerializer, "to_representation", return_value={"fktemplate": 337})
    def test_update_preserves_existing_when_incoming_is_zero(self, _to_repr):
        instance = SimpleNamespace(fktemplate="337")
        serializer = KardexSerializer()
        with patch(
            "rest_framework.serializers.ModelSerializer.update",
            return_value=instance,
        ) as mock_super_update:
            serializer.update(instance, {"fktemplate": 0, "referencia": "x"})

        mock_super_update.assert_called_once()
        validated = mock_super_update.call_args.args[1]
        self.assertNotIn("fktemplate", validated)
        self.assertEqual(validated["referencia"], "x")

    @patch.object(KardexSerializer, "to_representation", return_value={"fktemplate": 0})
    def test_update_allows_setting_plantilla_when_blank(self, _to_repr):
        instance = SimpleNamespace(fktemplate="0")
        serializer = KardexSerializer()
        with patch(
            "rest_framework.serializers.ModelSerializer.update",
            return_value=instance,
        ) as mock_super_update:
            serializer.update(instance, {"fktemplate": 404})

        validated = mock_super_update.call_args.args[1]
        self.assertEqual(validated["fktemplate"], 404)
