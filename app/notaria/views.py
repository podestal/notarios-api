from rest_framework.viewsets import ModelViewSet
from . import models
from . import serializers
from . import pagination
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q, Max, F, Func, Value
from django.db.models.functions import Cast, Substr
from django.db import models as django_models

from collections import defaultdict

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
        idtipkar = self.request.query_params.get('idtipkar', '0')
        if idtipkar:
            kardex_qs = models.Kardex.objects.filter(
                idtipkar=idtipkar
            ).order_by('-idkardex')

            return kardex_qs

        return None
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return serializers.CreateKardexSerializer
        return serializers.KardexSerializer

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

        contratantes_map = defaultdict(list)

        for c in contratantes:
            contratantes_map[c['kardex']].append(c['idcontratante'])
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
    
    def create(self, request, *args, **kwargs):
        """
        Override the create method to generate a Kardex number.
        """
        data = request.data.copy()
        idtipkar = data.get("idtipkar")
        fechaingreso = data.get("fechaingreso")

        # Validate required fields
        if not idtipkar or not fechaingreso:
            return Response({"error": "Missing required fields"}, status=400)

        # Extract the year from fechaingreso
        try:
            anio = fechaingreso.split("/")[-1]  # Assuming format is DD/MM/YYYY
        except IndexError:
            return Response({"error": "Invalid fechaingreso format"}, status=400)

        # Get abbreviation based on tipoescritura
        abreviatura_map = {
            "1": "KAR",  # ESCRITURAS PUBLICAS
            "2": "NCT",  # ASUNTOS NO CONTENCIOSOS
            "3": "ACT",  # TRANSFERENCIAS VEHICULARES
            "4": "GAM",  # GARANTIAS MOBILIARIAS
            "5": "TES",  # TESTAMENTOS
        }
        abreviatura = abreviatura_map.get(str(idtipkar))
        if not abreviatura:
            return Response({"error": "Invalid tipoescritura"}, status=400)

        # Query the last Kardex number for the given idtipkar and year
        last_kardex = models.Kardex.objects.filter(
            idtipkar=idtipkar,
            fechaingreso__endswith=anio,  # Match the year in fechaingreso
            kardex__startswith=abreviatura
        ).annotate(
            numeric_part=Cast(Substr(F('kardex'), len(abreviatura) + 1, 4), output_field=django_models.IntegerField())
        ).order_by('-numeric_part').first()

        # # Extract the numeric part of the last Kardex number
        if last_kardex and last_kardex.kardex:
            try:
                numeric_part = int("".join(filter(str.isdigit, last_kardex.kardex.split("-")[0])))
            except ValueError:
                numeric_part = 0
        else:
            numeric_part = 0  # Start from 0 if no Kardex exists
        # # Increment the numeric part and generate the new Kardex number
        new_kardex_number = f"{abreviatura}{numeric_part + 1}-{anio}"
        print('new_kardex_number:', new_kardex_number)
        # # Save the new Kardex record
        data["kardex"] = new_kardex_number
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        return Response(serializer.data, status=201)

        # return Response([], status=200)

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

        paginator = self.paginator
        paginated_kardex = paginator.paginate_queryset(kardex_qs, request)

        # Order by fechaingreso

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
        serializer = serializers.KardexSerializer(paginated_kardex, many=True, context={
            'usuarios_map': usuarios_map,
            'contratantes_map': contratantes_map,
            'clientes_map': clientes_map,
        })

        return self.get_paginated_response(serializer.data)

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

        cliente = models.Cliente2.objects.filter(
            Q(nombre__icontains=name) |
            Q(apepat__icontains=name) |
            Q(apemat__icontains=name) |
            Q(prinom__icontains=name) |
            Q(segnom__icontains=name)
        ).values('idcontratante', 'idcliente', 'nombre', 'numdoc')

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

    @action(detail=False, methods=['get'])
    def by_numescritura(self, request):
        """
        Get Kardex records by numescritura.
        """
        numescritura = request.query_params.get('numescritura')
        idtipkar = self.request.query_params.get('idtipkar')
        if not numescritura:
            return Response(
                {"error": "numescritura parameter is required."},
                status=400
            )

        kardex_qs = models.Kardex.objects.filter(
            numescritura=numescritura,
            idtipkar=idtipkar
        ).order_by('-fechaingreso')

        if not kardex_qs.exists():
            return Response({}, status=200)

        paginator = self.paginator
        paginated_kardex = paginator.paginate_queryset(kardex_qs, request)

        user_ids = set(obj.idusuario for obj in paginated_kardex)
        kardex_ids = set(obj.kardex for obj in paginated_kardex)

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

    @action(detail=False, methods=['get'])
    def by_kardex(self, request):
        """
        Get Contratantes by Kardex.
        """
        kardex = request.query_params.get('kardex')
        if not kardex:
            return Response(
                {"error": "kardex parameter is required."},
                status=400
            )
        contratantes = models.Contratantes.objects.filter(kardex=kardex)
        contratante_ids = set(c.idcontratante for c in contratantes)

        contratantes_tipoactos = set(
            c.condicion.split('.')[0] for c in contratantes
        )
        print('contratantes_tipoactos:', contratantes_tipoactos)

        condicion_map = {
            c['idcondicion']: c
            for c in models.Actocondicion.objects.filter(
                idcondicion__in=contratantes_tipoactos
            ).values('idcondicion', 'condicion')
        }

        print('condicion_map:', condicion_map)

        clientes_map = {
            c['idcontratante']: c
            for c in models.Cliente2.objects.filter(
                idcontratante__in=contratante_ids
            ).values(
                'idcontratante', 'nombre', 'numdoc'
            )
        }

        if not contratantes.exists():
            return Response({}, status=200)

        serializer = serializers.ContratantesKardexSerializer(
            contratantes,
            many=True,
            context={
                'clientes_map': clientes_map,
                'condicion_map': condicion_map
            })
        return Response(serializer.data)


