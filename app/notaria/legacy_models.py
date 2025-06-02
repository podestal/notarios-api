# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models


class Cliente(models.Model):
    idcliente = models.CharField(primary_key=True, max_length=10)
    tipper = models.CharField(max_length=1, blank=True, null=True)
    apepat = models.CharField(max_length=100, blank=True, null=True)
    apemat = models.CharField(max_length=100, blank=True, null=True)
    prinom = models.CharField(max_length=100, blank=True, null=True)
    segnom = models.CharField(max_length=100, blank=True, null=True)
    nombre = models.CharField(max_length=1000, blank=True, null=True)
    direccion = models.CharField(max_length=3000, db_collation='utf8_general_ci', blank=True, null=True)
    idtipdoc = models.IntegerField(blank=True, null=True)
    numdoc = models.CharField(max_length=50, blank=True, null=True)
    email = models.CharField(max_length=300, blank=True, null=True)
    telfijo = models.CharField(max_length=20, blank=True, null=True)
    telcel = models.CharField(max_length=20, blank=True, null=True)
    telofi = models.CharField(max_length=20, blank=True, null=True)
    sexo = models.CharField(max_length=1, blank=True, null=True)
    idestcivil = models.IntegerField(blank=True, null=True)
    natper = models.CharField(max_length=50, blank=True, null=True)
    conyuge = models.CharField(max_length=10, blank=True, null=True)
    nacionalidad = models.CharField(max_length=100, blank=True, null=True)
    idprofesion = models.IntegerField(blank=True, null=True)
    detaprofesion = models.CharField(max_length=1000, blank=True, null=True)
    idcargoprofe = models.IntegerField(blank=True, null=True)
    profocupa = models.CharField(max_length=1000, blank=True, null=True)
    dirfer = models.CharField(max_length=3000, blank=True, null=True)
    idubigeo = models.CharField(max_length=6, blank=True, null=True)
    cumpclie = models.CharField(max_length=15, blank=True, null=True)
    fechaing = models.CharField(max_length=10, blank=True, null=True)
    razonsocial = models.CharField(max_length=3000, db_collation='utf8_general_ci', blank=True, null=True)
    domfiscal = models.CharField(max_length=3000, db_collation='utf8_general_ci', blank=True, null=True)
    telempresa = models.CharField(max_length=12, blank=True, null=True)
    mailempresa = models.CharField(max_length=200, blank=True, null=True)
    contacempresa = models.CharField(max_length=1000, blank=True, null=True)
    fechaconstitu = models.CharField(max_length=12, blank=True, null=True)
    idsedereg = models.IntegerField(blank=True, null=True)
    numregistro = models.CharField(max_length=50, blank=True, null=True)
    numpartida = models.CharField(max_length=50, blank=True, null=True)
    actmunicipal = models.CharField(max_length=3000, blank=True, null=True)
    tipocli = models.CharField(max_length=1, blank=True, null=True)
    impeingre = models.CharField(max_length=10, blank=True, null=True)
    impnumof = models.CharField(max_length=50, blank=True, null=True)
    impeorigen = models.CharField(max_length=3000, blank=True, null=True)
    impentidad = models.CharField(max_length=3000, blank=True, null=True)
    impremite = models.CharField(max_length=3000, blank=True, null=True)
    impmotivo = models.CharField(max_length=3000, blank=True, null=True)
    residente = models.CharField(max_length=2, blank=True, null=True)
    docpaisemi = models.CharField(max_length=100, blank=True, null=True)
    partidaconyuge = models.CharField(max_length=15, blank=True, null=True)
    separaciondebienes = models.CharField(max_length=1, blank=True, null=True)
    idsedeconyuge = models.CharField(max_length=11, blank=True, null=True)
    numdoc_plantilla = models.CharField(max_length=11, blank=True, null=True)
    profesion_plantilla = models.CharField(max_length=200, blank=True, null=True)
    ubigeo_plantilla = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'cliente'
