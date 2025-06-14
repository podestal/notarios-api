from rest_framework.viewsets import ModelViewSet
from rest_framework import status
from . import models
from . import serializers
from . import pagination
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q, Max, F, Func, Value
from django.db.models.functions import Cast, Substr
from django.db import models as django_models
from django.db import transaction

from collections import defaultdict
from . import utils


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

        contratantes_map = defaultdict(list)

        for c in contratantes:
            contratantes_map[c['kardex']].append(c['idcontratante'])
        print('contratantes_map:', contratantes_map)
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

        contratantes_map = defaultdict(list)

        for c in contratantes:
            contratantes_map[c['kardex']].append(c['idcontratante'])

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
        # clientes_map = defaultdict(list)
        # for c in cliente:
        #     clientes_map[c['idcontratante']].append(c)
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

        contratantes_map = defaultdict(list)

        for c in contratantes:
            contratantes_map[c['kardex']].append(c['idcontratante'])

        print('contratantes_map:', contratantes_map)

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

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return serializers.CreateContratantesSerializer
        return serializers.ContratantesSerializer
    
    def delete(self, request, *args, **kwargs):
        """
        Override the delete method to handle related Cliente2 records.
        """
        instance = self.get_object()
        # Delete related Cliente2 records
        models.Cliente2.objects.filter(idcontratante=instance.idcontratante).delete()
        return super().delete(request, *args, **kwargs)
    
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """
        Create a Contratante and a Cliente2 based on the provided idcliente.
        This method will generate new IDs for Contratante and Cliente2,
        and ensure that Cliente2 is not orphaned.
        """
        idcliente = request.query_params.get('idcliente')

        if not idcliente:
            return Response({"error": "Debe proporcionar el idcliente"}, status=400)

        # Step 1: Get Cliente1 info from numdoc
        print('idcliente:', idcliente)
        cliente1 = models.Cliente.objects.filter(idcliente=idcliente).first()
        if not cliente1:
            return Response({"error": "No se encontró Cliente1 con ese número de documento"}, status=404)

        # Step 2: Try up to 5 times to generate valid IDs
        for attempt in range(5):
            try:
                # Generate IDs
                idcontratante = utils.generate_new_id(models.Contratantes, 'idcontratante')
                idcliente2 = utils.generate_new_id(models.Cliente2, 'idcliente')

                # Check orphan
                if models.Cliente2.objects.filter(idcontratante=idcontratante).exists():
                    models.Cliente2.objects.filter(idcontratante=idcontratante).delete()
                    continue  # Try again with a new idcontratante

                # Create Contratante
                contratante_serializer = self.get_serializer(data=request.data)
                contratante_serializer.is_valid(raise_exception=True)
                contratante_serializer.save(idcontratante=idcontratante)

                # Build Cliente2 data from Cliente1
                # idcontratante: res.idcontratante,
                # //             tipper: cliente1.tipper, 
                # //             apepat: cliente1.apepat,
                # //             apemat: cliente1.apemat,
                # //             prinom: cliente1.prinom,
                # //             segnom: cliente1.segnom,
                # //             nombre: `${cliente1.prinom} ${cliente1.segnom} ${cliente1.apepat} ${cliente1.apemat}`,
                # //             direccion: cliente1.direccion,
                # //             idtipdoc: cliente1.idtipdoc,
                # //             numdoc: cliente1.numdoc,
                # //             email: cliente1.email,
                # //             telfijo: cliente1.telfijo,
                # //             telcel: cliente1.telcel,
                # //             telofi: cliente1.telofi || '',
                # //             sexo: cliente1.sexo || '',
                # //             idestcivil: cliente1.idestcivil || 0,
                # //             natper: cliente1.nacionalidad || '',
                # //             conyuge: '',
                # //             nacionalidad: cliente1.nacionalidad || '',
                # //             idprofesion: cliente1.idprofesion || 0,
                # //             detaprofesion: cliente1.detaprofesion || '',
                # //             idcargoprofe: cliente1.idcargoprofe || 0,
                # //             profocupa: cliente1.detaprofesion || '',
                # //             dirfer: cliente1.direccion,
                # //             idubigeo: cliente1.idubigeo || '.',
                # //             cumpclie: cliente1.cumpclie || '.',
                # //             razonsocial: cliente1.razonsocial || '',
                # //             fechaing: '',
                # //             residente: cliente1.resedente || '0',
                # //             tipocli: '0',
                # //             profesion_plantilla: cliente1.detaprofesion || '',
                # //             ubigeo_plantilla: cliente1.idubigeo || '',
                # //             fechaconstitu: '',
                # //             idsedereg: 1
                # {'domfiscal': [ErrorDetail(string='This field is required.', code='required')], 'telempresa': [ErrorDetail(string='This field is required.', code='required')], 'mailempresa': [ErrorDetail(string='This field is required.', code='required')], 'contacempresa': [ErrorDetail(string='This field is required.', code='required')], 'numregistro': [ErrorDetail(string='This field is required.', code='required')], 'numpartida': [ErrorDetail(string='This field is required.', code='required')], 'actmunicipal': [ErrorDetail(string='This field is required.', code='required')], 'impeingre': [ErrorDetail(string='This field is required.', code='required')], 'impnumof': [ErrorDetail(string='This field is required.', code='required')], 'impeorigen': [ErrorDetail(string='This field is required.', code='required')], 'impentidad': [ErrorDetail(string='This field is required.', code='required')], 'impremite': [ErrorDetail(string='This field is required.', code='required')], 'impmotivo': [ErrorDetail(string='This field is required.', code='required')], 'docpaisemi': [ErrorDetail(string='This field is required.', code='required')]}"
                cliente2_data = {
                    'idcliente': idcliente2,
                    'idcontratante': idcontratante,
                    'tipper': cliente1.tipper,
                    'apepat': cliente1.apepat,
                    'apemat': cliente1.apemat,
                    'prinom': cliente1.prinom,
                    'segnom': cliente1.segnom,
                    'nombre': f"{cliente1.prinom} {cliente1.segnom} {cliente1.apepat} {cliente1.apemat}",
                    'direccion': cliente1.direccion,
                    'idtipdoc': cliente1.idtipdoc,
                    'numdoc': cliente1.numdoc,
                    'email': cliente1.email,
                    'telfijo': cliente1.telfijo,
                    'telcel': cliente1.telcel,
                    'telofi': cliente1.telofi or '',
                    'sexo': cliente1.sexo or '',
                    'idestcivil': cliente1.idestcivil or 0,     
                    'natper': cliente1.nacionalidad or '',
                    'conyuge': '',
                    'nacionalidad': cliente1.nacionalidad or '',
                    'idprofesion': cliente1.idprofesion or 0,
                    'detaprofesion': cliente1.detaprofesion or '',
                    'idcargoprofe': cliente1.idcargoprofe or 0,
                    'profocupa': cliente1.detaprofesion or '',
                    'dirfer': cliente1.direccion,
                    'idubigeo': cliente1.idubigeo or '.',
                    'cumpclie': cliente1.cumpclie or '.',
                    'razonsocial': cliente1.razonsocial or '',
                    'fechaing': '',  # This will be set later
                    'residente': cliente1.residente or '0',
                    'tipocli': '0',
                    'profesion_plantilla': cliente1.detaprofesion or '',
                    'ubigeo_plantilla': cliente1.idubigeo or '',
                    'fechaconstitu': '',  # This will be set later
                    'idsedereg': 1,  # Assuming this is a constant value
                    'domfiscal': '',
                    'telempresa': '',
                    'mailempresa': '',
                    'contacempresa': '',
                    'numregistro': '',
                    'numpartida': '',
                    'actmunicipal': '',
                    'impeingre': '',
                    'impnumof': '',
                    'impeorigen': '',
                    'impentidad': '',
                    'impremite': '',
                    'impmotivo': '',
                    'docpaisemi': '',
                }

                cliente2_serializer = serializers.Cliente2Serializer(data=cliente2_data)
                cliente2_serializer.is_valid(raise_exception=True)
                cliente2_serializer.save()

                # Return created contratante
                return Response(contratante_serializer.data, status=status.HTTP_201_CREATED)

            except Exception as e:
                # Last attempt → return error
                if attempt == 4:
                    return Response({"error": f"Error al crear contratante/cliente2: {str(e)}"}, status=400)
                continue  # Try again with new IDs

        return Response({"error": "No se pudo generar un ID válido tras varios intentos"}, status=400)

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

        condicion_map = {
            c['idcondicion']: c
            for c in models.Actocondicion.objects.filter(
                idcondicion__in=contratantes_tipoactos
            ).values('idcondicion', 'condicion')
        }

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


