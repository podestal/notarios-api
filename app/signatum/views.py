from django.shortcuts import render
from rest_framework import viewsets
from . import models, serializers


class NotarizationViewSet(viewsets.ModelViewSet):
    queryset = models.Notarization.objects.all()
    serializer_class = serializers.NotarizationSerializer


class NotarizationReservationViewSet(viewsets.ModelViewSet):
    queryset = models.NotarizationReservation.objects.all()
    serializer_class = serializers.NotarizationReservationSerializer

