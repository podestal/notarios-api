from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from notaria.services.kardex_acto_cleanup import (
    delete_kardex_acto_related,
    filter_participants_to_active_actos,
    purge_orphan_contratantesxacto_for_kardex,
    rebuild_contratantes_condicion_for_kardex,
    resolve_condition_pairs_for_kardex,
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

        list_qs = MagicMock()
        list_qs.__iter__ = lambda self: iter([contratante])
        update_qs = MagicMock()
        mock_contratantes.objects.filter.side_effect = [list_qs, update_qs]

        updated = rebuild_contratantes_condicion_for_kardex("K30-2026")

        self.assertEqual(updated, 1)
        update_qs.update.assert_called_once_with(condicion="049.5642/")


class DeleteKardexActoRelatedTests(SimpleTestCase):
    @patch("notaria.services.kardex_acto_cleanup.rebuild_contratantes_condicion_for_kardex")
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
        mock_rebuild,
    ):
        row = MagicMock(idcontratante="0001", idcondicion="043", item="5641")
        mock_cxa.objects.filter.return_value = mock_cxa_qs = MagicMock()
        mock_cxa_qs.__iter__ = lambda self: iter([row])
        mock_cxa_qs.delete.return_value = (1, {})
        mock_sync_cond.return_value = 1
        mock_rebuild.return_value = 1

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
        mock_rebuild.assert_called_once_with("K30-2026")


class ResolveConditionPairsForKardexTests(SimpleTestCase):
    @patch("notaria.services.kardex_acto_cleanup.models.Actocondicion")
    @patch("notaria.services.kardex_acto_cleanup.active_detalle_item_by_acto")
    def test_drops_conditions_for_removed_acto(self, mock_detalle, mock_acto_cond):
        mock_detalle.return_value = {"028": "6028"}

        def _get(**kwargs):
            idc = kwargs.get("idcondicion")
            if idc == "043":
                return MagicMock(idtipoacto="030")
            if idc == "049":
                return MagicMock(idtipoacto="028")
            return None

        mock_acto_cond.objects.filter.side_effect = lambda **kw: MagicMock(
            first=lambda: _get(**kw)
        )

        resolved = resolve_condition_pairs_for_kardex(
            "K162-2026",
            [("043", "6027"), ("049", "6027")],
        )

        self.assertEqual(resolved, [("049", "6028")])

    @patch("notaria.services.kardex_acto_cleanup.models.Actocondicion")
    @patch("notaria.services.kardex_acto_cleanup.active_detalle_item_by_acto")
    def test_remaps_stale_item_to_current_detalle(self, mock_detalle, mock_acto_cond):
        mock_detalle.return_value = {"028": "6028"}
        mock_acto_cond.objects.filter.return_value.first.return_value = MagicMock(
            idtipoacto="028"
        )

        resolved = resolve_condition_pairs_for_kardex(
            "K162-2026",
            [("050", "6027")],
        )

        self.assertEqual(resolved, [("050", "6028")])


class PurgeOrphanContratantesxactoTests(SimpleTestCase):
    @patch("notaria.services.kardex_acto_cleanup.rebuild_contratantes_condicion_for_kardex")
    @patch("notaria.services.kardex_acto_cleanup._sync_contratantes_condicion")
    @patch("notaria.services.kardex_acto_cleanup.delete_kardex_acto_related")
    @patch("notaria.services.kardex_acto_cleanup.models.DetalleActosKardex")
    @patch("notaria.services.kardex_acto_cleanup.models.Contratantesxacto")
    @patch("notaria.services.kardex_acto_cleanup.active_idtipoactos_for_kardex")
    def test_purges_orphan_acto_and_stale_item(
        self,
        mock_active,
        mock_cxa,
        mock_detalle,
        mock_delete_related,
        mock_sync,
        mock_rebuild,
    ):
        mock_active.return_value = {"028"}
        mock_detalle.objects.filter.return_value = [
            MagicMock(item=6028, idtipoacto="028")
        ]

        stale_qs = MagicMock()
        stale_row = MagicMock(idcontratante="1", idcondicion="050", item=6027)
        stale_qs.__iter__ = lambda self: iter([stale_row])
        stale_qs.delete.return_value = (1, {})

        filter_qs = MagicMock()
        filter_qs.values_list.return_value.distinct.return_value = ["030", "028"]
        filter_qs.exclude.return_value = stale_qs
        mock_cxa.objects.filter.return_value = filter_qs

        mock_delete_related.return_value = {"contratantesxacto": 2}
        mock_sync.return_value = 1
        mock_rebuild.return_value = 1

        counts = purge_orphan_contratantesxacto_for_kardex("K162-2026")

        mock_delete_related.assert_called_once_with(
            kardex="K162-2026", idtipoacto="030"
        )
        self.assertEqual(counts["contratantesxacto"], 2)
        self.assertEqual(counts["contratantesxacto_stale_item"], 1)