class Cliente2ViewSet(ModelViewSet):
    """
    ViewSet for the Cliente2 model.
    """
    queryset = models.Cliente2.objects.all()
    serializer_class = serializers.Cliente2Serializer
    pagination_class = pagination.KardexPagination

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return serializers.CreateCliente2Serializer
        return serializers.Cliente2Serializer

    @action(detail=False, methods=['get'])
    def by_dni(self, request):
        """
        Get Cliente2 records by DNI.
        """
        dni = request.query_params.get('dni')
        if not dni:
            return Response(
                {"error": "dni parameter is required."},
                status=400
            )

        clientes = models.Cliente2.objects.filter(numdoc=dni)
        if not clientes.exists():
            return Response({}, status=200)

        serializer = serializers.Cliente2Serializer(clientes[len(clientes) - 1])
        return Response(serializer.data)


class TiposDeActosViewSet(ModelViewSet):
    """
    ViewSet for the TiposDeActos model.
    """
    queryset = models.Tiposdeacto.objects.all()
    serializer_class = serializers.TiposDeActosSerializer


class ActoCondicionViewSet(ModelViewSet):
    """
    ViewSet for the ActoCondicion model.
    """
    queryset = models.Actocondicion.objects.all()
    serializer_class = serializers.ActoCondicionSerializer


class DetalleActosKardexViewSet(ModelViewSet):
    """
    ViewSet for the DetalleActosKardex model.
    """
    queryset = models.DetalleActosKardex.objects.all()
    serializer_class = serializers.DetalleActosKardexSerializer
    pagination_class = pagination.KardexPagination


class TbAbogadoViewSet(ModelViewSet):
    """
    ViewSet for the TbAbogado model.
    """
    queryset = models.TbAbogado.objects.all()
    serializer_class = serializers.TbAbogadoSerializer


class NacionalidadesViewSet(ModelViewSet):
    """
    ViewSet for the Nacionalidades model.
    """
    queryset = models.Nacionalidades.objects.all()
    serializer_class = serializers.NacionalidadesSerializer


class ProfesionesViewSet(ModelViewSet):
    """
    ViewSet for the Profesiones model.
    """
    queryset = models.Profesiones.objects.all()
    serializer_class = serializers.ProfesionesSerializer


class CargoprofeViewSet(ModelViewSet):
    """
    ViewSet for the Cargoprofe model.
    """
    queryset = models.Cargoprofe.objects.all()
    serializer_class = serializers.CargoprofeSerializer
