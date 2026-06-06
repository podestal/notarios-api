from django.db import models


class CodigosUnitarios(models.Model):
    id_codigo_unitario = models.AutoField(primary_key=True)
    codigo = models.CharField(max_length=10)
    descripcion = models.CharField(max_length=30)

    class Meta:
        managed = False
        db_table = "codigos_unitarios"

    def __str__(self) -> str:
        return f"{self.codigo} — {self.descripcion}"


class Catalogos(models.Model):
    id_catalogo = models.AutoField(primary_key=True)
    codigo = models.CharField(max_length=8)
    descripcion = models.CharField(max_length=200)
    valor_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    creado = models.DateTimeField(blank=True, null=True)
    actualizado = models.DateTimeField(blank=True, null=True)
    negocio_id = models.IntegerField()
    usuario_id = models.IntegerField()
    moneda_id = models.IntegerField()
    codigo_unitario = models.ForeignKey(
        CodigosUnitarios,
        models.DO_NOTHING,
        blank=True,
        null=True,
    )
    tipo_igv_id = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "catalogos"

    def __str__(self) -> str:
        return f"{self.codigo} — {self.descripcion}"
