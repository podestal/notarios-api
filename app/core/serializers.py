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

from .protocolar_permissions import (
    denied_from_permissions,
    protocolar_catalog,
    protocolar_permissions_payload,
)

user = get_user_model()


class ProtocolarPermissionSerializer(serializers.Serializer):
    idtipkar = serializers.IntegerField()
    name = serializers.CharField(required=False, allow_blank=True)
    allowed = serializers.BooleanField()


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
    protocolar_permissions = serializers.SerializerMethodField()

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
            'protocolar_permissions',
        ]

    def get_protocolar_permissions(self, obj):
        return protocolar_permissions_payload(obj)


class AdminUserSerializer(serializers.ModelSerializer):
    """Superuser-only user management for taxes linking and admin UI."""

    taxes_usuario_id = serializers.IntegerField(required=False, allow_null=True)
    negocio_id = serializers.IntegerField(required=False, allow_null=True)
    protocolar_permissions = ProtocolarPermissionSerializer(
        many=True,
        required=False,
        write_only=True,
    )

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
            'protocolar_permissions',
        ]
        read_only_fields = [
            'idusuario',
            'username',
            'date_joined',
            'last_login',
        ]

    def validate_is_active(self, value):
        request = self.context.get("request")
        if (
            request
            and getattr(request, "user", None)
            and self.instance is not None
            and self.instance.pk == request.user.pk
            and value is False
        ):
            raise serializers.ValidationError(
                "No puede desactivar su propio usuario."
            )
        return value

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if not hasattr(self, "_protocolar_catalog"):
            self._protocolar_catalog = protocolar_catalog()
        data["protocolar_permissions"] = protocolar_permissions_payload(
            instance,
            catalog=self._protocolar_catalog,
        )
        return data

    def update(self, instance, validated_data):
        permissions = validated_data.pop("protocolar_permissions", None)
        instance = super().update(instance, validated_data)
        if permissions is not None:
            instance.protocolar_denied = denied_from_permissions(permissions)
            instance.save(update_fields=["protocolar_denied"])
        return instance


class UserSummarySerializer(serializers.ModelSerializer):
    """
    Safe, read-only user fields for dropdowns and display labels.
    Does not expose passwords or legacy usuarios data.
    """

    class Meta:
        model = user
        fields = ['idusuario', 'username', 'first_name', 'last_name', 'email']
        read_only_fields = fields
