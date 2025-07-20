# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models


class Detallebienes(models.Model):
    detbien = models.AutoField(primary_key=True)
    itemmp = models.CharField(max_length=6)
    kardex = models.CharField(max_length=30, blank=True, null=True)
    idtipacto = models.CharField(max_length=10, blank=True, null=True)
    tipob = models.CharField(max_length=100)
    idtipbien = models.IntegerField()
    coddis = models.CharField(max_length=6)
    fechaconst = models.CharField(max_length=12)
    oespecific = models.CharField(max_length=200)
    smaquiequipo = models.CharField(max_length=200)
    tpsm = models.CharField(max_length=3)
    npsm = models.CharField(max_length=200)
    pregistral = models.CharField(max_length=50, blank=True, null=True)
    idsedereg = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'detallebienes'
