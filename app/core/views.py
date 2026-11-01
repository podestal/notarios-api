from django.contrib.auth import get_user_model
from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .permissions import IsStaffOrSuperuser, IsSuperuser
from .serializers import AdminUserSerializer, UserSummarySerializer
from .services.celery_status import celery_status_payload

User = get_user_model()


class UserSummaryViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    Read-only list of Django users with minimal fields.
    Replaces legacy GET /api/usuarios/ for UI pickers.
    """

    serializer_class = UserSummarySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return User.objects.filter(is_active=True).order_by('username')


class UserAdminViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """
    Staff can list users. Superuser can update taxes linking and protocolares.
    """

    serializer_class = AdminUserSerializer
    lookup_field = 'idusuario'
    http_method_names = ['get', 'head', 'options', 'put', 'patch']

    def get_permissions(self):
        if self.request.method in ('PUT', 'PATCH'):
            return [IsAuthenticated(), IsSuperuser()]
        return [IsAuthenticated(), IsStaffOrSuperuser()]

    def get_queryset(self):
        return User.objects.all().order_by('username')


class CeleryStatusView(APIView):
    """Beat schedule, next run times, and SUNAT outbox retries/failures."""

    permission_classes = [IsAuthenticated, IsStaffOrSuperuser]

    def get(self, request):
        return Response(celery_status_payload())
