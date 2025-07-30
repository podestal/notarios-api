# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models


class IngresoPoderes(models.Model):
    id_poder = models.AutoField()
    num_kardex = models.CharField(max_length=30, blank=True, null=True)
    nom_recep = models.CharField(max_length=1000, blank=True, null=True)
    hora_recep = models.CharField(max_length=20, blank=True, null=True)
    id_asunto = models.CharField(max_length=10, blank=True, null=True)
    fec_ingreso = models.CharField(max_length=30, blank=True, null=True)
    referencia = models.CharField(max_length=1000, blank=True, null=True)
    nom_comuni = models.CharField(max_length=500, blank=True, null=True)
    telf_comuni = models.CharField(max_length=500, blank=True, null=True)
    email_comuni = models.CharField(max_length=500, blank=True, null=True)
    documento = models.CharField(max_length=50, blank=True, null=True)
    id_respon = models.CharField(max_length=30, blank=True, null=True)
    des_respon = models.CharField(max_length=1000, blank=True, null=True)
    doc_presen = models.CharField(max_length=50, blank=True, null=True)
    fec_ofre = models.CharField(max_length=30, blank=True, null=True)
    hora_ofre = models.CharField(max_length=30, blank=True, null=True)
    num_formu = models.CharField(max_length=30, blank=True, null=True)
    fec_crono = models.CharField(max_length=30, blank=True, null=True)
    swt_est = models.CharField(max_length=5, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'ingreso_poderes'
