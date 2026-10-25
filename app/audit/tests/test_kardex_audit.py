from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from audit.context import clear_actor, get_actor, set_actor
from audit.query import kardex_logs_queryset
from audit.labels import humanize_kardex_changes
from audit.services import (
    _norm,
    build_payload,
    create_changes,
    delete_changes,
    diff_snapshots,
    drop_hidden_log_fields,
    drop_unchanged_log_fields,
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

    def test_norm_treats_numeric_ids_as_equal(self):
        self.assertEqual(_norm(360), _norm("360"))
        self.assertEqual(_norm(26), _norm("26"))
        self.assertEqual(
            diff_snapshots({"fktemplate": 360}, {"fktemplate": "360"}),
            {},
        )

    def test_same_plantilla_label_is_not_a_change(self):
        self.assertEqual(
            drop_unchanged_log_fields(
                {
                    "Plantilla": {
                        "old": "COMPRA VENTA INMUEBLE PN PN +",
                        "new": "COMPRA VENTA INMUEBLE PN PN +",
                    },
                    "Contrato": {"old": "A", "new": "B"},
                }
            ),
            {"Contrato": {"old": "A", "new": "B"}},
        )

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

    def test_hidden_kardex_log_fields_are_dropped(self):
        changes = {
            "contrato": {"old": "A", "new": "B"},
            "estado_sisgen": {"old": 1, "new": 0},
            "pagado": {"old": 0, "new": 1},
            "visita": {"old": 0, "new": 1},
            "codactos": {"old": None, "new": "030"},
        }
        self.assertEqual(
            drop_hidden_log_fields(changes, "kardex"),
            {"contrato": {"old": "A", "new": "B"}},
        )
        self.assertEqual(drop_hidden_log_fields(changes, "contratantes"), changes)

    def test_hidden_detalle_actos_fields_are_dropped(self):
        changes = {
            "kardex": {"old": None, "new": "K148-2026"},
            "idtipoacto": {"old": None, "new": "030"},
            "actosunat": {"old": None, "new": "04"},
            "actouif": {"old": None, "new": "012"},
            "idtipkar": {"old": None, "new": 1},
            "desacto": {"old": None, "new": "COMPRA VENTA DE INMUEBLE"},
        }
        self.assertEqual(
            drop_hidden_log_fields(changes, "detalle_actos_kardex"),
            {
                "actosunat": {"old": None, "new": "04"},
                "actouif": {"old": None, "new": "012"},
                "desacto": {"old": None, "new": "COMPRA VENTA DE INMUEBLE"},
            },
        )

    @patch("audit.labels._template_label", side_effect=lambda value, cache: "COMPRA VENTA INMUEBLE PN PN +")
    def test_unchanged_plantilla_id_is_dropped(self, _template):
        labeled = humanize_kardex_changes(
            {"fktemplate": {"old": 360, "new": "360"}, "contrato": {"old": "A", "new": "B"}}
        )
        self.assertNotIn("Plantilla", labeled)
        self.assertEqual(labeled["Contrato"]["new"], "B")

    @patch("audit.labels._template_label", side_effect=lambda value, cache: "Minuta compra venta")
    @patch("audit.labels._user_label", side_effect=lambda value, cache: "Ana Torres")
    @patch("audit.labels._tipo_kardex_label", side_effect=lambda value, cache: "Escritura")
    def test_kardex_changes_use_field_descriptions(self, _tipo, _user, _template):
        labeled = humanize_kardex_changes(
            {
                "idtipkar": {"old": None, "new": 1},
                "fechaingreso": {"old": None, "new": "2026-10-25"},
                "codactos": {"old": None, "new": "030"},
                "contrato": {"old": None, "new": "COMPRA VENTA DE INMUEBLE /"},
                "idusuario": {"old": None, "new": 26},
                "responsable": {"old": None, "new": 26},
                "recepcion": {"old": None, "new": 26},
                "fktemplate": {"old": None, "new": 360},
            }
        )
        self.assertNotIn("Actos", labeled)
        self.assertNotIn("codactos", labeled)
        self.assertEqual(labeled["Tipo de kardex"]["new"], "Escritura")
        self.assertEqual(labeled["Fecha de ingreso"]["new"], "2026-10-25")
        self.assertEqual(labeled["Contrato"]["new"], "COMPRA VENTA DE INMUEBLE /")
        self.assertEqual(labeled["Usuario"]["new"], "Ana Torres")
        self.assertEqual(labeled["Responsable"]["new"], "Ana Torres")
        self.assertEqual(labeled["Recepción"]["new"], "Ana Torres")
        self.assertEqual(labeled["Plantilla"]["new"], "Minuta compra venta")

    @patch("audit.labels._abogado_label", side_effect=lambda value, cache: "PEREZ RAMOS JUAN")
    def test_abogado_uses_name_instead_of_id(self, _abogado):
        labeled = humanize_kardex_changes(
            {"idabogado": {"old": None, "new": "0000000004"}}
        )
        self.assertEqual(labeled["Abogado"]["new"], "PEREZ RAMOS JUAN")

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


class AuditJWTAuthenticationTests(SimpleTestCase):
    def tearDown(self):
        clear_actor()

    def test_authenticate_stores_actor_from_jwt_user(self):
        from audit.authentication import AuditJWTAuthentication

        jwt_user = SimpleNamespace(is_authenticated=True, idusuario=26, username="galaxia69")
        request = SimpleNamespace(path="/api/kardex/5660/")
        auth = AuditJWTAuthentication()
        result = (jwt_user, "token")

        with patch(
            "rest_framework_simplejwt.authentication.JWTAuthentication.authenticate",
            return_value=result,
        ):
            self.assertEqual(auth.authenticate(request), result)

        self.assertEqual(get_actor()["username"], "galaxia69")
        self.assertEqual(get_actor()["user_id"], 26)


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
    def test_hidden_only_kardex_update_is_skipped(self, enqueue):
        instance = SimpleNamespace(
            pk=1,
            kardex="KAR1-2026",
            idkardex=1,
            _meta=SimpleNamespace(db_table="kardex"),
        )
        enqueue_instance_change(
            instance,
            action="update",
            old={"pagado": 0, "estado_sisgen": 1, "contrato": "A"},
            new={"pagado": 1, "estado_sisgen": 0, "contrato": "A"},
        )
        enqueue.assert_not_called()

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
