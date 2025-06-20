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

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """
        Override the create method to generate a Kardex number.
        """
        data = request.data.copy()
        idtipkar = data.get("idtipkar")
        fechaingreso = data.get("fechaingreso")
        idtipoacto = data.get("codactos")

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
        # # Save the new Kardex record
        data["kardex"] = new_kardex_number
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)

        try:
            tipo_acto = models.Tiposdeacto.objects.get(idtipoacto=idtipoacto)
        except models.Tiposdeacto.DoesNotExist:
            return Response(
                {"error": "Tipo de acto no encontrado."},
                status=404
            )

        detalle_data = {
            "kardex": new_kardex_number,
            "idtipoacto": idtipoacto,
            "actosunat": tipo_acto.actosunat,
            "actouif": tipo_acto.actouif,
            "idtipkar": int(idtipkar),
            "desacto": tipo_acto.desacto,
        }

        models.DetalleActosKardex.objects.create(**detalle_data)

        # Return the created Kardex object
        return Response(serializer.data, status=201)

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

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        """ 
        Update a Contratante and its related Contratantesxacto records.
        This method will update the Contratante and ensure that the related
        Contratantesxacto records are also updated based on the provided conditions.
        """
        print('updating Contratante')
        instance = self.get_object()
        data = request.data
        print('data:', data)
        data_conditions = []
        # item = instance.
        if '/' not in data.get('condicion'):
            data_conditions = [data.get('condicion')]
            item = instance
        else :
            data_conditions = data.get('condicion').split('/')
            item = data_conditions[0].split('.')[1] if '.' in data_conditions[0] else ''

        conditions = instance.condicion.split('/')
        item = conditions[0].split('.')[1] if '.' in conditions[0] else ''

        consditions_normalized = []

        for condition in conditions:
            if condition:
                idcondicion = condition.split('.')[0]
                consditions_normalized.append(idcondicion)

        set_data = set(data_conditions)
        set_conditions = set(consditions_normalized)

        # Check if the conditions in the data are already in the instance
        only_in_set_data = set_data - set_conditions
        # print('only_in_set_data:', only_in_set_data)

        for condition in only_in_set_data:
            print('adding contratantexacto for condition:', condition)
            # If the condition is in the data but not in the instance, add it
            acto_condicion = models.Actocondicion.objects.get(idcondicion=condition)
            models.Contratantesxacto.objects.create(
                idtipkar=acto_condicion.idtipoacto,
                kardex=data.get('kardex'),
                idtipoacto=acto_condicion.idtipoacto,
                idcontratante=instance.idcontratante,
                item=item,
                idcondicion=condition,
                parte=acto_condicion.parte,
                porcentaje='',
                uif=acto_condicion.uif,
                formulario=acto_condicion.formulario,
                monto='',
                opago='',
                ofondo='',
                montop=acto_condicion.montop
            )

        only_in_set_conditions = set_conditions - set_data
        # print('only_in_set_conditions:', only_in_set_conditions)
        for condition in only_in_set_conditions:
            print('removing contratantexacto for condition:', condition)
            # If the condition is in the instance but not in the data, delete it
            models.Contratantesxacto.objects.filter(
                idcontratante=instance.idcontratante,
                idcondicion=condition,
                kardex=instance.kardex,
                # item=instance.item
            ).delete()

        conditions_formatted_array = []
        for single_condition in  data.get('condicion').split('/'):
            if single_condition:
                conditions_formatted_array.append(f"{single_condition}.{item}/")

        data['condicion'] = ''.join(conditions_formatted_array)

        serializer = self.get_serializer(instance, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
    
    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        """
        Delete a Contratante and all related Cliente2 and Contratantesxacto records.
        """
        instance = self.get_object()

        # BEFORE REMOVE THE CONTRATANTE CHECK IF
        # - idcontratanterp filled
        #   - if so remove representante with the current contratante id
        # - check for all contratantes with the same kardex of the current one and if they have idcontratanterp field with the id of the current contratante
        #   - if so remove the idcontratanterp field from those contratantes as well as the representantes
        # Optional: delete related data
        models.Cliente2.objects.filter(idcontratante=instance.idcontratante).delete()
        models.Contratantesxacto.objects.filter(idcontratante=instance.idcontratante).delete()

        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """
        Create a Contratante and a Cliente2 based on the provided idcliente.
        This method will generate new IDs for Contratante and Cliente2,
        and ensure that Cliente2 is not orphaned.
        """
        idcliente = request.query_params.get('idcliente')
        data = request.data

        try:
            item = models.DetalleActosKardex.objects.get(
                kardex=data.get('kardex')
            ).item
        except models.DetalleActosKardex.DoesNotExist:
            return Response(
                {"error": "DetalleActosKardex not found for the provided kardex."},
                status=404
            )

        conditions = []
        
        if '/' not in data.get('condicion'):
            conditions = [data.get('condicion')]
            data['condicion'] = f"{data.get('condicion')}.{item}/"  # Ensure it has a sub-condition

        else:
            conditions = data.get('condicion').split('/')
            conditions_array = []
            for condition in conditions:
                conditions_array.append(f"{condition}.{item}/")
            data['condicion'] = ''.join(conditions_array)

        if not idcliente:
            return Response({"error": "Debe proporcionar el idcliente"}, status=400)

        # Step 1: Get Cliente1 info from numdoc

        cliente1 = models.Cliente.objects.filter(idcliente=idcliente).first()
        if not cliente1:
            return Response({"error": "No se encontró Cliente1 con ese número de documento"}, status=404)

        # Step 2: Try up to 5 times to generate valid IDs
        for attempt in range(5):
            try:
                sid = transaction.savepoint()
                # Generate IDs
                idcontratante = utils.generate_new_id(models.Contratantes, 'idcontratante')
                idcliente2 = utils.generate_new_id(models.Cliente2, 'idcliente')

                for condition in conditions:
                    acto_condicion = models.Actocondicion.objects.get(idcondicion=condition)
                    models.Contratantesxacto.objects.create(
                        idtipkar=acto_condicion.idtipoacto,
                        kardex=data.get('kardex'),
                        idtipoacto=acto_condicion.idtipoacto,
                        idcontratante=idcontratante,
                        item=item,
                        idcondicion=condition,
                        parte=acto_condicion.parte,
                        porcentaje='',
                        uif=acto_condicion.uif,
                        formulario=acto_condicion.formulario,
                        monto='',
                        opago='',
                        ofondo='',
                        montop=acto_condicion.montop
                    )

                # Check orphan
                if models.Cliente2.objects.filter(idcontratante=idcontratante).exists():
                    models.Cliente2.objects.filter(idcontratante=idcontratante).delete()
                    continue  # Try again with a new idcontratante

                # Create Contratante
                contratante_serializer = self.get_serializer(data=request.data)
                contratante_serializer.is_valid(raise_exception=True)
                contratante_serializer.save(idcontratante=idcontratante)

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
                transaction.savepoint_commit(sid)
                return Response(contratante_serializer.data, status=status.HTTP_201_CREATED)

            except Exception as e:
                transaction.savepoint_rollback(sid)
                if attempt == 4:
                    return Response({"error": f"Error al crear contratante/cliente2: {str(e)}"}, status=400)
                continue

        return Response({"error": "No se pudo generar un ID válido tras varios intentos"}, status=400)

    # @transaction.atomic
    # def create(self, request, *args, **kwargs):
    #     idcliente = request.query_params.get('idcliente')
    #     data = request.data

    #     try:
    #         item = models.DetalleActosKardex.objects.get(
    #             kardex=data.get('kardex')
    #         ).item
    #     except models.DetalleActosKardex.DoesNotExist:
    #         return Response(
    #             {"error": "DetalleActosKardex not found for the provided kardex."},
    #             status=404
    #         )

    #     if '/' not in data.get('condicion'):
    #         data['condicion'] = f"{data.get('condicion')}.{item}/"
    #         conditions = [data['condicion']]
    #     else:
    #         conditions_array = []
    #         for condition in data.get('condicion').split('/'):
    #             if condition:
    #                 conditions_array.append(f"{condition}.{item}/")
    #         conditions = conditions_array
    #         data['condicion'] = ''.join(conditions_array)

    #     if not idcliente:
    #         return Response({"error": "Debe proporcionar el idcliente"}, status=400)

    #     cliente1 = models.Cliente.objects.filter(idcliente=idcliente).first()
    #     if not cliente1:
    #         return Response({"error": "No se encontró Cliente1 con ese número de documento"}, status=404)

    #     for attempt in range(5):
    #         sid = transaction.savepoint()  # Create savepoint for rollback
    #         try:
    #             idcontratante = utils.generate_new_id(models.Contratantes, 'idcontratante')
    #             idcliente2 = utils.generate_new_id(models.Cliente2, 'idcliente')

    #             for singleCondition in conditions:
    #                 print('condition:', singleCondition)
    #                 acto_condicion = models.Actocondicion.objects.get(idcondicion=singleCondition)
    #                 models.Contratantesxacto.objects.create(
    #                     idtipkar=acto_condicion.idtipoacto,
    #                     kardex=data.get('kardex'),
    #                     idtipoacto=acto_condicion.idtipoacto,
    #                     idcontratante=idcontratante,
    #                     item=item,
    #                     idcondicion=singleCondition,
    #                     parte=acto_condicion.parte,
    #                     porcentaje='',
    #                     uif=acto_condicion.uif,
    #                     formulario=acto_condicion.formulario,
    #                     monto='',
    #                     opago='',
    #                     ofondo='',
    #                     montop=acto_condicion.montop
    #                 )

    #             if models.Cliente2.objects.filter(idcontratante=idcontratante).exists():
    #                 models.Cliente2.objects.filter(idcontratante=idcontratante).delete()
    #                 transaction.savepoint_rollback(sid)
    #                 continue

    #             contratante_serializer = self.get_serializer(data=request.data)
    #             contratante_serializer.is_valid(raise_exception=True)
    #             contratante_serializer.save(idcontratante=idcontratante)

    #             cliente2_data = {
    #                 'idcliente': idcliente2,
    #                 'idcontratante': idcontratante,
    #                 'tipper': cliente1.tipper,
    #                 'apepat': cliente1.apepat,
    #                 'apemat': cliente1.apemat,
    #                 'prinom': cliente1.prinom,
    #                 'segnom': cliente1.segnom,
    #                 'nombre': f"{cliente1.prinom} {cliente1.segnom} {cliente1.apepat} {cliente1.apemat}",
    #                 'direccion': cliente1.direccion,
    #                 'idtipdoc': cliente1.idtipdoc,
    #                 'numdoc': cliente1.numdoc,
    #                 'email': cliente1.email,
    #                 'telfijo': cliente1.telfijo,
    #                 'telcel': cliente1.telcel,
    #                 'telofi': cliente1.telofi or '',
    #                 'sexo': cliente1.sexo or '',
    #                 'idestcivil': cliente1.idestcivil or 0,
    #                 'natper': cliente1.nacionalidad or '',
    #                 'conyuge': '',
    #                 'nacionalidad': cliente1.nacionalidad or '',
    #                 'idprofesion': cliente1.idprofesion or 0,
    #                 'detaprofesion': cliente1.detaprofesion or '',
    #                 'idcargoprofe': cliente1.idcargoprofe or 0,
    #                 'profocupa': cliente1.detaprofesion or '',
    #                 'dirfer': cliente1.direccion,
    #                 'idubigeo': cliente1.idubigeo or '.',
    #                 'cumpclie': cliente1.cumpclie or '.',
    #                 'razonsocial': cliente1.razonsocial or '',
    #                 'fechaing': '',
    #                 'residente': cliente1.residente or '0',
    #                 'tipocli': '0',
    #                 'profesion_plantilla': cliente1.detaprofesion or '',
    #                 'ubigeo_plantilla': cliente1.idubigeo or '',
    #                 'fechaconstitu': '',
    #                 'idsedereg': 1,
    #                 'domfiscal': '',
    #                 'telempresa': '',
    #                 'mailempresa': '',
    #                 'contacempresa': '',
    #                 'numregistro': '',
    #                 'numpartida': '',
    #                 'actmunicipal': '',
    #                 'impeingre': '',
    #                 'impnumof': '',
    #                 'impeorigen': '',
    #                 'impentidad': '',
    #                 'impremite': '',
    #                 'impmotivo': '',
    #                 'docpaisemi': '',
    #             }

    #             cliente2_serializer = serializers.Cliente2Serializer(data=cliente2_data)
    #             cliente2_serializer.is_valid(raise_exception=True)
    #             cliente2_serializer.save()

    #             transaction.savepoint_commit(sid)
    #             return Response(contratante_serializer.data, status=status.HTTP_201_CREATED)

    #         except Exception as e:
    #             transaction.savepoint_rollback(sid)
    #             if attempt == 4:
    #                 return Response({"error": f"Error al crear contratante/cliente2: {str(e)}"}, status=400)
    #             continue

    #     return Response({"error": "No se pudo generar un ID válido tras varios intentos"}, status=400)


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
                'idcontratante', 'nombre', 'numdoc', 'idcliente'
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
    

class ContratantesxactoViewSet(ModelViewSet):
    """
    ViewSet for the Contratantesxacto model.
    """
    queryset = models.Contratantesxacto.objects.all()
    serializer_class = serializers.ContratantesxactoSerializer
    pagination_class = pagination.KardexPagination

    # def get_serializer_class(self):
    #     if self.request.method == 'POST':
    #         return serializers.CreateContratantesxactoSerializer
    #     return serializers.ContratantesxactoSerializer


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

    @action(detail=False, methods=['get'])
    def by_contratante(self, request):
        """
        Get Cliente2 records by Contratante ID.
        """
        idcontratante = request.query_params.get('idcontratante')
        if not idcontratante:
            return Response(
                {"error": "idcontratante parameter is required."},
                status=400
            )   
        cliente = models.Cliente2.objects.get(idcontratante=idcontratante)
        if not cliente:
            return Response({}, status=200)     
        serializer = serializers.Cliente2Serializer(cliente)
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

class SedesRegistralesViewSet(ModelViewSet):
    """
    ViewSet for the SedesRegistrales model.
    """
    queryset = models.Sedesregistrales.objects.all()
    serializer_class = serializers.SedesregistralesSerializer


class RepresentantesViewSet(ModelViewSet):
    """
    ViewSet for the Representantes model.
    """
    queryset = models.Representantes.objects.all()
    serializer_class = serializers.RepresentantesSerializer
    pagination_class = pagination.KardexPagination


class PatrimonialViewSet(ModelViewSet):
    """
    ViewSet for the Patrimonial model.
    """
    queryset = models.Patrimonial.objects.all()
    serializer_class = serializers.PatrimonialSerializer
    pagination_class = pagination.KardexPagination

    @action(detail=False, methods=['get'])
    def by_kardex(self, request):
        """
        Get Patrimonial records by Kardex.
        """
        kardex = request.query_params.get('kardex')
        if not kardex:
            return Response(
                {"error": "kardex parameter is required."},
                status=400
            )
        
        patrimonial = models.Patrimonial.objects.filter(kardex=kardex)
        if not patrimonial.exists():
            return Response([], status=200)

        serializer = serializers.PatrimonialSerializer(patrimonial, many=True)
        return Response(serializer.data)

