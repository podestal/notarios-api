# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models


class ViajeContratantes(models.Model):
    id_viaje = models.IntegerField(blank=True, null=True)
    id_contratante = models.AutoField()
    c_codcontrat = models.CharField(max_length=30, blank=True, null=True)
    c_descontrat = models.CharField(max_length=2000, blank=True, null=True)
    c_fircontrat = models.CharField(max_length=20, blank=True, null=True)
    c_condicontrat = models.CharField(max_length=30, blank=True, null=True)
    edad = models.CharField(max_length=10, blank=True, null=True)
    condi_edad = models.CharField(max_length=10, blank=True, null=True)
    codi_testigo = models.CharField(max_length=2000, blank=True, null=True)
    tip_incapacidad = models.CharField(max_length=2000, blank=True, null=True)
    codi_podera = models.CharField(max_length=100, blank=True, null=True)
    partida_e = models.CharField(max_length=2000, blank=True, null=True)
    sede_regis = models.CharField(max_length=2000, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'viaje_contratantes'
