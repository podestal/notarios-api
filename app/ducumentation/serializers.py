from rest_framework import serializers
from . import models

class TemplateSerializer(serializers.ModelSerializer):
    """
    Serializer for the TplTemplate model.
    This serializer is used to validate and serialize the TplTemplate data.
    """

    class Meta:
        model = models.TplTemplate
        fields = '__all__'


class DocumentosGeneradosSerializer(serializers.ModelSerializer):
    """
    Serializer for the Documentogenerados model.
    This serializer is used to validate and serialize the Documentogenerados data.
    """

    class Meta:
        model = models.Documentogenerados
        fields = '__all__'