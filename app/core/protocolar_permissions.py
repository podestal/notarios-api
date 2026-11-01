"""Per-user protocolar (tipkar 1–5) restrictions.

Empty ``User.protocolar_denied`` means every protocolar is allowed.
Superusers always pass enforcement, even if flags are stored as denied.
"""

from rest_framework.exceptions import PermissionDenied

PROTOCOLAR_TIPKARS = (1, 2, 3, 4, 5)

PROTOCOLAR_NAMES = {
    1: "Escrituras Públicas",
    2: "Asuntos No Contenciosos",
    3: "Transferencias Vehiculares",
    4: "Garantías Mobiliarias",
    5: "Testamentos",
}

PROTOCOLAR_DENIED_MESSAGE = "No tiene permiso para este tipo de protocolar."


def normalize_denied(value):
    if not value:
        return []
    if isinstance(value, (str, bytes)):
        return []
    denied = []
    for item in value:
        try:
            tipkar = int(item)
        except (TypeError, ValueError):
            continue
        if tipkar in PROTOCOLAR_TIPKARS and tipkar not in denied:
            denied.append(tipkar)
    return denied


def stored_denied_tipkars(user):
    return normalize_denied(getattr(user, "protocolar_denied", None))


def denied_tipkars(user):
    if user is None or not getattr(user, "is_authenticated", False):
        return list(PROTOCOLAR_TIPKARS)
    if getattr(user, "is_superuser", False):
        return []
    return stored_denied_tipkars(user)


def user_can_protocolar(user, idtipkar):
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    try:
        tipkar = int(idtipkar)
    except (TypeError, ValueError):
        return False
    return tipkar not in stored_denied_tipkars(user)


def protocolar_catalog():
    names = dict(PROTOCOLAR_NAMES)
    try:
        from notaria.models import Tipokar

        for row in Tipokar.objects.filter(idtipkar__in=PROTOCOLAR_TIPKARS):
            label = (getattr(row, "nomtipkar", None) or "").strip()
            if label:
                names[int(row.idtipkar)] = label
    except Exception:
        pass
    return [
        {"idtipkar": tipkar, "name": names.get(tipkar, f"Tipo {tipkar}")}
        for tipkar in PROTOCOLAR_TIPKARS
    ]


def protocolar_permissions_payload(user, catalog=None):
    denied = set(stored_denied_tipkars(user))
    items = catalog if catalog is not None else protocolar_catalog()
    return [
        {
            "idtipkar": item["idtipkar"],
            "name": item["name"],
            "allowed": item["idtipkar"] not in denied,
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
        try:
            tipkar = int(item.get("idtipkar"))
        except (TypeError, ValueError):
            continue
        if tipkar in PROTOCOLAR_TIPKARS and not item.get("allowed", True):
            if tipkar not in denied:
                denied.append(tipkar)
    return denied


def ensure_protocolar_permission(user, idtipkar):
    if not user_can_protocolar(user, idtipkar):
        raise PermissionDenied(PROTOCOLAR_DENIED_MESSAGE)
