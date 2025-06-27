# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models


class Documentogenerados(models.Model):
    observacion = models.TextField(blank=True, null=True)
    fecha = models.DateTimeField(blank=True, null=True)
    usuario = models.IntegerField(blank=True, null=True)
    ip = models.CharField(max_length=20, blank=True, null=True)
    pc = models.CharField(max_length=50, blank=True, null=True)
    tipogeneracion = models.CharField(max_length=30, blank=True, null=True)
    kardex = models.CharField(max_length=15, blank=True, null=True)
    cliente = models.CharField(max_length=255, blank=True, null=True)
    tipo_docu = models.IntegerField(blank=True, null=True)
    num_docu = models.CharField(max_length=15, blank=True, null=True)
    fecha_partest = models.CharField(max_length=15, blank=True, null=True)
    flag = models.CharField(max_length=5, blank=True, null=True)
    hora = models.CharField(max_length=20, blank=True, null=True)
    estado = models.IntegerField(blank=True, null=True)
    extension = models.CharField(max_length=10, blank=True, null=True)
    otrotipo = models.CharField(db_column='otroTipo', max_length=150, blank=True, null=True)  # Field name made lowercase.

    class Meta:
        managed = False
        db_table = 'documentogenerados'
