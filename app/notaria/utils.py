def generate_new_id(model, id_field='id', fill=10):
    """
    Generate a new 10-digit ID for the given model based on the given field.
    """
    last_instance = model.objects.order_by(f'-{id_field}').first()
    if last_instance:
        last_id = getattr(last_instance, id_field, '0')
        if last_id.isdigit():
            return str(int(last_id) + 1).zfill(fill)
    return '0000000001'

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