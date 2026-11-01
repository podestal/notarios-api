from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()


class TestUserAdminViewSet(APITestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username='admin',
            password='secret123',
            email='admin@example.com',
        )
        self.regular_user = User.objects.create_user(
            username='clerk',
            password='secret123',
            email='clerk@example.com',
        )
        self.staff_user = User.objects.create_user(
            username='staff',
            password='secret123',
            email='staff@example.com',
            is_staff=True,
        )
        self.target = User.objects.create_user(
            username='jperez',
            password='secret123',
            email='jperez@example.com',
            first_name='Juan',
            last_name='Perez',
        )
        self.list_url = reverse('admin-users-list')
        self.detail_url = reverse('admin-users-detail', kwargs={'idusuario': self.target.idusuario})

    def test_list_requires_staff_or_superuser(self):
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_list_returns_users_for_staff(self):
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 4)

    def test_list_returns_all_users_for_superuser(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.get(self.list_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 4)
        row = next(item for item in response.data if item['username'] == 'jperez')
        self.assertIn('taxes_usuario_id', row)
        self.assertIn('negocio_id', row)
        self.assertIn('protocolar_permissions', row)
        self.assertEqual(len(row['protocolar_permissions']), 5)
        self.assertTrue(all(item['allowed'] for item in row['protocolar_permissions']))
        self.assertEqual(row['first_name'], 'Juan')

    def test_patch_updates_taxes_fields(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.patch(
            self.detail_url,
            {'taxes_usuario_id': 12, 'negocio_id': 1},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.target.refresh_from_db()
        self.assertEqual(self.target.taxes_usuario_id, 12)
        self.assertEqual(self.target.negocio_id, 1)
        self.assertEqual(response.data['taxes_usuario_id'], 12)
        self.assertEqual(response.data['negocio_id'], 1)

    def test_patch_denied_for_non_superuser(self):
        self.client.force_authenticate(user=self.regular_user)
        response = self.client.patch(
            self.detail_url,
            {'taxes_usuario_id': 99},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_patch_toggles_is_active(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.patch(
            self.detail_url,
            {'is_active': False},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)
        self.assertFalse(response.data['is_active'])

    def test_cannot_deactivate_self(self):
        self.client.force_authenticate(user=self.superuser)
        url = reverse('admin-users-detail', kwargs={'idusuario': self.superuser.idusuario})
        response = self.client.patch(url, {'is_active': False}, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.superuser.refresh_from_db()
        self.assertTrue(self.superuser.is_active)

    def test_username_is_read_only(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.patch(
            self.detail_url,
            {'username': 'changed'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.target.refresh_from_db()
        self.assertEqual(self.target.username, 'jperez')
