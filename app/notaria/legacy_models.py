# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models


class CertDomiciliario(models.Model):
    id_domiciliario = models.AutoField()
    num_certificado = models.CharField(max_length=10, blank=True, null=True)
    fec_ingreso = models.CharField(max_length=20, blank=True, null=True)
    num_formu = models.CharField(max_length=30, blank=True, null=True)
    nombre_solic = models.CharField(max_length=500, blank=True, null=True)
    tipdoc_solic = models.CharField(max_length=20, blank=True, null=True)
    numdoc_solic = models.CharField(max_length=50, blank=True, null=True)
    domic_solic = models.CharField(max_length=3000, blank=True, null=True)
    motivo_solic = models.CharField(max_length=3000, blank=True, null=True)
    distrito_solic = models.CharField(max_length=50, blank=True, null=True)
    texto_cuerpo = models.TextField(blank=True, null=True)
    justifi_cuerpo = models.TextField(blank=True, null=True)
    nom_testigo = models.CharField(max_length=500, blank=True, null=True)
    tdoc_testigo = models.CharField(max_length=20, blank=True, null=True)
    ndocu_testigo = models.CharField(max_length=50, blank=True, null=True)
    idestcivil = models.IntegerField(blank=True, null=True)
    sexo = models.CharField(max_length=3, blank=True, null=True)
    detprofesionc = models.TextField(blank=True, null=True)
    profesionc = models.TextField(blank=True, null=True)
    especificacion = models.CharField(max_length=30, blank=True, null=True)
    recibo_empresa = models.CharField(max_length=200, blank=True, null=True)
    fecha_ocupa = models.DateField(blank=True, null=True)
    declara_ser = models.CharField(max_length=200, blank=True, null=True)
    propietario = models.CharField(max_length=200, blank=True, null=True)
    recibido = models.CharField(max_length=200, blank=True, null=True)
    numero_recibo = models.CharField(max_length=60, blank=True, null=True)
    mes_facturado = models.CharField(max_length=60, blank=True, null=True)
    idusuario = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'cert_domiciliario'
