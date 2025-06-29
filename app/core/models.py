from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    idusuario = models.AutoField(primary_key=True, verbose_name='ID Usuario', help_text='Unique identifier for the user')
    notary = models.IntegerField(default=0, verbose_name='Notary', help_text='Notary level of the user')