class ClienteViewSet(ModelViewSet):
    """
    ViewSet for the Cliente model.
    """
    queryset = models.Cliente.objects.all()
    serializer_class = serializers.ClienteSerializer
    pagination_class = pagination.KardexPagination

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return serializers.CreateClienteSerializer
        return serializers.ClienteSerializer

    @action(detail=False, methods=['get'])
    def by_dni(self, request):
        """
        Get Cliente records by DNI.
        """
        dni = request.query_params.get('dni')
        if not dni:
            return Response(
                {"error": "dni parameter is required."},
                status=400
            )

        clientes = models.Cliente.objects.filter(numdoc=dni)
        if not clientes.exists():
            return Response({}, status=200)

        serializer = serializers.ClienteSerializer(clientes[len(clientes) - 1])
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

    @action(detail=False, methods=['get'])
    def by_tipoacto(self, request):
        """
        Get ActoCondicion records by tipoacto.
        """
        tipoacto = request.query_params.get('tipoacto')
        print()
        if not tipoacto:
            return Response(
                {"error": "tipoacto parameter is required."},
                status=400
            )

        acto_condiciones = models.Actocondicion.objects.filter(
            idtipoacto=tipoacto
        )

        if not acto_condiciones.exists():
            return Response({}, status=200)

        serializer = serializers.ActoCondicionSerializer(acto_condiciones, many=True)
        return Response(serializer.data)


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


class UbigeoViewSet(ModelViewSet):
    """
    ViewSet for the Ubigeo model.
    """
    queryset = models.Ubigeo.objects.all()
    serializer_class = serializers.UbigeoSerializer
    # pagination_class = pagination.KardexPagination
