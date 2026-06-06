from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    idusuario = models.AutoField(primary_key=True, verbose_name='ID Usuario', help_text='Unique identifier for the user')
    notary = models.IntegerField(default=0, verbose_name='Notary', help_text='Notary level of the user')
    taxes_usuario_id = models.IntegerField(
        null=True,
        blank=True,
        verbose_name='Taxes usuario ID',
        help_text='Primary key (id_usuario) in Postgres taxes.usuarios — not a FK (separate DB).',
    )
    negocio_id = models.IntegerField(
        null=True,
        blank=True,
        verbose_name='Negocio ID',
        help_text='Tenant (negocio) in Postgres taxes — copied from linked usuarios row.',
    )

    @property
    def id(self):
        return self.idusuario