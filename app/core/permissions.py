from rest_framework.permissions import BasePermission


class IsSuperuser(BasePermission):
    """Allow access only when the authenticated user is a Django superuser."""

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_superuser)


class IsStaffOrSuperuser(BasePermission):
    """Allow access for Django staff or superuser (ops / admin tools)."""

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (user.is_staff or user.is_superuser)
        )
