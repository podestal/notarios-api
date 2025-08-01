# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models


class IngresoCartas(models.Model):
    id_carta = models.AutoField()
    num_carta = models.CharField(max_length=10, db_collation='utf8_general_ci')
    fec_ingreso = models.CharField(max_length=20, db_collation='utf8_general_ci', blank=True, null=True)
    id_remitente = models.CharField(max_length=20, db_collation='utf8_general_ci', blank=True, null=True)
    nom_remitente = models.CharField(max_length=800, db_collation='utf8_general_ci', blank=True, null=True)
    dir_remitente = models.CharField(max_length=3000, db_collation='utf8_general_ci', blank=True, null=True)
    telf_remitente = models.CharField(max_length=500, db_collation='utf8_general_ci', blank=True, null=True)
    nom_destinatario = models.CharField(max_length=500, db_collation='utf8_general_ci', blank=True, null=True)
    dir_destinatario = models.CharField(max_length=3000, db_collation='utf8_general_ci', blank=True, null=True)
    zona_destinatario = models.CharField(max_length=10, db_collation='utf8_general_ci', blank=True, null=True)
    costo = models.CharField(max_length=50, db_collation='utf8_general_ci', blank=True, null=True)
    id_encargado = models.CharField(max_length=800, db_collation='utf8_general_ci', blank=True, null=True)
    des_encargado = models.CharField(max_length=500, db_collation='utf8_general_ci', blank=True, null=True)
    fec_entrega = models.CharField(max_length=20, db_collation='utf8_general_ci', blank=True, null=True)
    hora_entrega = models.CharField(max_length=20, db_collation='utf8_general_ci', blank=True, null=True)
    emple_entrega = models.CharField(max_length=500, db_collation='utf8_general_ci', blank=True, null=True)
    conte_carta = models.TextField(db_collation='utf8_general_ci', blank=True, null=True)
    nom_regogio = models.CharField(max_length=800, db_collation='utf8_general_ci', blank=True, null=True)
    doc_recogio = models.CharField(max_length=50, db_collation='utf8_general_ci', blank=True, null=True)
    fec_recogio = models.CharField(max_length=20, db_collation='utf8_general_ci', blank=True, null=True)
    fact_recogio = models.CharField(max_length=500, db_collation='utf8_general_ci', blank=True, null=True)
    dni_destinatario = models.CharField(max_length=30, blank=True, null=True)
    recepcion = models.CharField(max_length=250, blank=True, null=True)
    firmo = models.CharField(max_length=2, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'ingreso_cartas'
