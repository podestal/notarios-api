"""Per-user extraprotocolar restrictions.

Empty ``User.extraprotocolar_denied`` means every extra type is allowed.
Superusers always pass enforcement, even if flags are stored as denied.
"""

from rest_framework.exceptions import PermissionDenied

EXTRAPROTOCOLAR_TYPES = (
    "permisos_viaje",
    "poderes",
    "cartas",
    "libros",
    "supervivencia_capaz",
    "supervivencia_incapaz",
    "domiciliario",
    "cambio_caracteristicas",
    "busqueda_avanzada",
)

EXTRAPROTOCOLAR_NAMES = {
    "permisos_viaje": "Cert. Autorización de viaje",
    "poderes": "Poderes Fuera de Registro",
    "cartas": "Cartas Notariales",
    "libros": "Cert. Apertura de Libros",
    "supervivencia_capaz": "Cert. Supervivencia Persona Capaz",
    "supervivencia_incapaz": "Cert. Supervivencia Persona Incapaz",
    "domiciliario": "Certificado Domiciliario",
    "cambio_caracteristicas": "Cambio de Características",
    "busqueda_avanzada": "Búsqueda Avanzada",
}

EXTRAPROTOCOLAR_DENIED_MESSAGE = (
    "No tiene permiso para este tipo de extraprotocolar."
)

EXTRAPROTOCOLAR_ACTION_TYPES = {
    "permiso_viaje_interior": "permisos_viaje",
    "permiso_viaje_exterior": "permisos_viaje",
    "poder_fuera_registro": "poderes",
    "poder_essalud": "poderes",
    "poder_onp": "poderes",
    "carta_notarial": "cartas",
    "cert_domiciliario": "domiciliario",
    "libro": "libros",
}


def normalize_denied(value):
    if not value:
        return []
    if isinstance(value, (str, bytes)):
        raw = [value.decode() if isinstance(value, bytes) else value]
    else:
        raw = list(value)
    denied = []
    for item in raw:
        key = str(item or "").strip()
        if key in EXTRAPROTOCOLAR_TYPES and key not in denied:
            denied.append(key)
    return denied


def stored_denied_extras(user):
    return normalize_denied(getattr(user, "extraprotocolar_denied", None))


def denied_extras(user):
    if user is None or not getattr(user, "is_authenticated", False):
        return list(EXTRAPROTOCOLAR_TYPES)
    if getattr(user, "is_superuser", False):
        return []
    return stored_denied_extras(user)


def user_can_extraprotocolar(user, extra_type):
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    key = str(extra_type or "").strip()
    return key not in stored_denied_extras(user)


def extraprotocolar_catalog():
    return [
        {"key": key, "name": EXTRAPROTOCOLAR_NAMES[key]}
        for key in EXTRAPROTOCOLAR_TYPES
    ]


def extraprotocolar_permissions_payload(user, catalog=None):
    denied = set(stored_denied_extras(user))
    items = catalog if catalog is not None else extraprotocolar_catalog()
    return [
        {
            "key": item["key"],
            "name": item["name"],
            "allowed": item["key"] not in denied,
        }
        for item in items
    ]


def denied_from_permissions(items):
    if not items:
        return []
    denied = []
    for item in items:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        if key in EXTRAPROTOCOLAR_TYPES and not item.get("allowed", True):
            if key not in denied:
                denied.append(key)
    return denied


def ensure_extraprotocolar_permission(user, extra_type):
    if not user_can_extraprotocolar(user, extra_type):
        raise PermissionDenied(EXTRAPROTOCOLAR_DENIED_MESSAGE)


class ExtraProtocolarRestrictedMixin:
    extra_type = None

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        extra_type = getattr(self, "extra_type", None)
        if extra_type:
            ensure_extraprotocolar_permission(request.user, extra_type)
