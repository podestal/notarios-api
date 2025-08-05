from django.db import models


class Viaje(models.Model):
    id_viaje = models.IntegerField(primary_key=True)
    num_kardex = models.CharField(max_length=30, blank=True, null=True)
    asunto = models.CharField(max_length=1000, blank=True, null=True)
    fecha_ingreso = models.DateField(blank=True, null=True)	
    referencia = models.CharField(max_length=3000, blank=True, null=True)
    num_formu = models.CharField(max_length=30, blank=True, null=True)
    lugar_formu = models.CharField(max_length=3000, blank=True, null=True)
    observacion = models.TextField(blank=True, null=True)
    sede_regis = models.CharField(max_length=200, blank=True, null=True)
    via = models.CharField(max_length=60, blank=True, null=True)
    fecha_desde = models.DateField(blank=True, null=True)
    fecha_hasta = models.DateField(blank=True, null=True)


class Participante(models.Model):
    id_viaje = models.IntegerField(blank=True, null=True)
    documento = models.CharField(max_length=30, blank=True, null=True)
    nombres = models.CharField(max_length=2000, blank=True, null=True)
    condicion = models.CharField(max_length=30, blank=True, null=True)
    edad = models.CharField(max_length=10, blank=True, null=True)
    incapacidad = models.CharField(max_length=2000, blank=True, null=True)

