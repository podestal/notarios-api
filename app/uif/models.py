from django.db import models


class RoDataField(models.Model):
    pk_data_field = models.AutoField(primary_key=True, db_column="pkDataField")
    number_of_data = models.SmallIntegerField(db_column="numberOfData", blank=True, null=True)
    column_length = models.IntegerField(db_column="columnLength", blank=True, null=True)
    column_description = models.CharField(max_length=250, db_column="columnDescription", blank=True, null=True)

    class Meta:
        managed = False
        db_table = "ro_data_field"


class RoValidationByAct(models.Model):
    pk_validation_by_act = models.AutoField(primary_key=True, db_column="pkValidationByAct")
    fk_data_field = models.IntegerField(db_column="fkDataField", blank=True, null=True)
    code_act = models.CharField(max_length=3, db_column="codeAct", blank=True, null=True)
    data_value = models.CharField(max_length=50, db_column="dataValue", blank=True, null=True)
    detail_value = models.CharField(max_length=3000, db_column="detailValue", blank=True, null=True)

    class Meta:
        managed = False
        db_table = "ro_validation_by_act"


class Mediospago(models.Model):
    codmepag = models.AutoField(primary_key=True)
    uif = models.CharField(max_length=3)
    desmpagos = models.CharField(max_length=200)

    class Meta:
        managed = False
        db_table = "mediospago"


class FpagoUif(models.Model):
    id_fpago = models.AutoField(primary_key=True)
    codigo = models.CharField(max_length=10, blank=True, null=True)
    descripcion = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "fpago_uif"


class Monedas(models.Model):
    idmon = models.AutoField(primary_key=True)
    codigo = models.CharField(max_length=3, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "monedas"


class Ciiu(models.Model):
    coddivi = models.CharField(primary_key=True, max_length=20)
    nombre = models.CharField(max_length=200, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "ciiu"
