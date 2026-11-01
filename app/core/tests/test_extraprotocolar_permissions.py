from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.urls import reverse
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APITestCase

from core.extraprotocolar_permissions import (
    EXTRAPROTOCOLAR_DENIED_MESSAGE,
    EXTRAPROTOCOLAR_NAMES,
    EXTRAPROTOCOLAR_TYPES,
    denied_extras,
    denied_from_permissions,
    ensure_extraprotocolar_permission,
    extraprotocolar_permissions_payload,
    normalize_denied,
    stored_denied_extras,
    user_can_extraprotocolar,
)

User = get_user_model()


class TestExtraProtocolarPermissionHelpers(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="clerk",
            password="secret123",
            email="clerk@example.com",
        )
        self.superuser = User.objects.create_superuser(
            username="admin",
            password="secret123",
            email="admin@example.com",
        )

    def test_new_users_have_empty_denied_list(self):
        self.assertEqual(self.user.extraprotocolar_denied, [])

    def test_normalize_denied_keeps_valid_unique_keys(self):
        self.assertEqual(
            normalize_denied(["cartas", "cartas", "unknown", "libros", None]),
            ["cartas", "libros"],
        )
        self.assertEqual(normalize_denied(None), [])
        self.assertEqual(normalize_denied(""), [])

    def test_default_user_can_do_all_extras(self):
        for extra_type in EXTRAPROTOCOLAR_TYPES:
            self.assertTrue(user_can_extraprotocolar(self.user, extra_type))
        self.assertEqual(denied_extras(self.user), [])

    def test_denied_key_blocks_regular_user(self):
        self.user.extraprotocolar_denied = ["cartas"]
        self.user.save(update_fields=["extraprotocolar_denied"])

        self.assertTrue(user_can_extraprotocolar(self.user, "libros"))
        self.assertFalse(user_can_extraprotocolar(self.user, "cartas"))
        self.assertEqual(denied_extras(self.user), ["cartas"])

    def test_superuser_bypasses_denied_flags(self):
        self.superuser.extraprotocolar_denied = ["cartas", "poderes"]
        self.superuser.save(update_fields=["extraprotocolar_denied"])

        self.assertTrue(user_can_extraprotocolar(self.superuser, "cartas"))
        self.assertEqual(denied_extras(self.superuser), [])
        self.assertEqual(stored_denied_extras(self.superuser), ["cartas", "poderes"])

    def test_anonymous_cannot_extraprotocolar(self):
        self.assertFalse(user_can_extraprotocolar(AnonymousUser(), "cartas"))
        self.assertFalse(user_can_extraprotocolar(None, "cartas"))

    def test_payload_defaults_all_allowed(self):
        payload = extraprotocolar_permissions_payload(self.user)
        self.assertEqual(len(payload), len(EXTRAPROTOCOLAR_TYPES))
        self.assertTrue(all(item["allowed"] for item in payload))
        self.assertEqual([item["key"] for item in payload], list(EXTRAPROTOCOLAR_TYPES))
        self.assertEqual(payload[0]["name"], EXTRAPROTOCOLAR_NAMES["permisos_viaje"])

    def test_denied_from_permissions(self):
        denied = denied_from_permissions(
            [
                {"key": "cartas", "allowed": True},
                {"key": "libros", "allowed": False},
                {"key": "unknown", "allowed": False},
            ]
        )
        self.assertEqual(denied, ["libros"])

    def test_ensure_raises_permission_denied(self):
        self.user.extraprotocolar_denied = ["poderes"]
        with self.assertRaises(PermissionDenied) as ctx:
            ensure_extraprotocolar_permission(self.user, "poderes")
        self.assertEqual(str(ctx.exception), EXTRAPROTOCOLAR_DENIED_MESSAGE)
        ensure_extraprotocolar_permission(self.user, "cartas")


class TestAdminExtraProtocolarPermissions(APITestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="admin",
            password="secret123",
            email="admin@example.com",
        )
        self.target = User.objects.create_user(
            username="jperez",
            password="secret123",
            email="jperez@example.com",
        )
        self.detail_url = reverse(
            "admin-users-detail",
            kwargs={"idusuario": self.target.idusuario},
        )
        self.client.force_authenticate(user=self.superuser)

    def test_list_includes_all_allowed_extra_permissions(self):
        response = self.client.get(reverse("admin-users-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        row = next(item for item in response.data if item["username"] == "jperez")
        perms = row["extraprotocolar_permissions"]
        self.assertEqual(len(perms), len(EXTRAPROTOCOLAR_TYPES))
        self.assertTrue(all(item["allowed"] for item in perms))

    def test_patch_denies_and_restores_extras(self):
        response = self.client.patch(
            self.detail_url,
            {
                "extraprotocolar_permissions": [
                    {"key": "cartas", "allowed": False},
                    {"key": "libros", "allowed": True},
                    {"key": "poderes", "allowed": False},
                ]
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.target.refresh_from_db()
        self.assertEqual(self.target.extraprotocolar_denied, ["cartas", "poderes"])

        by_key = {
            item["key"]: item["allowed"]
            for item in response.data["extraprotocolar_permissions"]
        }
        self.assertFalse(by_key["cartas"])
        self.assertTrue(by_key["libros"])
        self.assertFalse(by_key["poderes"])

        restore = self.client.patch(
            self.detail_url,
            {
                "extraprotocolar_permissions": [
                    {"key": key, "allowed": True} for key in EXTRAPROTOCOLAR_TYPES
                ]
            },
            format="json",
        )
        self.assertEqual(restore.status_code, status.HTTP_200_OK)
        self.target.refresh_from_db()
        self.assertEqual(self.target.extraprotocolar_denied, [])
