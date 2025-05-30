# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models


class DetalleActosKardex(models.Model):
    item = models.AutoField(primary_key=True)
    kardex = models.CharField(max_length=30, blank=True, null=True)
    idtipoacto = models.CharField(max_length=6)
    actosunat = models.CharField(max_length=3)
    actouif = models.CharField(max_length=3)
    idtipkar = models.IntegerField()
    desacto = models.CharField(max_length=500)

    class Meta:
        managed = False
        db_table = 'detalle_actos_kardex'
