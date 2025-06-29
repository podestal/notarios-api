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


class Documentogenerados(models.Model):
    observacion = models.TextField(blank=True, null=True)
    fecha = models.DateTimeField(blank=True, null=True)
    usuario = models.IntegerField(blank=True, null=True)
    ip = models.CharField(max_length=20, blank=True, null=True)
    pc = models.CharField(max_length=50, blank=True, null=True)
    tipogeneracion = models.CharField(max_length=30, blank=True, null=True)
    kardex = models.CharField(max_length=15, blank=True, null=True)
    cliente = models.CharField(max_length=255, blank=True, null=True)
    tipo_docu = models.IntegerField(blank=True, null=True)
    num_docu = models.CharField(max_length=15, blank=True, null=True)
    fecha_partest = models.CharField(max_length=15, blank=True, null=True)
    flag = models.CharField(max_length=5, blank=True, null=True)
    hora = models.CharField(max_length=20, blank=True, null=True)
    estado = models.IntegerField(blank=True, null=True)
    extension = models.CharField(max_length=10, blank=True, null=True)
    otrotipo = models.CharField(db_column='otroTipo', max_length=150, blank=True, null=True)  # Field name made lowercase.

    class Meta:
        managed = False
        db_table = 'documentogenerados'
