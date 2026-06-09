from taxes.models import Monedas, Personas, Usuarios


def _full_name(nombres, apellido_paterno, apellido_materno):
    parts = [
        part.strip()
        for part in (nombres, apellido_paterno, apellido_materno)
        if part and part.strip() and part.strip() != "-"
    ]
    return " ".join(parts) or None


def persona_documento_display(persona):
    if not persona:
        return None
    return persona.numero_documento


def persona_nombres_display(persona):
    if not persona:
        return None
    return _full_name(persona.nombres, persona.apellido_paterno, persona.apellido_materno)


def usuario_display(usuario, personas_by_id):
    if not usuario:
        return None
    persona = personas_by_id.get(usuario.persona_id)
    if persona:
        return _full_name(persona.nombres, persona.apellido_paterno, persona.apellido_materno)
    return usuario.usuario or None


def moneda_display(moneda):
    if not moneda:
        return None
    return moneda.descripcion


def ingresos_lookup_context(ingresos) -> dict:
    items = ingresos if isinstance(ingresos, list) else [ingresos]

    persona_ids = {i.persona_id for i in items if i.persona_id}
    usuario_ids = {i.usuario_id for i in items if i.usuario_id}
    moneda_ids = {i.moneda_id for i in items if i.moneda_id}

    usuarios_by_id = Usuarios.objects.in_bulk(usuario_ids) if usuario_ids else {}
    persona_ids |= {u.persona_id for u in usuarios_by_id.values() if u.persona_id}

    personas_by_id = Personas.objects.in_bulk(persona_ids) if persona_ids else {}
    monedas_by_id = Monedas.objects.in_bulk(moneda_ids) if moneda_ids else {}

    return {
        "personas_by_id": personas_by_id,
        "usuarios_by_id": usuarios_by_id,
        "monedas_by_id": monedas_by_id,
    }
