# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models


class PoderesPension(models.Model):
    id_poder = models.IntegerField(blank=True, null=True)
    id_pension = models.AutoField()
    p_crono = models.CharField(max_length=50, blank=True, null=True)
    p_fecha = models.CharField(max_length=30, blank=True, null=True)
    p_numformu = models.CharField(max_length=30, blank=True, null=True)
    p_domicilio = models.CharField(max_length=500, blank=True, null=True)
    p_pension = models.CharField(max_length=500, blank=True, null=True)
    p_mespension = models.CharField(max_length=500, blank=True, null=True)
    p_anopension = models.CharField(max_length=500, blank=True, null=True)
    p_plazopoder = models.CharField(max_length=500, blank=True, null=True)
    p_fecotor = models.CharField(max_length=30, blank=True, null=True)
    p_fecvcto = models.CharField(max_length=30, blank=True, null=True)
    p_presauto = models.CharField(max_length=1000, blank=True, null=True)
    p_observ = models.TextField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'poderes_pension'
