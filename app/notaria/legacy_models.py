# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models


class PoderesFuerareg(models.Model):
    id_poder = models.IntegerField(blank=True, null=True)
    id_fuerareg = models.AutoField()
    id_tipo = models.CharField(max_length=10, blank=True, null=True)
    f_fecha = models.CharField(max_length=20, blank=True, null=True)
    f_plazopoder = models.CharField(max_length=100, blank=True, null=True)
    f_fecotor = models.CharField(max_length=100, blank=True, null=True)
    f_fecvcto = models.CharField(max_length=100, blank=True, null=True)
    f_solicita = models.TextField(blank=True, null=True)
    f_observ = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'poderes_fuerareg'
