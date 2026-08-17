from django.contrib import admin

from .models import Personas, Usuarios


@admin.register(Usuarios)
class UsuariosAdmin(admin.ModelAdmin):
    """Postgres taxes.usuarios — required before a Django user can emit comprobantes."""

    list_display = (
        "id_usuario",
        "usuario",
        "email",
        "negocio_id",
        "rol_id",
        "persona_id",
        "estado",
    )
    list_filter = ("estado", "negocio_id", "rol_id")
    search_fields = ("usuario", "email", "telefono")
    ordering = ("usuario",)
    fields = (
        "usuario",
        "email",
        "telefono",
        "negocio_id",
        "rol_id",
        "persona_id",
        "estado",
        "clave",
    )

    def get_changeform_initial_data(self, request):
        return {
            "estado": 1,
            "rol_id": 1,
            "telefono": "",
            "email": "",
        }

    def save_model(self, request, obj, form, change):
        if not obj.foto:
            obj.foto = ""
        if obj.telefono is None:
            obj.telefono = ""
        if obj.email is None:
            obj.email = ""
        if obj.clave is None:
            obj.clave = ""
        if not obj.clave_encriptada:
            obj.clave_encriptada = obj.clave or ""
        if obj.estado is None:
            obj.estado = 1
        super().save_model(request, obj, form, change)


@admin.register(Personas)
class PersonasAdmin(admin.ModelAdmin):
    """Lookup for persona_id when creating a taxes usuario."""

    list_display = ("id_persona", "nombre_completo", "numero_documento", "email")
    search_fields = ("nombre_completo", "numero_documento", "email", "razon_social")
    ordering = ("nombre_completo",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
