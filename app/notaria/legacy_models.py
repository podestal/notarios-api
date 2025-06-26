# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models


class TplTemplate(models.Model):
    pktemplate = models.AutoField(db_column='pkTemplate', primary_key=True)  # Field name made lowercase.
    nametemplate = models.CharField(db_column='nameTemplate', max_length=250, blank=True, null=True)  # Field name made lowercase.
    fktypekardex = models.IntegerField(db_column='fkTypeKardex', blank=True, null=True)  # Field name made lowercase.
    codeacts = models.CharField(db_column='codeActs', max_length=50, blank=True, null=True)  # Field name made lowercase.
    contract = models.CharField(max_length=3000, blank=True, null=True)
    urltemplate = models.CharField(db_column='urlTemplate', max_length=250, blank=True, null=True)  # Field name made lowercase.
    filename = models.CharField(db_column='fileName', max_length=250, blank=True, null=True)  # Field name made lowercase.
    registrationdate = models.DateTimeField(db_column='registrationDate', blank=True, null=True)  # Field name made lowercase.
    statusregister = models.IntegerField(db_column='statusRegister', blank=True, null=True)  # Field name made lowercase.

    class Meta:
        managed = False
        db_table = 'tpl_template'
