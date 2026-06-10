# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = False` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models


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
    recibo = models.ForeignKey('Recibos', models.DO_NOTHING)
    catalogo_id = models.IntegerField()
    tipo_igv = models.ForeignKey('TiposIgv', models.DO_NOTHING, blank=True, null=True)
    creado = models.DateTimeField(blank=True, null=True)
    actualizado = models.DateTimeField(blank=True, null=True)
    detalles = models.CharField(max_length=2000, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'items_recibos'
