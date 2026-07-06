from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from compliance.services.access import kardex_owned_by_user, resolve_idusuario


class ResolveIdusuarioTests(SimpleTestCase):
    def test_prefers_idusuario_attribute(self):
        user = MagicMock(idusuario=42, pk=99)
        self.assertEqual(resolve_idusuario(user), 42)

    def test_falls_back_to_pk(self):
        user = MagicMock(spec=[])
        user.pk = 7
        self.assertEqual(resolve_idusuario(user), 7)


class KardexOwnedByUserTests(SimpleTestCase):
    @patch("compliance.services.access.models.Kardex")
    def test_returns_row_when_owner_matches(self, mock_kardex_model):
        row = MagicMock(idusuario=5)
        mock_kardex_model.objects.filter.return_value.first.return_value = row
        user = MagicMock(is_authenticated=True, idusuario=5, pk=5)

        result = kardex_owned_by_user(kardex="K1-2026", user=user)

        self.assertIs(result, row)
        mock_kardex_model.objects.filter.assert_called_once_with(kardex="K1-2026")

    @patch("compliance.services.access.models.Kardex")
    def test_returns_none_for_other_owner(self, mock_kardex_model):
        row = MagicMock(idusuario=99)
        mock_kardex_model.objects.filter.return_value.first.return_value = row
        user = MagicMock(is_authenticated=True, idusuario=5, pk=5)

        self.assertIsNone(kardex_owned_by_user(kardex="K1-2026", user=user))

    @patch("compliance.services.access.models.Kardex")
    def test_returns_none_when_kardex_missing(self, mock_kardex_model):
        mock_kardex_model.objects.filter.return_value.first.return_value = None
        user = MagicMock(is_authenticated=True, idusuario=5, pk=5)

        self.assertIsNone(kardex_owned_by_user(kardex="MISSING", user=user))
