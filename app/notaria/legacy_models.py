# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models


class PermiViaje(models.Model):
    id_viaje = models.AutoField()
    num_kardex = models.CharField(max_length=30, blank=True, null=True)
    asunto = models.CharField(max_length=1000, blank=True, null=True)
    fec_ingreso = models.DateField(blank=True, null=True)
    nom_recep = models.CharField(max_length=1000, blank=True, null=True)
    hora_recep = models.CharField(max_length=30, blank=True, null=True)
    referencia = models.CharField(max_length=3000, blank=True, null=True)
    nom_comu = models.CharField(max_length=500, blank=True, null=True)
    tel_comu = models.CharField(max_length=500, blank=True, null=True)
    email_comu = models.CharField(max_length=500, blank=True, null=True)
    documento = models.CharField(max_length=500, blank=True, null=True)
    num_crono = models.CharField(max_length=50, blank=True, null=True)
    fecha_crono = models.DateField(blank=True, null=True)
    num_formu = models.CharField(max_length=30, blank=True, null=True)
    lugar_formu = models.CharField(max_length=3000, blank=True, null=True)
    observacion = models.TextField(blank=True, null=True)
    swt_est = models.CharField(max_length=5, blank=True, null=True)
    partida_e = models.CharField(max_length=200, blank=True, null=True)
    sede_regis = models.CharField(max_length=200, blank=True, null=True)
    qr = models.IntegerField(blank=True, null=True)
    via = models.CharField(max_length=60, blank=True, null=True)
    fecha_desde = models.DateField(blank=True, null=True)
    fecha_hasta = models.DateField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'permi_viaje'
