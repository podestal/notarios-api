# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models


class Resumenes(models.Model):
    id_resumen = models.AutoField(primary_key=True)
    fecha_resumen = models.DateField()
    fecha_emision = models.DateField()
    lote = models.IntegerField()
    cantidad = models.IntegerField()
    usuario_id = models.IntegerField()
    ticket_sunat = models.CharField(max_length=100, blank=True, null=True)
    denominacion = models.CharField(max_length=100, blank=True, null=True)
    digest_value = models.TextField(blank=True, null=True)
    signature_value = models.TextField(blank=True, null=True)
    enviada_sunat = models.BooleanField()
    aceptada_sunat = models.BooleanField()

    class Meta:
        managed = False
        db_table = 'resumenes'
