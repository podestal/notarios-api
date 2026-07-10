from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from notaria.services.kardex_acto_cleanup import (
    delete_kardex_acto_related,
    filter_participants_to_active_actos,
    rebuild_contratantes_condicion_for_kardex,
)


class FilterParticipantsToActiveActosTests(SimpleTestCase):
    @patch("notaria.services.kardex_acto_cleanup.active_idtipoactos_for_kardex")
    def test_drops_stale_idtipoacto(self, mock_active):
        mock_active.return_value = {"028"}
        participants = [
            {"idcontratante": "1", "idtipoacto": "030", "idcondicion": "043"},
            {"idcontratante": "2", "idtipoacto": "028", "idcondicion": "050"},
        ]

        filtered = filter_participants_to_active_actos(
            participants, kardex="K30-2026", codactos="028"
        )

        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["idtipoacto"], "028")


class RebuildContratantesCondicionTests(SimpleTestCase):
    @patch("notaria.services.kardex_acto_cleanup.models.Contratantes")
    @patch("notaria.services.kardex_acto_cleanup.models.Contratantesxacto")
    @patch("notaria.services.kardex_acto_cleanup.active_idtipoactos_for_kardex")
    def test_rebuild_from_active_cxa_only(self, mock_active, mock_cxa, mock_contratantes):
        mock_active.return_value = {"028"}
        row = MagicMock(idcontratante="0001", idcondicion="049", item="5642", idtipoacto="028")
        mock_cxa.objects.filter.return_value = [row]
        contratante = MagicMock(pk=1, idcontratante="0001", condicion="043.5641/049.5642/")
        mock_contratantes.objects.filter.return_value = [contratante]

        updated = rebuild_contratantes_condicion_for_kardex("K30-2026")

        self.assertEqual(updated, 1)
        mock_contratantes.objects.filter(pk=1).update.assert_called_once_with(
            condicion="049.5642/"
        )


class DeleteKardexActoRelatedTests(SimpleTestCase):
    @patch("notaria.services.kardex_acto_cleanup.models.DetalleActosKardex")
    @patch("notaria.services.kardex_acto_cleanup.models.Representantes")
    @patch("notaria.services.kardex_acto_cleanup.models.Detallevehicular")
    @patch("notaria.services.kardex_acto_cleanup.models.Detallebienes")
    @patch("notaria.services.kardex_acto_cleanup.models.Detallemediopago")
    @patch("notaria.services.kardex_acto_cleanup.models.Patrimonial")
    @patch("notaria.services.kardex_acto_cleanup._sync_contratantes_condicion")
    @patch("notaria.services.kardex_acto_cleanup.models.Contratantesxacto")
    def test_cascade_deletes_related_tables(
        self,
        mock_cxa,
        mock_sync_cond,
        mock_pat,
        mock_mp,
        mock_bi,
        mock_veh,
        mock_rep,
        mock_detalle,
    ):
        row = MagicMock(idcontratante="0001", idcondicion="043", item="5641")
        mock_cxa.objects.filter.return_value = mock_cxa_qs = MagicMock()
        mock_cxa_qs.__iter__ = lambda self: iter([row])
        mock_cxa_qs.delete.return_value = (1, {})
        mock_sync_cond.return_value = 1

        pat_row = MagicMock(itemmp="000123")
        mock_pat.objects.filter.return_value.first.side_effect = None
        mock_pat.objects.filter.return_value = pat_qs = MagicMock()
        pat_qs.__iter__ = lambda self: iter([pat_row])
        pat_qs.delete.return_value = (1, {})

        mock_mp.objects.filter.return_value.delete.return_value = (2, {})
        mock_bi.objects.filter.return_value.delete.return_value = (1, {})
        mock_veh.objects.filter.return_value.delete.return_value = (1, {})
        mock_rep.objects.filter.return_value.delete.return_value = (0, {})
        mock_detalle.objects.filter.return_value.delete.return_value = (1, {})

        counts = delete_kardex_acto_related(kardex="K30-2026", idtipoacto="030")

        self.assertEqual(counts["contratantesxacto"], 1)
        self.assertEqual(counts["contratantes_condicion_updated"], 1)
        self.assertEqual(counts["patrimonial"], 1)
        self.assertEqual(counts["detalle_actos_kardex"], 1)
        mock_sync_cond.assert_called_once()
