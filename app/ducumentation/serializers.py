from rest_framework import serializers
from . import models




class DocumentosGeneradosSerializer(serializers.ModelSerializer):
    """
    Serializer for the Documentogenerados model.
    This serializer is used to validate and serialize the Documentogenerados data.
    """

    class Meta:
        model = models.Documentogenerados
        fields = '__all__'