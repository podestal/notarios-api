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
    fieldsets = BaseUserAdmin.fieldsets + (
        (
            'Taxes',
            {'fields': ('taxes_usuario_id', 'negocio_id', 'notary')},
        ),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide'),
            'fields': ('username', 'password1', 'password2',
                       'first_name', 'last_name', 'notary', 'email'),
        }),
    )
