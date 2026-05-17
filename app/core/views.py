from django.contrib.auth import get_user_model
from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated

from .serializers import UserSummarySerializer

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
