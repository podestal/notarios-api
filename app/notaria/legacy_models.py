# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models


class Libros(models.Model):
    numlibro = models.CharField(max_length=10)
    ano = models.CharField(max_length=4)
    fecing = models.DateField()
    tipper = models.CharField(max_length=1)
    apepat = models.CharField(max_length=1000)
    apemat = models.CharField(max_length=1000)
    prinom = models.CharField(max_length=1000)
    segnom = models.CharField(max_length=1000)
    ruc = models.CharField(max_length=11)
    domicilio = models.CharField(max_length=2000)
    coddis = models.CharField(max_length=6)
    empresa = models.CharField(max_length=5000)
    domfiscal = models.CharField(max_length=3000)
    idtiplib = models.IntegerField()
    descritiplib = models.CharField(max_length=3000)
    idlegal = models.IntegerField()
    folio = models.CharField(max_length=20)
    idtipfol = models.IntegerField()
    detalle = models.CharField(max_length=3000)
    idnotario = models.IntegerField()
    solicitante = models.CharField(max_length=3000)
    comentario = models.CharField(max_length=3000)
    feclegal = models.CharField(max_length=12)
    comentario2 = models.CharField(max_length=3000)
    dni = models.CharField(max_length=11)
    idusuario = models.IntegerField()
    idnlibro = models.IntegerField()
    codclie = models.CharField(max_length=10, blank=True, null=True)
    flag = models.IntegerField(blank=True, null=True)
    numdoc_plantilla = models.CharField(max_length=11, blank=True, null=True)
    estadosisgen = models.IntegerField(db_column='estadoSisgen', blank=True, null=True)  # Field name made lowercase.

    class Meta:
        managed = False
        db_table = 'libros'
        unique_together = (('numlibro', 'ano'),)
