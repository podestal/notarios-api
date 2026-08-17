from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        'username',
        'email',
        'notary',
        'taxes_usuario_id',
        'negocio_id',
        'is_active',
        'is_staff',
    )
    list_filter = BaseUserAdmin.list_filter + ('negocio_id',)
    search_fields = ('username', 'email', 'first_name', 'last_name')
    fieldsets = BaseUserAdmin.fieldsets + (
        (
            'Taxes / facturación',
            {
                'fields': ('taxes_usuario_id', 'negocio_id', 'notary'),
                'description': (
                    'taxes_usuario_id = id_usuario in Postgres taxes.usuarios. '
                    'Create that row first under Taxes → Usuarios, then paste the id here.'
                ),
            },
        ),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'username',
                'password1',
                'password2',
                'first_name',
                'last_name',
                'email',
                'notary',
                'taxes_usuario_id',
                'negocio_id',
                'is_staff',
            ),
        }),
    )

    def save_model(self, request, obj, form, change):
        if obj.taxes_usuario_id and not obj.negocio_id:
            from taxes.models import Usuarios

            taxes_user = (
                Usuarios.objects.filter(id_usuario=obj.taxes_usuario_id).first()
            )
            if taxes_user and taxes_user.negocio_id:
                obj.negocio_id = taxes_user.negocio_id
        super().save_model(request, obj, form, change)
