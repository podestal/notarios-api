from django.db import models

"""
Models for the taxes app.
This app is used to manage the taxes of the system.
It is used to manage the taxes of the system.
"""


class Usuarios(models.Model):
    id_usuario = models.AutoField(primary_key=True)
    usuario = models.CharField(unique=True, max_length=20)
    clave = models.CharField(max_length=255)
    foto = models.CharField(max_length=200)
    telefono = models.CharField(max_length=20)
    email = models.CharField(max_length=200)
    clave_encriptada = models.CharField(max_length=255)
    estado = models.IntegerField()
    persona_id = models.IntegerField()
    rol_id = models.IntegerField()
    negocio_id = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'usuarios'


class CodigosUnitarios(models.Model):
    id_codigo_unitario = models.AutoField(primary_key=True)
    codigo = models.CharField(max_length=10)
    descripcion = models.CharField(max_length=30)

    class Meta:
        managed = False
        db_table = "codigos_unitarios"

    def __str__(self) -> str:
        return f"{self.codigo} — {self.descripcion}"


class Monedas(models.Model):
    id_moneda = models.AutoField(primary_key=True)
    codigo = models.CharField(max_length=10)
    descripcion = models.CharField(max_length=100)
    abreviatura = models.CharField(max_length=10)
    simbolo = models.CharField(max_length=10)
    creado = models.DateTimeField(blank=True, null=True)
    actualizado = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'monedas'


class TiposIgv(models.Model):
    id_tipo_igv = models.AutoField(primary_key=True)
    codigo = models.CharField(max_length=4)
    descripcion = models.CharField(max_length=100)
    onerosa = models.BooleanField()
    creado = models.DateTimeField(blank=True, null=True)
    actualizado = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'tipos_igv'


class Catalogos(models.Model):
    id_catalogo = models.AutoField(primary_key=True)
    codigo = models.CharField(max_length=8)
    descripcion = models.CharField(max_length=200)
    valor_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    creado = models.DateTimeField(blank=True, null=True)
    actualizado = models.DateTimeField(blank=True, null=True)
    negocio_id = models.IntegerField(blank=True, null=True)
    usuario_id = models.IntegerField(blank=True, null=True)
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
