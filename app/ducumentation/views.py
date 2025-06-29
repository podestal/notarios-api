from django.shortcuts import render
from rest_framework.viewsets import ModelViewSet
from rest_framework.decorators import action
from rest_framework.response import Response
from . import models, serializers
from notaria import pagination


class DocumentosGeneradosViewSet(ModelViewSet):
    """
    ViewSet for the Documentogenerados model.
    """
    queryset = models.Documentogenerados.objects.all()
    serializer_class = serializers.DocumentosGeneradosSerializer
    pagination_class = pagination.KardexPagination

    @action(detail=False, methods=['get'])
    def by_kardex(self, request):
        """
        Get Documentogenerados records by Kardex.
        """
        kardex = request.query_params.get('kardex')
        if not kardex:
            return Response(
                {"error": "kardex parameter is required."},
                status=400
            )
        
        documentos_generados = models.Documentogenerados.objects.filter(kardex=kardex)
        if not documentos_generados.exists():
            return Response([], status=200)

        serializer = serializers.DocumentosGeneradosSerializer(documentos_generados, many=True)
        return Response(serializer.data)
