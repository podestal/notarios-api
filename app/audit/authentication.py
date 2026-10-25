from rest_framework_simplejwt.authentication import JWTAuthentication

from audit.context import set_actor


class AuditJWTAuthentication(JWTAuthentication):
    """JWT auth that also stores the user for kardex change logs.

    DRF authenticates after Django middleware, so the audit middleware still
    sees an anonymous request. Setting the actor here is what actually gets
    written to user_id / username.
    """

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is not None:
            user, _token = result
            set_actor(user, source=getattr(request, "path", "") or "")
        return result
