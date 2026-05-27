"""
RoClass::remplace_string_ro — text normalization for UIF plane / RO fields.
"""


def remplace_string_ro(value, type_person=1):
    """Port of RoClass::remplace_string_ro (PHP)."""
    if value is None:
        return ""
    value_string = str(value)
    if type_person == 1:
        for ch in '"$&@/().,;':
            value_string = value_string.replace(ch, "")
    replacements = [
        ("Ã¡", "á"),
        ("Ã©", "é"),
        ("Ã­", "í"),
        ("ï¿½", "í"),
        ("Ã³", "ó"),
        ("Ãº", "ú"),
        ("n~", "ñ"),
        ("ÃƒÂ¡", "á"),
        ("Ã±", "ñ"),
        ("Ã'", "Ñ"),
        ("ÃƒÂ±", "ñ"),
        ("Ãš", "Ú"),
        ("Ã?", "Ñ"),
        ("Ã??", "Ñ"),
        ("À?", "Ñ"),
        ("À‘", "Ñ"),
        ("ã¡", "á"),
        ("ã©", "é"),
        ("ã­", "í"),
        ("ã³", "ó"),
        ("ãº", "ú"),
        ("ãƒÂ¡", "á"),
        ("ã±", "ñ"),
        ("ãƒÂ±", "ñ"),
        ("ãš", "Ú"),
        ("ã?", "Ñ"),
        ("ã??", "Ñ"),
        ("ã‘", "Ñ"),
        ("ÃŠ", "U"),
        ("AÂ", "A"),
        ("ÁÂ", "A"),
        ("IÂ", "I"),
        ("Ã‘", "Ñ"),
        ("º", ""),
        ("Nº", "Nro"),
        ("|", ""),
        ("N°", ""),
        ("´", ""),
        (" °", ""),
        ("°", ""),
        ("¿", ""),
        ("?", ""),
        ("-", ""),
    ]
    for old, new in replacements:
        value_string = value_string.replace(old, new)
    accent_groups = []
    for chars, repl in accent_groups:
        for ch in chars:
            value_string = value_string.replace(ch, repl)
    value_string = value_string.replace("*", "")
    for deg in "1234567890":
        value_string = value_string.replace(f"{deg}°", deg)
    return value_string
