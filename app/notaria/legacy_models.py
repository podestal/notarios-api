# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models


class Tiposdeacto(models.Model):
    idtipoacto = models.CharField(primary_key=True, max_length=6)
    actosunat = models.CharField(max_length=25, blank=True, null=True)
    actouif = models.CharField(max_length=25, blank=True, null=True)
    idtipkar = models.IntegerField()
    desacto = models.CharField(max_length=300)
    umbral = models.IntegerField(blank=True, null=True)
    impuestos = models.IntegerField(blank=True, null=True)
    idcalnot = models.IntegerField(blank=True, null=True)
    idecalreg = models.IntegerField(blank=True, null=True)
    idmodelo = models.IntegerField(blank=True, null=True)
    rol_part = models.CharField(max_length=10, blank=True, null=True)
    cod_ancert = models.CharField(max_length=5, blank=True, null=True)
    tipoplantilla_default = models.CharField(max_length=1, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'tiposdeacto'
