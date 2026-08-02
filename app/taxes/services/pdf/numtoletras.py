"""
Convert a monetary amount to Spanish words (SOLES), SUNAT-style.

Used in CPE XML ``cbc:Note`` and PDF importe-en-letras. Incorrect wording
is a compliance risk — keep this module covered by unit tests.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP, InvalidOperation


_UNITS = (
    "",
    "UN",
    "DOS",
    "TRES",
    "CUATRO",
    "CINCO",
    "SEIS",
    "SIETE",
    "OCHO",
    "NUEVE",
    "DIEZ",
    "ONCE",
    "DOCE",
    "TRECE",
    "CATORCE",
    "QUINCE",
    "DIECISEIS",
    "DIECISIETE",
    "DIECIOCHO",
    "DIECINUEVE",
)

_TENS = (
    "",
    "",
    "VEINTE",
    "TREINTA",
    "CUARENTA",
    "CINCUENTA",
    "SESENTA",
    "SETENTA",
    "OCHENTA",
    "NOVENTA",
)

_HUNDREDS = (
    "",
    "CIENTO",
    "DOSCIENTOS",
    "TRESCIENTOS",
    "CUATROCIENTOS",
    "QUINIENTOS",
    "SEISCIENTOS",
    "SETECIENTOS",
    "OCHOCIENTOS",
    "NOVECIENTOS",
)


def _under_100(n: int) -> str:
    if n < 20:
        return _UNITS[n]
    tens, units = divmod(n, 10)
    if tens == 2 and units:
        return f"VEINTI{_UNITS[units]}"
    if units == 0:
        return _TENS[tens]
    return f"{_TENS[tens]} Y {_UNITS[units]}"


def _under_1000(n: int) -> str:
    if n < 100:
        return _under_100(n)
    if n == 100:
        return "CIEN"
    hundreds, rest = divmod(n, 100)
    head = _HUNDREDS[hundreds]
    if rest == 0:
        return head
    return f"{head} {_under_100(rest)}"


def _integer_to_words(n: int) -> str:
    if n == 0:
        return "CERO"
    if n < 0:
        return f"MENOS {_integer_to_words(-n)}"

    parts: list[str] = []

    billions, n = divmod(n, 1_000_000_000)
    if billions:
        if billions == 1:
            parts.append("UN BILLON")
        else:
            parts.append(f"{_integer_to_words(billions)} BILLONES")

    millions, n = divmod(n, 1_000_000)
    if millions:
        if millions == 1:
            parts.append("UN MILLON")
        else:
            parts.append(f"{_integer_to_words(millions)} MILLONES")

    thousands, n = divmod(n, 1000)
    if thousands:
        if thousands == 1:
            parts.append("MIL")
        else:
            parts.append(f"{_under_1000(thousands)} MIL")

    if n:
        parts.append(_under_1000(n))

    return " ".join(parts)


def _ending_un_to_uno(words: str) -> str:
    """
    For importe en letras, a trailing masculine \"UN\" becomes \"UNO\"
    (e.g. 101 → CIENTO UNO, 21 → VEINTIUNO). \"UN SOL\" is handled separately.
    """
    if words.endswith("VEINTIUN"):
        return f"{words[:-2]}UNO"
    if words == "UN":
        return "UNO"
    if words.endswith(" UN"):
        return f"{words[:-2]}UNO"
    return words


def _parse_amount(value) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        raw = value
    else:
        text = str(value).strip().replace(" ", "")
        # Allow "1,234.56" or European "1234,56" only when unambiguous.
        if "," in text and "." in text:
            text = text.replace(",", "")
        elif "," in text and "." not in text:
            text = text.replace(",", ".")
        try:
            raw = Decimal(text)
        except (InvalidOperation, AttributeError, TypeError, ValueError):
            return Decimal("0")
    try:
        return raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return Decimal("0")


def numtoletras(total1) -> str:
    """
    Format amount as ``OCHENTA Y OCHO CON 00/100 SOLES``.

    Accepts int / float / Decimal / str. Always rounds half-up to 2 decimals.
    """
    amount = _parse_amount(total1)
    negative = amount < 0
    amount = abs(amount)

    whole = int(amount)
    # Avoid float noise: derive cents from quantized Decimal.
    cents = int((amount - Decimal(whole)) * 100)
    cents_str = f"{cents:02d}"

    if whole == 0:
        words = f"CERO CON {cents_str}/100 SOLES"
    elif whole == 1:
        words = f"UN SOL CON {cents_str}/100"
    else:
        integer_words = _ending_un_to_uno(_integer_to_words(whole))
        words = f"{integer_words} CON {cents_str}/100 SOLES"

    if negative:
        words = f"MENOS {words}"
    return words
