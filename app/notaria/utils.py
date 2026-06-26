from rest_framework import serializers

TIPDOC_RUC = 8
TIPDOC_SIN_DOCUMENTO = 10


def _effective_attr(attrs, instance, field):
    if field in attrs:
        return attrs[field]
    if instance is not None:
        return getattr(instance, field, None)
    return None


def _coerce_idtipdoc(value):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise serializers.ValidationError({"idtipdoc": "Tipo de documento inválido."})


def validate_juridica_documento(attrs, instance=None):
    """
    Persona jurídica (tipper=J):
    - idtipdoc=8 (RUC): numdoc required, 11 digits.
    - idtipdoc=10 (sin documento): numdoc must be empty.
    """
    tipper = (_effective_attr(attrs, instance, "tipper") or "").strip().upper()
    if tipper != "J":
        return attrs

    idtipdoc = _coerce_idtipdoc(_effective_attr(attrs, instance, "idtipdoc"))
    numdoc = (_effective_attr(attrs, instance, "numdoc") or "").strip()

    if idtipdoc == TIPDOC_RUC:
        if not numdoc:
            raise serializers.ValidationError(
                {"numdoc": "RUC requerido para persona jurídica."}
            )
        if len(numdoc) != 11 or not numdoc.isdigit():
            raise serializers.ValidationError(
                {"numdoc": "RUC inválido: debe tener 11 dígitos."}
            )
        attrs["numdoc"] = numdoc
    elif idtipdoc == TIPDOC_SIN_DOCUMENTO:
        if numdoc:
            raise serializers.ValidationError(
                {"numdoc": "Empresa sin documento no debe tener número de documento."}
            )
        attrs["numdoc"] = ""

    return attrs


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