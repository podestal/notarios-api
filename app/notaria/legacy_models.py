# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models


class Legalizacion(models.Model):
    idlegalizacion = models.AutoField(db_column='idLegalizacion', primary_key=True)  # Field name made lowercase.
    fechaingreso = models.DateField(db_column='fechaIngreso')  # Field name made lowercase.
    direccioncertificado = models.CharField(db_column='direccionCertificado', max_length=250)  # Field name made lowercase.
    documento = models.TextField()
    dni = models.CharField(max_length=11, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'legalizacion'
