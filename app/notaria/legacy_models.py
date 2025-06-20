# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models


class Patrimonial(models.Model):
    itemmp = models.CharField(max_length=6)
    kardex = models.CharField(max_length=30, blank=True, null=True)
    idtipoacto = models.CharField(max_length=6)
    nminuta = models.CharField(max_length=30)
    idmon = models.IntegerField()
    tipocambio = models.CharField(max_length=10)
    importetrans = models.DecimalField(max_digits=12, decimal_places=2)
    exhibiomp = models.CharField(max_length=2)
    presgistral = models.CharField(max_length=50)
    nregistral = models.CharField(max_length=50)
    idsedereg = models.CharField(max_length=3)
    fpago = models.CharField(max_length=3)
    idoppago = models.CharField(max_length=5)
    ofondos = models.CharField(max_length=150)
    item = models.IntegerField()
    des_idoppago = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'patrimonial'
