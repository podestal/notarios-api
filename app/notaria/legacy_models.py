# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models


class Detallevehicular(models.Model):
    detveh = models.AutoField()
    kardex = models.CharField(max_length=30, blank=True, null=True)
    idtipacto = models.CharField(max_length=20, blank=True, null=True)
    idplaca = models.CharField(max_length=3)
    numplaca = models.CharField(max_length=50)
    clase = models.CharField(max_length=50, blank=True, null=True)
    marca = models.CharField(max_length=100, blank=True, null=True)
    anofab = models.CharField(max_length=30, blank=True, null=True)
    modelo = models.CharField(max_length=100, blank=True, null=True)
    combustible = models.CharField(max_length=100, blank=True, null=True)
    carroceria = models.CharField(max_length=100, blank=True, null=True)
    fecinsc = models.CharField(max_length=30, blank=True, null=True)
    color = models.CharField(max_length=100, blank=True, null=True)
    motor = models.CharField(max_length=100, blank=True, null=True)
    numcil = models.CharField(max_length=3, blank=True, null=True)
    numserie = models.CharField(max_length=30, blank=True, null=True)
    numrueda = models.CharField(max_length=3, blank=True, null=True)
    idmon = models.CharField(max_length=5, blank=True, null=True)
    precio = models.DecimalField(max_digits=16, decimal_places=2, blank=True, null=True)
    codmepag = models.CharField(max_length=4, blank=True, null=True)
    pregistral = models.CharField(max_length=100, blank=True, null=True)
    idsedereg = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'detallevehicular'
