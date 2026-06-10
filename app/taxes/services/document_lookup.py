from django.db.models import Q

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


def document_lookup_context(documents) -> dict:
    items = documents if isinstance(documents, list) else [documents]

    persona_ids = {doc.persona_id for doc in items if getattr(doc, "persona_id", None)}
    usuario_ids = {doc.usuario_id for doc in items if getattr(doc, "usuario_id", None)}
    moneda_ids = {doc.moneda_id for doc in items if getattr(doc, "moneda_id", None)}

    usuarios_by_id = Usuarios.objects.in_bulk(usuario_ids) if usuario_ids else {}
    persona_ids |= {u.persona_id for u in usuarios_by_id.values() if u.persona_id}

    personas_by_id = Personas.objects.in_bulk(persona_ids) if persona_ids else {}
    monedas_by_id = Monedas.objects.in_bulk(moneda_ids) if moneda_ids else {}

    return {
        "personas_by_id": personas_by_id,
        "usuarios_by_id": usuarios_by_id,
        "monedas_by_id": monedas_by_id,
    }


def filter_documents_by_persona_usuario(qs, params):
    persona_documento = params.get("persona_documento", "").strip()
    if persona_documento:
        persona_ids = Personas.objects.filter(
            numero_documento__icontains=persona_documento,
        ).values_list("id_persona", flat=True)
        qs = qs.filter(persona_id__in=persona_ids)

    persona_nombres = params.get("persona_nombres", "").strip()
    if persona_nombres:
        persona_ids = Personas.objects.filter(
            Q(nombre_completo__icontains=persona_nombres)
            | Q(nombres__icontains=persona_nombres)
            | Q(apellido_paterno__icontains=persona_nombres)
            | Q(apellido_materno__icontains=persona_nombres)
        ).values_list("id_persona", flat=True)
        qs = qs.filter(persona_id__in=persona_ids)

    usuario = params.get("usuario", "").strip()
    if usuario:
        persona_ids = Personas.objects.filter(
            Q(nombre_completo__icontains=usuario)
            | Q(nombres__icontains=usuario)
            | Q(apellido_paterno__icontains=usuario)
            | Q(apellido_materno__icontains=usuario)
        ).values_list("id_persona", flat=True)
        usuario_ids = Usuarios.objects.filter(
            Q(usuario__icontains=usuario) | Q(persona_id__in=persona_ids)
        ).values_list("id_usuario", flat=True)
        qs = qs.filter(usuario_id__in=usuario_ids)

    return qs
