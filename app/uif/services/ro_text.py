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
        ("Ã‘", "#"),
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
    ]
    for old, new in replacements:
        value_string = value_string.replace(old, new)
    value_string = value_string.replace("*", "&")
    value_string = value_string.replace("ÃŠ", "U")
    value_string = value_string.replace("*", "")
    for old, new in (
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
    ):
        value_string = value_string.replace(old, new)
    for deg in "1234567890":
        value_string = value_string.replace(f"{deg}°", deg)
    accent_groups = [
        ("áàâãªä", "a"),
        ("ÁÀÂÃÄ", "A"),
        ("ÍÌÎÏ", "I"),
        ("íìîï", "i"),
        ("éèêë", "e"),
        ("ÉÈÊË", "E"),
        ("óòôõöº", "o"),
        ("ÓÒÔÕÖ", "O"),
        ("úùûü", "u"),
        ("ÚÙÛÜ", "U"),
        ("ñÑ", "#"),
    ]
    for chars, repl in accent_groups:
        for ch in chars:
            value_string = value_string.replace(ch, repl)
    return value_string
