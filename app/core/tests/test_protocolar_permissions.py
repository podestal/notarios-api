from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.urls import reverse
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APITestCase

from core.protocolar_permissions import (
    PROTOCOLAR_DENIED_MESSAGE,
    PROTOCOLAR_NAMES,
    PROTOCOLAR_TIPKARS,
    denied_from_permissions,
    denied_tipkars,
    ensure_protocolar_permission,
    normalize_denied,
    protocolar_permissions_payload,
    stored_denied_tipkars,
    user_can_protocolar,
)

User = get_user_model()


class TestProtocolarPermissionHelpers(APITestCase):
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
        self.assertEqual(self.user.protocolar_denied, [])

    def test_normalize_denied_keeps_valid_unique_tipkars(self):
        self.assertEqual(normalize_denied([5, "1", 1, 99, "x", None]), [5, 1])
        self.assertEqual(normalize_denied(None), [])
        self.assertEqual(normalize_denied(""), [])

    def test_default_user_can_do_all_protocolares(self):
        for tipkar in PROTOCOLAR_TIPKARS:
            self.assertTrue(user_can_protocolar(self.user, tipkar))
        self.assertEqual(denied_tipkars(self.user), [])

    def test_denied_tipkar_blocks_regular_user(self):
        self.user.protocolar_denied = [5]
        self.user.save(update_fields=["protocolar_denied"])

        self.assertTrue(user_can_protocolar(self.user, 1))
        self.assertFalse(user_can_protocolar(self.user, 5))
        self.assertEqual(denied_tipkars(self.user), [5])

    def test_superuser_bypasses_denied_flags(self):
        self.superuser.protocolar_denied = [1, 5]
        self.superuser.save(update_fields=["protocolar_denied"])

        self.assertTrue(user_can_protocolar(self.superuser, 5))
        self.assertEqual(denied_tipkars(self.superuser), [])
        self.assertEqual(stored_denied_tipkars(self.superuser), [1, 5])

    def test_anonymous_cannot_protocolar(self):
        self.assertFalse(user_can_protocolar(AnonymousUser(), 1))
        self.assertFalse(user_can_protocolar(None, 1))

    def test_payload_defaults_all_allowed(self):
        payload = protocolar_permissions_payload(self.user)
        self.assertEqual(len(payload), 5)
        self.assertTrue(all(item["allowed"] for item in payload))
        self.assertEqual(
            [item["idtipkar"] for item in payload],
            list(PROTOCOLAR_TIPKARS),
        )
        self.assertEqual(payload[0]["name"], PROTOCOLAR_NAMES[1])

    def test_payload_reflects_stored_denied_for_superuser(self):
        self.superuser.protocolar_denied = [3]
        payload = protocolar_permissions_payload(self.superuser)
        transferencias = next(item for item in payload if item["idtipkar"] == 3)
        self.assertFalse(transferencias["allowed"])

    def test_denied_from_permissions(self):
        denied = denied_from_permissions(
            [
                {"idtipkar": 1, "allowed": True},
                {"idtipkar": 5, "allowed": False},
                {"idtipkar": 99, "allowed": False},
            ]
        )
        self.assertEqual(denied, [5])

    def test_ensure_raises_permission_denied(self):
        self.user.protocolar_denied = [2]
        with self.assertRaises(PermissionDenied) as ctx:
            ensure_protocolar_permission(self.user, 2)
        self.assertEqual(str(ctx.exception), PROTOCOLAR_DENIED_MESSAGE)
        ensure_protocolar_permission(self.user, 1)


class TestAdminProtocolarPermissions(APITestCase):
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

    def test_list_includes_all_allowed_protocolar_permissions(self):
        response = self.client.get(reverse("admin-users-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        row = next(item for item in response.data if item["username"] == "jperez")
        perms = row["protocolar_permissions"]
        self.assertEqual(len(perms), 5)
        self.assertTrue(all(item["allowed"] for item in perms))

    def test_patch_denies_and_restores_protocolares(self):
        response = self.client.patch(
            self.detail_url,
            {
                "protocolar_permissions": [
                    {"idtipkar": 1, "allowed": True},
                    {"idtipkar": 2, "allowed": True},
                    {"idtipkar": 3, "allowed": False},
                    {"idtipkar": 4, "allowed": True},
                    {"idtipkar": 5, "allowed": False},
                ]
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.target.refresh_from_db()
        self.assertEqual(self.target.protocolar_denied, [3, 5])

        by_id = {item["idtipkar"]: item["allowed"] for item in response.data["protocolar_permissions"]}
        self.assertTrue(by_id[1])
        self.assertFalse(by_id[3])
        self.assertFalse(by_id[5])

        restore = self.client.patch(
            self.detail_url,
            {
                "protocolar_permissions": [
                    {"idtipkar": tipkar, "allowed": True}
                    for tipkar in PROTOCOLAR_TIPKARS
                ]
            },
            format="json",
        )
        self.assertEqual(restore.status_code, status.HTTP_200_OK)
        self.target.refresh_from_db()
        self.assertEqual(self.target.protocolar_denied, [])
