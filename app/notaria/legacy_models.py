# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models


class Renta(models.Model):
    idrenta = models.CharField(primary_key=True, max_length=6)
    idcontratante = models.CharField(max_length=10)
    kardex = models.CharField(max_length=30, blank=True, null=True)
    pregu1 = models.CharField(max_length=2)
    pregu2 = models.CharField(max_length=2)
    pregu3 = models.CharField(max_length=2)

    class Meta:
        managed = False
        db_table = 'renta'
