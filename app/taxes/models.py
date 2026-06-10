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


class Documentos(models.Model):
    id_documento = models.AutoField(primary_key=True)
    codigo = models.CharField(max_length=2)
    descripcion = models.CharField(max_length=100)
    abreviatura = models.CharField(max_length=10, blank=True, null=True)
    creado = models.DateTimeField(blank=True, null=True)
    actualizado = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "documentos"


class Personas(models.Model):
    id_persona = models.AutoField(primary_key=True)
    nombres = models.CharField(max_length=45, blank=True, null=True)
    apellido_paterno = models.CharField(max_length=45, blank=True, null=True)
    apellido_materno = models.CharField(max_length=45, blank=True, null=True)
    razon_social = models.CharField(max_length=150, blank=True, null=True)
    nombre_comercial = models.CharField(max_length=45, blank=True, null=True)
    documento = models.ForeignKey(Documentos, models.DO_NOTHING)
    numero_documento = models.CharField(unique=True, max_length=20)
    direccion = models.CharField(max_length=255, blank=True, null=True)
    fecha_nacimiento = models.DateField(blank=True, null=True)
    nombre_completo = models.CharField(max_length=255)
    creado = models.DateTimeField(blank=True, null=True)
    actualizado = models.DateTimeField(blank=True, null=True)
    email = models.CharField(max_length=200, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "personas"


class Comprobantes(models.Model):
    id_comprobante = models.AutoField(primary_key=True)
    codigo = models.CharField(max_length=10)
    descripcion = models.CharField(max_length=100)
    creado = models.DateTimeField(blank=True, null=True)
    actualizado = models.DateTimeField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "comprobantes"


class Series(models.Model):
    id_serie = models.AutoField(primary_key=True)
    serie = models.CharField(max_length=10)
    sede_id = models.IntegerField()
    comprobante = models.ForeignKey(Comprobantes, models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = "series"


class Recibos(models.Model):
    id_recibo = models.AutoField(primary_key=True)
    fecha_emision = models.DateTimeField()
    fecha_vencimiento = models.DateField()
    comprobante = models.ForeignKey('Comprobantes', models.DO_NOTHING)
    serie = models.CharField(max_length=10)
    numero = models.IntegerField()
    exportacion = models.BooleanField(blank=True, null=True)
    moneda_id = models.IntegerField()
    gravada = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    inafecta = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    exonerada = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    igv = models.DecimalField(max_digits=10, decimal_places=2)
    descuento = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    total = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    igv_porcentaje = models.DecimalField(max_digits=10, decimal_places=2)
    detraccion = models.BooleanField(blank=True, null=True)
    observaciones = models.CharField(max_length=255, blank=True, null=True)
    digest_value = models.TextField(blank=True, null=True)
    signature_value = models.TextField(blank=True, null=True)
    enviada_sunat = models.BooleanField()
    nombre_comprobante = models.CharField(max_length=255, blank=True, null=True)
    aceptada_sunat = models.BooleanField(blank=True, null=True)
    usuario_id = models.IntegerField()
    negocio_id = models.IntegerField(blank=True, null=True)
    persona_id = models.IntegerField()
    direccion = models.CharField(max_length=200, blank=True, null=True)
    consulta_ticket = models.CharField(max_length=100, blank=True, null=True)
    motivo_baja = models.CharField(max_length=2000, blank=True, null=True)
    fecha_baja = models.DateField(blank=True, null=True)
    fecha_resumen = models.DateField(blank=True, null=True)
    anulada = models.BooleanField(blank=True, null=True)
    resumen_id = models.IntegerField(blank=True, null=True)
    tipo_recibo_modificado_id = models.IntegerField(blank=True, null=True)
    tipo_nota_credito_id = models.IntegerField(blank=True, null=True)
    tipo_nota_debito_id = models.IntegerField(blank=True, null=True)
    motivo_modificacion = models.CharField(max_length=100, blank=True, null=True)
    serie_documento_modificado = models.CharField(max_length=60, blank=True, null=True)
    numero_documento_modificado = models.CharField(max_length=60, blank=True, null=True)
    baja_id = models.IntegerField(blank=True, null=True)
    observaciones_sunat = models.CharField(max_length=2000, blank=True, null=True)
    codigo_error = models.CharField(max_length=60, blank=True, null=True)
    error_sunat = models.CharField(max_length=2000, blank=True, null=True)
    gratuita = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "recibos"
        unique_together = (('negocio_id', 'comprobante', 'serie', 'numero'),)


class ItemsRecibos(models.Model):
    id_item = models.AutoField(primary_key=True)
    cantidad = models.IntegerField()
    descripcion = models.CharField(max_length=200, blank=True, null=True)
    valor_unitario = models.DecimalField(max_digits=20, decimal_places=10, blank=True, null=True)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    descuento = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    igv = models.DecimalField(max_digits=10, decimal_places=2)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    recibo = models.ForeignKey(Recibos, models.DO_NOTHING)
    catalogo_id = models.IntegerField()
    tipo_igv = models.ForeignKey(TiposIgv, models.DO_NOTHING, blank=True, null=True)
    creado = models.DateTimeField(blank=True, null=True)
    actualizado = models.DateTimeField(blank=True, null=True)
    detalles = models.CharField(max_length=2000, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "items_recibos"

    
class Ingresos(models.Model):
    id_ingreso = models.AutoField(primary_key=True)
    fecha_emision = models.DateTimeField(blank=True, null=True)
    numero = models.IntegerField(blank=True, null=True)
    moneda_id = models.IntegerField(blank=True, null=True)
    total = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    anulada = models.BooleanField()
    usuario_id = models.IntegerField(blank=True, null=True)
    negocio_id = models.IntegerField(blank=True, null=True)
    persona_id = models.IntegerField(blank=True, null=True)
    direccion = models.CharField(max_length=200, blank=True, null=True)
    motivo_baja = models.CharField(max_length=200, blank=True, null=True)
    fecha_baja = models.DateField(blank=True, null=True)
    recibo = models.ForeignKey('Recibos', models.DO_NOTHING, blank=True, null=True)
    serie = models.CharField(max_length=10)
    comprobante = models.ForeignKey('Comprobantes', models.DO_NOTHING, blank=True, null=True)
    canjeada = models.BooleanField()
    observaciones = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        managed = False
        db_table = "ingresos"
        unique_together = (('negocio_id', 'comprobante', 'serie', 'numero'),)


class IngresosDetalles(models.Model):
    id_ingreso_detalle = models.AutoField(primary_key=True)
    cantidad = models.IntegerField(blank=True, null=True)
    descripcion = models.CharField(max_length=200, blank=True, null=True)
    total = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    detalles = models.CharField(max_length=200, blank=True, null=True)
    ingreso = models.ForeignKey('Ingresos', models.DO_NOTHING, blank=True, null=True)
    catalogo_id = models.IntegerField(blank=True, null=True)
    creado = models.DateTimeField(blank=True, null=True)
    actualizado = models.DateTimeField(blank=True, null=True)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        managed = False
        db_table = "ingresos_detalles"