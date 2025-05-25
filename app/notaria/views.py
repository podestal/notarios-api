from rest_framework.viewsets import ModelViewSet
from . import models
from . import serializers
from . import pagination
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q


'''
ViewSets for the Notaria app.
These viewsets define the views for the Notaria app.
They are used to handle HTTP requests and responses.
They are also used to define the URL patterns for the Notaria app.
'''


class UsuariosViewSet(ModelViewSet):
    """
    ViewSet for the Usuarios model.
    """
    queryset = models.Usuarios.objects.all()
    serializer_class = serializers.UsuariosSerializer


class PermisosUsuariosViewSet(ModelViewSet):
    """
    ViewSet for the PermisosUsuarios model.
    """
    queryset = models.PermisosUsuarios.objects.all()
    serializer_class = serializers.PermisosUsuariosSerializer


class KardexViewSet(ModelViewSet):
    """
    ViewSet for the Kardex model.
    """
    serializer_class = serializers.KardexSerializer
    pagination_class = pagination.KardexPagination

    def get_queryset(self):
        idtipkar = self.request.query_params.get('idtipkar')
        if idtipkar:
            kardex_qs = models.Kardex.objects.filter(
                idtipkar=idtipkar
            ).order_by('-fechaingreso')

            return kardex_qs

        return None

    def list(self, request, *args, **kwargs):
        """
        List all Kardex objects.
        """
        page_kardex = self.paginate_queryset(self.get_queryset())

        user_ids = set(obj.idusuario for obj in page_kardex)
        kardex_ids = set(obj.kardex for obj in page_kardex)

        usuarios_map = {
            u.idusuario: u
            for u in models.Usuarios.objects.filter(idusuario__in=user_ids)
        }

        contratantes = models.Contratantes.objects.filter(
            kardex__in=kardex_ids
        ).values('idcontratante', 'kardex')
        contratantes_map = {
            c['kardex']: c['idcontratante']
            for c in contratantes
        }

        contratante_ids = set(c['idcontratante'] for c in contratantes)

        clientes_map = {
            c['idcontratante']: c
            for c in models.Cliente2.objects.filter(
                idcontratante__in=contratante_ids
            ).values(
                'idcontratante', 'nombre', 'numdoc'
            )
        }

        # Pass context manually to serializer if needed
        serializer = self.get_serializer(page_kardex, many=True, context={
            'usuarios_map': usuarios_map,
            'contratantes_map': contratantes_map,
            'clientes_map': clientes_map,
        })

        return self.get_paginated_response(serializer.data)

    @action(detail=False, methods=['get'])
    def kardex_by_correlative(self, request):
        """
        Get Kardex records by correlative prefix (kardex__startswith).
        """
        correlative = request.query_params.get('correlative')
        idtipkar = self.request.query_params.get('idtipkar')

        if not correlative:
            return Response(
                {"error": "correlative parameter is required."},
                status=400
            )

        # Get the filtered queryset
        kardex_qs = models.Kardex.objects.filter(
            kardex__startswith=correlative,
            idtipkar=idtipkar
        )

        if not kardex_qs.exists():
            return Response({}, status=200)

        # Prepare optimized data maps (same as in list)
        user_ids = set(obj.idusuario for obj in kardex_qs)
        kardex_ids = set(obj.kardex for obj in kardex_qs)

        usuarios_map = {
            u.idusuario: u
            for u in models.Usuarios.objects.filter(idusuario__in=user_ids)
        }

        contratantes = models.Contratantes.objects.filter(
            kardex__in=kardex_ids
        ).values('idcontratante', 'kardex')

        contratantes_map = {c['kardex']: c['idcontratante'] for c in contratantes}
        contratante_ids = set(c['idcontratante'] for c in contratantes)

        clientes_map = {
            c['idcontratante']: c
            for c in models.Cliente2.objects.filter(idcontratante__in=contratante_ids)
            .values('idcontratante', 'idcliente', 'nombre')
        }

        # Pass context manually
        serializer = serializers.KardexSerializer(kardex_qs, many=True, context={
            'usuarios_map': usuarios_map,
            'contratantes_map': contratantes_map,
            'clientes_map': clientes_map,
        })

        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def by_name(self, request):
        """
        Get Kardex records by name.
        """
        name = request.query_params.get('name')
        idtipkar = self.request.query_params.get('idtipkar')
        if not name:
            return Response(
                {"error": "name parameter is required."},
                status=400
            )
        print('name:', name)
        cliente = models.Cliente2.objects.filter(
            Q(nombre__icontains=name) |
            Q(apepat__icontains=name) |
            Q(apemat__icontains=name) |
            Q(prinom__icontains=name) |
            Q(segnom__icontains=name)
        ).values('idcontratante', 'idcliente', 'nombre', 'numdoc')

        print('cliente:', cliente)
        clientes_map = {c['idcontratante']: c for c in cliente}

        if not cliente.exists():
            return Response(
                {"error": "No records found for the given name."},
                status=404
            )
        
        contratantes_ids = [c["idcontratante"] for c in cliente]
        contratantes = models.Contratantes.objects.filter(
            idcontratante__in=contratantes_ids
        ).values('idcontratante', 'kardex')

        contratantes_map = {c['kardex']: c['idcontratante'] for c in contratantes}

        kardex_ids = [c['kardex'] for c in contratantes]
        kardex_qs = models.Kardex.objects.filter(
            kardex__in=kardex_ids,
            idtipkar=idtipkar
        ).order_by('-fechaingreso')

        if not kardex_qs.exists():
            return Response({}, status=200)

        paginator = self.paginator
        paginated_kardex = paginator.paginate_queryset(kardex_qs, request)

        user_ids = set(obj.idusuario for obj in kardex_qs)

        usuarios_map = {
            u.idusuario: u
            for u in models.Usuarios.objects.filter(idusuario__in=user_ids)
        }

        serializer = serializers.KardexSerializer(paginated_kardex, many=True, context={
            'usuarios_map': usuarios_map,
            'contratantes_map': contratantes_map,
            'clientes_map': clientes_map,
        })

        return self.get_paginated_response(serializer.data)

    @action(detail=False, methods=['get'])
    def by_document(self, request):
        """
        Get Kardex records by name.
        """
        document = request.query_params.get('document')
        idtipkar = self.request.query_params.get('idtipkar')
        if not document:
            return Response(
                {"error": "name parameter is required."},
                status=400
            )
        
        cliente = models.Cliente2.objects.filter(
            numdoc__icontains=document
        ).values('idcontratante', 'idcliente', 'nombre')
        clientes_map = {c['idcontratante']: c for c in cliente}

        if not cliente.exists():
            return Response(
                {"error": "No records found for the given name."},
                status=404
            )
        
        contratantes_ids = [c["idcontratante"] for c in cliente]
        contratantes = models.Contratantes.objects.filter(
            idcontratante__in=contratantes_ids
        ).values('idcontratante', 'kardex')

        contratantes_map = {c['kardex']: c['idcontratante'] for c in contratantes}

        kardex_ids = [c['kardex'] for c in contratantes]
        kardex_qs = models.Kardex.objects.filter(
            kardex__in=kardex_ids,
            idtipkar=idtipkar
        ).order_by('-fechaingreso')

        if not kardex_qs.exists():
            return Response({}, status=200)

        paginator = self.paginator
        paginated_kardex = paginator.paginate_queryset(kardex_qs, request)

        user_ids = set(obj.idusuario for obj in kardex_qs)

        usuarios_map = {
            u.idusuario: u
            for u in models.Usuarios.objects.filter(idusuario__in=user_ids)
        }

        serializer = serializers.KardexSerializer(paginated_kardex, many=True, context={
            'usuarios_map': usuarios_map,
            'contratantes_map': contratantes_map,
            'clientes_map': clientes_map,
        })

        return self.get_paginated_response(serializer.data)


class TipoKarViewSet(ModelViewSet):
    """
    ViewSet for the TipoKar model.
    """
    queryset = models.Tipokar.objects.all()
    serializer_class = serializers.TipoKarSerializer


class ContratantesViewSet(ModelViewSet):
    """
    ViewSet for the Contratante model.
    """
    queryset = models.Contratantes.objects.all()
    serializer_class = serializers.ContratantesSerializer
    pagination_class = pagination.KardexPagination


class Cliente2ViewSet(ModelViewSet):
    """
    ViewSet for the Cliente2 model.
    """
    queryset = models.Cliente2.objects.all()
    serializer_class = serializers.Cliente2Serializer
    pagination_class = pagination.KardexPagination
