from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()


class TestUserSummaryList(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="admin",
            password="secret123",
            email="admin@example.com",
            first_name="Ana",
            last_name="Garcia",
        )
        User.objects.create_user(
            username="inactive",
            password="secret123",
            email="inactive@example.com",
            is_active=False,
        )
        self.client.force_authenticate(user=self.user)

    def test_list_returns_limited_fields_for_active_users(self):
        url = reverse("users-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        row = response.data[0]
        self.assertEqual(
            set(row.keys()),
            {"idusuario", "username", "first_name", "last_name", "email"},
        )
        self.assertEqual(row["username"], "admin")
        self.assertEqual(row["first_name"], "Ana")
        self.assertEqual(row["last_name"], "Garcia")
        self.assertEqual(row["email"], "admin@example.com")
        self.assertNotIn("password", row)

    def test_list_requires_authentication(self):
        self.client.force_authenticate(user=None)
        response = self.client.get(reverse("users-list"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
