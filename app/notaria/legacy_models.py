# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models


class Actocondicion(models.Model):
    idcondicion = models.CharField(primary_key=True, max_length=3)
    idtipoacto = models.CharField(max_length=6)
    condicion = models.CharField(max_length=100)
    parte = models.CharField(max_length=20, blank=True, null=True)
    uif = models.CharField(max_length=20, blank=True, null=True)
    formulario = models.CharField(max_length=20, blank=True, null=True)
    montop = models.CharField(max_length=20, blank=True, null=True)
    totorgante = models.CharField(max_length=2, blank=True, null=True)
    condicionsisgen = models.CharField(max_length=100, blank=True, null=True)
    codconsisgen = models.CharField(max_length=5, blank=True, null=True)
    parte_generacion = models.CharField(max_length=1, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'actocondicion'
