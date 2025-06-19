# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models


class Contratantesxacto(models.Model):
    idtipkar = models.IntegerField()
    kardex = models.CharField(max_length=30, blank=True, null=True)
    idtipoacto = models.CharField(max_length=6)
    idcontratante = models.CharField(max_length=10)
    item = models.IntegerField()
    idcondicion = models.CharField(max_length=3)
    parte = models.CharField(max_length=3)
    porcentaje = models.CharField(max_length=50)
    uif = models.CharField(max_length=5)
    formulario = models.CharField(max_length=2)
    monto = models.CharField(max_length=100)
    opago = models.CharField(max_length=2)
    ofondo = models.CharField(max_length=300)
    montop = models.CharField(max_length=2)

    class Meta:
        managed = False
        db_table = 'contratantesxacto'
