from audit.context import clear_actor, set_actor


class KardexAuditMiddleware:
    """Store the JWT user on thread-local so signals can attribute changes."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        source = ""
        try:
            source = request.path or ""
        except Exception:
            source = ""
        try:
            set_actor(user, source=source)
            return self.get_response(request)
        finally:
            clear_actor()
