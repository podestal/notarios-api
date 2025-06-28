from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    notary = models.IntegerField(default=0, verbose_name='Notary', help_text='Notary level of the user')

