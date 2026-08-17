from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.test import APITestCase

from taxes.serializers import CreateTaxesUsuarioSerializer
from taxes.services.usuario import build_nombre_completo, create_taxes_usuario

User = get_user_model()


class BuildNombreCompletoTests(SimpleTestCase):
    def test_joins_names(self):
        self.assertEqual(
            build_nombre_completo(
                nombres="Juan",
                apellido_paterno="Perez",
                apellido_materno="Garcia",
            ),
            "Juan Perez Garcia",
        )

    def test_falls_back_to_razon_social(self):
        self.assertEqual(
            build_nombre_completo(razon_social="Notaria SAC"),
            "Notaria SAC",
        )

    def test_raises_when_empty(self):
        with self.assertRaises(ValidationError):
            build_nombre_completo()


class CreateTaxesUsuarioSerializerTests(SimpleTestCase):
    def test_requires_persona(self):
        serializer = CreateTaxesUsuarioSerializer(
            data={"usuario": "jperez", "negocio_id": 1}
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("persona", serializer.errors)

    def test_accepts_nested_persona(self):
        serializer = CreateTaxesUsuarioSerializer(
            data={
                "usuario": "jperez",
                "negocio_id": 1,
                "persona": {
                    "nombres": "Juan",
                    "apellido_paterno": "Perez",
                    "numero_documento": "12345678",
                },
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)


class CreateTaxesUsuarioServiceTests(SimpleTestCase):
    def _actor(self, negocio_id=1):
        return SimpleNamespace(negocio_id=negocio_id)

    @patch("taxes.services.usuario.transaction.atomic")
    @patch("taxes.services.usuario.next_serial_id")
    @patch("taxes.services.usuario.Usuarios")
    @patch("taxes.services.usuario.Personas")
    @patch("taxes.services.usuario.Documentos")
    def test_creates_persona_from_given_data_when_dni_is_new(
        self,
        mock_documentos,
        mock_personas,
        mock_usuarios,
        mock_next_id,
        _atomic,
    ):
        mock_documentos.objects.using.return_value.filter.return_value.exists.return_value = (
            True
        )
        mock_personas.objects.using.return_value.filter.return_value.first.return_value = (
            None
        )
        persona = SimpleNamespace(
            id_persona=10,
            nombres="Juan",
            apellido_paterno="Perez",
            apellido_materno="Garcia",
            email="juan@notaria.pe",
        )
        mock_personas.objects.using.return_value.create.return_value = persona
        mock_usuarios.objects.using.return_value.filter.return_value.exists.return_value = (
            False
        )
        mock_usuarios.objects.using.return_value.create.return_value = SimpleNamespace(
            id_usuario=5,
            usuario="jperez",
            negocio_id=1,
            persona_id=10,
        )
        mock_next_id.side_effect = [10, 5]

        result = create_taxes_usuario(
            actor=self._actor(),
            usuario="jperez",
            email="juan@notaria.pe",
            negocio_id=1,
            persona={
                "nombres": "Juan",
                "apellido_paterno": "Perez",
                "apellido_materno": "Garcia",
                "numero_documento": "12345678",
                "documento": 1,
            },
        )

        self.assertEqual(result["persona"].id_persona, 10)
        self.assertEqual(result["usuario"].id_usuario, 5)
        self.assertIsNone(result["core_user"])
        kwargs = mock_personas.objects.using.return_value.create.call_args.kwargs
        self.assertEqual(kwargs["nombres"], "Juan")
        self.assertEqual(kwargs["apellido_paterno"], "Perez")
        self.assertEqual(kwargs["numero_documento"], "12345678")

    @patch("taxes.services.usuario.transaction.atomic")
    @patch("taxes.services.usuario.Personas")
    @patch("taxes.services.usuario.Usuarios")
    def test_existing_dni_errors_and_does_not_create_user(
        self, mock_usuarios, mock_personas, _atomic
    ):
        mock_usuarios.objects.using.return_value.filter.return_value.exists.return_value = (
            False
        )
        mock_personas.objects.using.return_value.filter.return_value.first.return_value = (
            SimpleNamespace(
                id_persona=4929,
                nombre_completo="Sandra Beatriz Gonzales Caceres",
            )
        )
        with self.assertRaises(ValidationError) as ctx:
            create_taxes_usuario(
                actor=self._actor(),
                usuario="sgonzales",
                persona={
                    "nombres": "Someone Else",
                    "numero_documento": "12345678",
                },
            )
        self.assertIn("4929", str(ctx.exception.detail))
        mock_personas.objects.using.return_value.create.assert_not_called()
        mock_usuarios.objects.using.return_value.create.assert_not_called()

    @patch("taxes.services.usuario.transaction.atomic")
    @patch("taxes.services.usuario.next_serial_id")
    @patch("taxes.services.usuario.Usuarios")
    @patch("taxes.services.usuario.Personas")
    @patch("taxes.services.usuario.Documentos")
    @patch("taxes.services.usuario.User")
    def test_links_existing_core_user_without_using_their_name(
        self,
        mock_user,
        mock_documentos,
        mock_personas,
        mock_usuarios,
        mock_next_id,
        _atomic,
    ):
        mock_documentos.objects.using.return_value.filter.return_value.exists.return_value = (
            True
        )
        mock_personas.objects.using.return_value.filter.return_value.first.return_value = (
            None
        )
        mock_personas.objects.using.return_value.create.return_value = SimpleNamespace(
            id_persona=11,
            nombres="Ana",
            apellido_paterno="Garcia",
            email="ana@notaria.pe",
        )
        mock_usuarios.objects.using.return_value.filter.return_value.exists.return_value = (
            False
        )
        taxes_user = SimpleNamespace(
            id_usuario=5,
            usuario="agarcia",
            negocio_id=1,
        )
        mock_usuarios.objects.using.return_value.create.return_value = taxes_user
        mock_next_id.side_effect = [11, 5]
        core_user = SimpleNamespace(
            idusuario=3,
            first_name="Sandra",
            last_name="Gonzales",
            taxes_usuario_id=None,
            negocio_id=None,
        )
        core_user.save = lambda **kwargs: None
        mock_user.objects.filter.return_value.first.return_value = core_user

        result = create_taxes_usuario(
            actor=self._actor(),
            usuario="agarcia",
            idusuario=3,
            persona={
                "nombres": "Ana",
                "apellido_paterno": "Garcia",
                "numero_documento": "87654321",
                "documento": 1,
            },
        )

        kwargs = mock_personas.objects.using.return_value.create.call_args.kwargs
        self.assertEqual(kwargs["nombres"], "Ana")
        self.assertEqual(kwargs["apellido_paterno"], "Garcia")
        self.assertEqual(result["core_user"].idusuario, 3)
        self.assertEqual(core_user.taxes_usuario_id, 5)

    @patch("taxes.services.usuario.transaction.atomic")
    @patch("taxes.services.usuario.Usuarios")
    def test_duplicate_usuario_is_rejected(self, mock_usuarios, _atomic):
        mock_usuarios.objects.using.return_value.filter.return_value.exists.return_value = (
            True
        )
        with self.assertRaises(ValidationError):
            create_taxes_usuario(
                actor=self._actor(),
                usuario="jperez",
                persona={"nombres": "Juan", "numero_documento": "12345678"},
            )

    def test_negocio_id_required(self):
        with self.assertRaises(ValidationError):
            create_taxes_usuario(
                actor=self._actor(negocio_id=None),
                usuario="jperez",
                persona={"nombres": "Juan", "numero_documento": "12345678"},
            )


class CreateTaxesUsuarioViewTests(APITestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="admin",
            password="secret123",
            email="admin@example.com",
            negocio_id=1,
        )
        self.regular = User.objects.create_user(
            username="staff",
            password="secret123",
            email="staff@example.com",
        )
        self.url = reverse("taxes-usuarios-list")

    def test_requires_superuser(self):
        self.client.force_authenticate(user=self.regular)
        response = self.client.post(
            self.url,
            {
                "usuario": "jperez",
                "persona": {
                    "nombres": "Juan",
                    "numero_documento": "12345678",
                },
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("taxes.views.CreateTaxesUsuarioResponseSerializer")
    @patch("taxes.views.create_taxes_usuario")
    def test_superuser_creates_user(self, mock_create, mock_response):
        mock_create.return_value = {
            "persona": object(),
            "usuario": object(),
            "core_user": None,
        }
        mock_response.return_value.data = {
            "persona": {"id_persona": 10},
            "usuario": {"id_usuario": 5, "usuario": "jperez"},
            "core_user": None,
        }
        self.client.force_authenticate(user=self.superuser)
        response = self.client.post(
            self.url,
            {
                "usuario": "jperez",
                "persona": {
                    "nombres": "Juan",
                    "apellido_paterno": "Perez",
                    "numero_documento": "12345678",
                },
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        kwargs = mock_create.call_args.kwargs
        self.assertEqual(kwargs["persona"]["nombres"], "Juan")
        self.assertNotIn("persona_id", kwargs)
