# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models


class Ubigeo(models.Model):
    coddis = models.CharField(primary_key=True, max_length=6, db_collation='latin1_swedish_ci')
    nomdis = models.CharField(max_length=50, db_collation='latin1_swedish_ci')
    nomprov = models.CharField(max_length=50, db_collation='latin1_swedish_ci')
    nomdpto = models.CharField(max_length=50, db_collation='latin1_swedish_ci')
    coddist = models.CharField(max_length=2, db_collation='latin1_swedish_ci')
    codprov = models.CharField(max_length=2, db_collation='latin1_swedish_ci')
    codpto = models.CharField(max_length=2, db_collation='latin1_swedish_ci')

    class Meta:
        managed = False
        db_table = 'ubigeo'
