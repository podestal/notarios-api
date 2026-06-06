from django.contrib.auth import get_user_model
from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated

from .permissions import IsSuperuser
from .serializers import AdminUserSerializer, UserSummarySerializer

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
    Superuser-only list and update of core users (taxes linking, admin UI).
    """

    serializer_class = AdminUserSerializer
    # permission_classes = [IsAuthenticated, IsSuperuser]
    lookup_field = 'idusuario'
    http_method_names = ['get', 'head', 'options', 'put', 'patch']

    def get_queryset(self):
        return User.objects.all().order_by('username')
