from djoser.serializers import UserSerializer as BasedUserSerializer, UserCreateSerializer
from rest_framework import serializers
from django.contrib.auth.models import Group
from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string

user = get_user_model()


class CreateUserSerializer(UserCreateSerializer):
    taxes_usuario_id = serializers.IntegerField(required=False, allow_null=True)
    negocio_id = serializers.IntegerField(required=False, allow_null=True)

    class Meta(UserCreateSerializer.Meta):
        fields = [
            'idusuario',
            'username',
            'email',
            'password',
            'notary',
            'taxes_usuario_id',
            'negocio_id',
            'first_name',
            'last_name',
        ]


class UserSerializer(BasedUserSerializer):
    class Meta(BasedUserSerializer.Meta):
        fields = [
            'idusuario',
            'username',
            'email',
            'notary',
            'taxes_usuario_id',
            'negocio_id',
            'first_name',
            'last_name',
            'is_staff',
            'is_superuser',
        ]


class AdminUserSerializer(serializers.ModelSerializer):
    """Superuser-only user management for taxes linking and admin UI."""

    taxes_usuario_id = serializers.IntegerField(required=False, allow_null=True)
    negocio_id = serializers.IntegerField(required=False, allow_null=True)

    class Meta:
        model = user
        fields = [
            'idusuario',
            'username',
            'email',
            'first_name',
            'last_name',
            'notary',
            'taxes_usuario_id',
            'negocio_id',
            'is_active',
            'is_staff',
            'is_superuser',
            'date_joined',
            'last_login',
        ]
        read_only_fields = [
            'idusuario',
            'username',
            'date_joined',
            'last_login',
        ]


class UserSummarySerializer(serializers.ModelSerializer):
    """
    Safe, read-only user fields for dropdowns and display labels.
    Does not expose passwords or legacy usuarios data.
    """

    class Meta:
        model = user
        fields = ['idusuario', 'username', 'first_name', 'last_name', 'email']
        read_only_fields = fields
