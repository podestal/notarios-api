# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models


class Predios(models.Model):
    id_predio = models.AutoField(primary_key=True)
    tipo = models.CharField(max_length=20)
    tipo_zona = models.CharField(max_length=6, blank=True, null=True)
    zona = models.CharField(max_length=200, blank=True, null=True)
    denominacion = models.CharField(max_length=200, blank=True, null=True)
    tipo_via = models.CharField(max_length=60, blank=True, null=True)
    nombre_via = models.CharField(max_length=60, blank=True, null=True)
    numero = models.CharField(max_length=10, blank=True, null=True)
    manzana = models.CharField(max_length=10, blank=True, null=True)
    lote = models.CharField(max_length=10, blank=True, null=True)
    kardex = models.CharField(max_length=20, blank=True, null=True)
    fecha_registro = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'predios'
        unique_together = (('tipo_zona', 'zona', 'denominacion', 'tipo_via', 'nombre_via', 'numero', 'manzana', 'lote'),)
