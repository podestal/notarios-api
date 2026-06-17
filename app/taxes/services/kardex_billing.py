from rest_framework.exceptions import ValidationError

from notaria.models import Kardex


def normalize_kardex(value) -> str | None:
    value = str(value or "").strip()
    return value or None


def lock_kardex_for_billing(kardex_value: str | None) -> Kardex | None:
    kardex_code = normalize_kardex(kardex_value)
    if kardex_code is None:
        return None

    kardex = (
        Kardex.objects.select_for_update()
        .filter(kardex=kardex_code)
        .first()
    )
    if kardex is None:
        raise ValidationError({"kardex": "Kardex no encontrado."})

    return kardex


def mark_kardex_as_billed(kardex: Kardex | None) -> None:
    if kardex is None:
        return

    kardex.pagado = 1
    kardex.save(update_fields=["pagado"])
