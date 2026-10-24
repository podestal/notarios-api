from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from audit.context import clear_actor, get_actor, set_actor
from audit.query import kardex_logs_queryset
from audit.services import (
    build_payload,
    create_changes,
    delete_changes,
    diff_snapshots,
    enqueue_instance_change,
    jsonable,
    snapshot_instance,
)


class JsonableAndDiffTests(SimpleTestCase):
    def test_jsonable_normalizes_types(self):
        self.assertEqual(jsonable(Decimal("10.50")), "10.50")
        self.assertEqual(jsonable(date(2026, 4, 15)), "2026-04-15")
        self.assertEqual(jsonable(None), None)
        self.assertEqual(jsonable("hola"), "hola")

    def test_diff_ignores_blank_vs_none(self):
        changes = diff_snapshots({"contrato": None, "nc": "1"}, {"contrato": "", "nc": "1"})
        self.assertEqual(changes, {})

    def test_diff_reports_changed_fields_only(self):
        changes = diff_snapshots(
            {"numescritura": "10", "contrato": "A"},
            {"numescritura": "11", "contrato": "A"},
        )
        self.assertEqual(changes, {"numescritura": {"old": "10", "new": "11"}})

    def test_create_and_delete_changes_skip_empty(self):
        self.assertEqual(create_changes({"a": "x", "b": ""}), {"a": {"old": None, "new": "x"}})
        self.assertEqual(delete_changes({"a": "x", "b": None}), {"a": {"old": "x", "new": None}})

    def test_snapshot_skips_primary_key(self):
        field_pk = SimpleNamespace(primary_key=True, name="idkardex", value_from_object=lambda inst: 9)
        field_name = SimpleNamespace(
            primary_key=False, name="kardex", value_from_object=lambda inst: "KAR1-2026"
        )
        instance = SimpleNamespace(_meta=SimpleNamespace(concrete_fields=[field_pk, field_name]))
        self.assertEqual(snapshot_instance(instance), {"kardex": "KAR1-2026"})


class ActorContextTests(SimpleTestCase):
    def tearDown(self):
        clear_actor()

    def test_set_actor_from_jwt_user(self):
        user = SimpleNamespace(is_authenticated=True, idusuario=17, username="ana")
        set_actor(user, source="/api/kardex/")
        self.assertEqual(get_actor(), {"user_id": 17, "username": "ana", "source": "/api/kardex/"})

    def test_anonymous_user_is_empty(self):
        user = SimpleNamespace(is_authenticated=False, idusuario=1, username="x")
        set_actor(user, source="/api/kardex/")
        actor = get_actor()
        self.assertIsNone(actor["user_id"])
        self.assertEqual(actor["username"], "")


class EnqueueTests(SimpleTestCase):
    def tearDown(self):
        clear_actor()

    @patch("audit.tasks.persist_kardex_change.delay")
    def test_enqueue_uses_celery(self, delay):
        from audit.services import _enqueue_now

        _enqueue_now({"table_name": "kardex", "action": "update", "changes": {}})
        delay.assert_called_once()

    @patch("audit.services.persist_kardex_change_sync")
    @patch("audit.tasks.persist_kardex_change.delay", side_effect=RuntimeError("broker down"))
    def test_enqueue_falls_back_when_broker_is_down(self, delay, persist):
        from audit.services import _enqueue_now

        _enqueue_now({"table_name": "kardex", "action": "create", "changes": {}})
        persist.assert_called_once()

    @patch("audit.services.enqueue_kardex_change")
    def test_instance_update_without_changes_is_skipped(self, enqueue):
        instance = SimpleNamespace(
            pk=1,
            kardex="KAR1-2026",
            idkardex=1,
            _meta=SimpleNamespace(db_table="kardex"),
        )
        enqueue_instance_change(
            instance,
            action="update",
            old={"numescritura": "1"},
            new={"numescritura": "1"},
        )
        enqueue.assert_not_called()

    def test_build_payload_includes_actor(self):
        user = SimpleNamespace(is_authenticated=True, idusuario=4, username="lucia")
        set_actor(user, source="/api/contratantes/")
        payload = build_payload(
            table_name="contratantes",
            record_pk="0001",
            action="create",
            changes={"firma": {"old": None, "new": "SI"}},
            kardex="KAR1-2026",
        )
        self.assertEqual(payload["user_id"], 4)
        self.assertEqual(payload["username"], "lucia")
        self.assertEqual(payload["source"], "/api/contratantes/")


class QueryTests(SimpleTestCase):
    def test_filters_are_applied(self):
        qs = MagicMock()
        qs.filter.return_value = qs
        with patch("audit.query.KardexChangeLog.objects") as objects:
            objects.all.return_value = qs
            kardex_logs_queryset(
                {
                    "kardex": "KAR1-2026",
                    "table": "cliente2",
                    "action": "update",
                    "user_id": "9",
                    "dateFrom": "01/04/2026",
                    "dateTo": "2026-10-31",
                }
            )
        kwargs_used = [call.kwargs for call in qs.filter.call_args_list]
        self.assertIn({"kardex": "KAR1-2026"}, kwargs_used)
        self.assertIn({"table_name": "cliente2"}, kwargs_used)
        self.assertIn({"action": "update"}, kwargs_used)
        self.assertIn({"user_id": 9}, kwargs_used)


class LogsEndpointTests(SimpleTestCase):
    def test_logs_require_kardex(self):
        from rest_framework.request import Request
        from rest_framework.test import APIRequestFactory

        from notaria.views import KardexViewSet

        request = Request(APIRequestFactory().get("/api/kardex/logs/"))
        view = KardexViewSet()
        view.request = request
        view.format_kwarg = None
        view.action = "logs"
        response = view.logs(request)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "kardex is required")

    def test_logs_actions_are_superuser_only(self):
        from core.permissions import IsSuperuser
        from notaria.views import KardexViewSet
        from rest_framework.permissions import IsAuthenticated

        for action_name in ("logs", "logs_for_kardex"):
            action = getattr(KardexViewSet, action_name)
            self.assertEqual(
                action.kwargs["permission_classes"],
                [IsAuthenticated, IsSuperuser],
            )
