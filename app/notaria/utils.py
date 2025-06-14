def generate_new_id(model, id_field='id'):
    """
    Generate a new 10-digit ID for the given model based on the given field.
    """
    last_instance = model.objects.order_by(f'-{id_field}').first()
    if last_instance:
        last_id = getattr(last_instance, id_field, '0')
        if last_id.isdigit():
            return str(int(last_id) + 1).zfill(10)
    return '0000000001'