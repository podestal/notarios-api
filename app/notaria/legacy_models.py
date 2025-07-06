# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models


class Detallemediopago(models.Model):
    detmp = models.AutoField(primary_key=True)
    itemmp = models.CharField(max_length=6, blank=True, null=True)
    kardex = models.CharField(max_length=30, blank=True, null=True)
    tipacto = models.CharField(max_length=10, blank=True, null=True)
    codmepag = models.IntegerField(blank=True, null=True)
    fpago = models.CharField(max_length=10, blank=True, null=True)
    idbancos = models.IntegerField(blank=True, null=True)
    importemp = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    idmon = models.CharField(max_length=10, blank=True, null=True)
    foperacion = models.CharField(max_length=12, blank=True, null=True)
    documentos = models.CharField(max_length=500, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'detallemediopago'
