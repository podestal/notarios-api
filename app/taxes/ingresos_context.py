from taxes.services.document_lookup import (
    document_lookup_context,
    moneda_display,
    persona_documento_display,
    persona_nombres_display,
    usuario_display,
)

ingresos_lookup_context = document_lookup_context

__all__ = [
    "document_lookup_context",
    "ingresos_lookup_context",
    "moneda_display",
    "persona_documento_display",
    "persona_nombres_display",
    "usuario_display",
]
