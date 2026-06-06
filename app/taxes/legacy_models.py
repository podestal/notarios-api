# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models


class Personas(models.Model):
    id_persona = models.AutoField(primary_key=True)
    nombres = models.CharField(max_length=45, blank=True, null=True)
    apellido_paterno = models.CharField(max_length=45, blank=True, null=True)
    apellido_materno = models.CharField(max_length=45, blank=True, null=True)
    razon_social = models.CharField(max_length=150, blank=True, null=True)
    nombre_comercial = models.CharField(max_length=45, blank=True, null=True)
    documento = models.ForeignKey('Documentos', models.DO_NOTHING)
    numero_documento = models.CharField(unique=True, max_length=20)
    direccion = models.CharField(max_length=255, blank=True, null=True)
    fecha_nacimiento = models.DateField(blank=True, null=True)
    nombre_completo = models.CharField(max_length=255)
    creado = models.DateTimeField(blank=True, null=True)
    actualizado = models.DateTimeField(blank=True, null=True)
    email = models.CharField(max_length=200, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'personas'
