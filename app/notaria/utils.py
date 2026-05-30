def normalize_residente_for_tipper(tipper, residente=None):
    """Persona jurídica must use empty residente; natural persons use 1/0."""
    if (tipper or "").strip().upper() == "J":
        return ""
    value = str(residente or "").strip()
    if not value or value.upper() == "NULL":
        return "0"
    return value


def merge_legacy_resedente_into_attrs(attrs, initial_data):
    """Accept legacy frontend key `resedente` as alias for `residente`."""
    if initial_data is None:
        return attrs
    if "residente" not in attrs and initial_data.get("resedente") is not None:
        attrs["residente"] = initial_data.get("resedente")
    return attrs


def apply_juridica_residente_blank(instance):
    """Force empty residente on persisted cliente/cliente2 jurídica rows."""
    tipper = (getattr(instance, "tipper", None) or "").strip().upper()
    if tipper != "J":
        return
    instance.__class__.objects.filter(pk=instance.pk).update(residente="")
    instance.residente = ""


def generate_new_id(model, id_field='id', fill=10):
    """
    Generate a new 10-digit ID for the given model based on the given field.
    """
    last_instance = model.objects.order_by(f'-{id_field}').first()
    if last_instance:
        last_id = getattr(last_instance, id_field, '0')
        if last_id.isdigit():
            return str(int(last_id) + 1).zfill(fill)
    return str(1).zfill(fill)

def normalize_name_for_search(name):
    """
    Normalize a name for search purposes.
    Handles common variations and edge cases.
    """
    if not name:
        return ""
    
    # Strip whitespace
    normalized = name.strip()
    
    # Handle common abbreviations and variations
    replacements = {
        'DR.': 'DR',
        'DRA.': 'DRA',
        'SR.': 'SR',
        'SRA.': 'SRA',
        'LIC.': 'LIC',
        'ING.': 'ING',
        'CP.': 'CP',
        'MGR.': 'MGR',
        'PH.D.': 'PHD',
        'MBA.': 'MBA',
    }
    
    for old, new in replacements.items():
        normalized = normalized.replace(old, new)
    
    return normalized