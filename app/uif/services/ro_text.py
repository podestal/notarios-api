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
        ("Ã¡", "A"),
        ("Ã©", "E"),
        ("Ã­", "I"),
        ("ï¿½", "I"),
        ("Ã³", "O"),
        ("Ãº", "U"),
        ("n~", "#"),
        ("ÃƒÂ¡", "A"),
        ("Ã±", "#"),
        ("Ã'", "#"),
        ("ÃƒÂ±", "#"),
        ("Ãš", "U"),
        ("Ã?", "#"),
        ("Ã??", "#"),
        ("À?", "#"),
        ("À‘", "#"),
        ("ã¡", "A"),
        ("ã©", "E"),
        ("ã­", "I"),
        ("ã³", "O"),
        ("ãº", "U"),
        ("ãƒÂ¡", "A"),
        ("ã±", "#"),
        ("ãƒÂ±", "#"),
        ("ãš", "Ú"),
        ("ã?", "#"),
        ("ã??", "#"),
        ("ã‘", "#"),
        ("ÃŠ", "U"),
        ("AÂ", "A"),
        ("ÁÂ", "A"),
        ("IÂ", "I"),
        ("Ã‘", "#"),
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
    accent_groups = [
        (("á", "à", "â", "ã", "ª", "ä"), "a"),
        (("Á", "À", "Â", "Ã", "Ä"), "A"),
        (("Í", "Ì", "Î", "Ï"), "I"),
        (("í", "ì", "î", "ï"), "i"),
        (("é", "è", "ê", "ë"), "e"),
        (("É", "È", "Ê", "Ë"), "E"),
        (("ó", "ò", "ô", "õ", "ö", "º"), "o"),
        (("Ó", "Ò", "Ô", "Õ", "Ö"), "O"),
        (("ú", "ù", "û", "ü"), "u"),
        (("Ú", "Ù", "Û", "Ü"), "U"),
        (("ñ", "Ñ"), "#"),
    ]
    for chars, repl in accent_groups:
        for ch in chars:
            value_string = value_string.replace(ch, repl)
    value_string = value_string.replace("*", "")
    for deg in "1234567890":
        value_string = value_string.replace(f"{deg}°", deg)
    return value_string
