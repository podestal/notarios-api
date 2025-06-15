# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models


class Representantes(models.Model):
    idcontratante = models.CharField(max_length=15, blank=True, null=True)
    kardex = models.CharField(max_length=15, blank=True, null=True)
    idtipoacto = models.CharField(max_length=15, blank=True, null=True)
    facultades = models.CharField(max_length=150, blank=True, null=True)
    inscrito = models.CharField(max_length=50, blank=True, null=True)
    sede_registral = models.CharField(max_length=15, blank=True, null=True)
    partida = models.CharField(max_length=50, blank=True, null=True)
    idcontratante_r = models.CharField(max_length=15, blank=True, null=True)
    id_ro_repre = models.CharField(max_length=50, blank=True, null=True)
    ido = models.CharField(db_column='idO', max_length=5, blank=True, null=True)  # Field name made lowercase.
    odb = models.CharField(db_column='odB', max_length=5, blank=True, null=True)  # Field name made lowercase.

    class Meta:
        managed = False
        db_table = 'representantes'
