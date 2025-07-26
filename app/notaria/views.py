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
        idtipkar = self.request.query_params.get('idtipkar')
        qs = models.Kardex.objects.all().order_by('-idkardex')
        if idtipkar is not None:
            qs = qs.filter(idtipkar=idtipkar)
        return qs
    
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
                'idcontratante', 'nombre', 'numdoc', 'razonsocial'
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
    def update(self, request, *args, **kwargs):

        instance = self.get_object()
        data = request.data
        codactos = data.get('codactos', '')
        id_tipo_actos_array = [codactos[i:i+3] for i in range(0, len(codactos), 3)]
        set_data = set(id_tipo_actos_array)
        id_tipo_actos_array_instance =  [ instance.codactos[i:i+3] for i in range(0, len( instance.codactos), 3)]
        set_instance = set(id_tipo_actos_array_instance)

        only_in_set_data = set_data - set_instance
        only_in_set_conditions = set_instance - set_data

        for id_tipo_acto in only_in_set_conditions:
            try:
                tipo_acto = models.Tiposdeacto.objects.get(idtipoacto=id_tipo_acto)
            except tipo_acto.DoesNotExist:
                return Response(
                    {"error": "Tipo de acto no encontrado."},
                    status=404
                )
            
            # Check if there are any contratantes using this tipo_acto
            if models.Contratantesxacto.objects.filter(
                kardex=instance.kardex,
                idtipoacto=id_tipo_acto
            ).exists():
                return Response(
                    {"error": "No se puede eliminar el tipo de acto porque hay contratantes asociados."},
                    status=400
                )

            # chec if there any patrimonial records using this tipo_acto
            if models.Patrimonial.objects.filter(
                kardex=instance.kardex,
                idtipoacto=id_tipo_acto
            ).exists():
                return Response(
                    {"error": "No se puede eliminar el tipo de acto porque hay patrimoniales asociados."},
                    status=400
                )

            # If no contratantes are using this tipo_acto, delete the detalle acto
            models.DetalleActosKardex.objects.filter(
                kardex=instance.kardex,
                idtipoacto=id_tipo_acto
            ).delete()

        for id_tipo_acto in only_in_set_data:
            try:
                tipo_acto = models.Tiposdeacto.objects.get(idtipoacto=id_tipo_acto)
            except models.Tiposdeacto.DoesNotExist:
                return Response(
                    {"error": "Tipo de acto no encontrado."},
                    status=404
                )
            
            detalle_data = {
                "kardex": instance.kardex,
                "idtipoacto": id_tipo_acto,
                "actosunat": tipo_acto.actosunat,
                "actouif": tipo_acto.actouif,
                "idtipkar": int(instance.idtipkar),
                "desacto": tipo_acto.desacto,
            }

            models.DetalleActosKardex.objects.create(**detalle_data)
        
        return super().update(request, *args, **kwargs)

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """
        Override the create method to generate a Kardex number.
        """
        data = request.data.copy()
        idtipkar = data.get("idtipkar")
        fechaingreso = data.get("fechaingreso")
        idtipoactos = data.get("codactos")

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

        id_tipo_actos_array = [idtipoactos[i:i+3] for i in range(0, len(idtipoactos), 3)]
        for idtipoacto in id_tipo_actos_array:
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

        instance = self.get_object()
        data = request.data

        data_conditions = data.get('condicion').split('/') if data.get('condicion') else []
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
        set_conditions = set(conditions)

        # Check if the conditions in the data are already in the instance
        only_in_set_data = set_data - set_conditions

        for condition in only_in_set_data:

            if condition:
                idcondicion, item = condition.split('.')
                acto_condicion = models.Actocondicion.objects.get(idcondicion=idcondicion)
                models.Contratantesxacto.objects.create(
                    idtipkar=acto_condicion.idtipoacto,
                    kardex=data.get('kardex'),
                    idtipoacto=acto_condicion.idtipoacto,
                    idcontratante=instance.idcontratante,
                    item=item,
                    idcondicion=idcondicion,
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
        for condition in only_in_set_conditions:
            if condition:
                idcondicion, item = condition.split('.')
                print('removing contratantexacto for condition:', condition)
                # If the condition is in the instance but not in the data, delete it
                models.Contratantesxacto.objects.filter(
                    idcontratante=instance.idcontratante,
                    idcondicion=idcondicion,
                    kardex=instance.kardex,
                    # item=instance.item
                ).delete()

        # conditions_formatted_array = []
        # for single_condition in  data.get('condicion').split('/'):
        #     if single_condition:
        #         conditions_formatted_array.append(f"{single_condition}.{item}/")

        # data['condicion'] = ''.join(conditions_formatted_array)

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

                conditions = data.get('condicion').split('/')
                for condition in conditions:
                    if condition:
                        idcondicion, item = condition.split('.')
                        acto_condicion = models.Actocondicion.objects.get(idcondicion=idcondicion)
                        models.Contratantesxacto.objects.create(
                            idtipkar=acto_condicion.idtipoacto,
                            kardex=data.get('kardex'),
                            idtipoacto=acto_condicion.idtipoacto,
                            idcontratante=idcontratante,
                            item=item,
                            idcondicion=idcondicion,
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
                    'domfiscal': cliente1.domfiscal or '',
                    'telempresa': cliente1.telofi or '',
                    'mailempresa': cliente1.email or '',
                    'contacempresa': cliente1.contacempresa or '',
                    'numregistro': cliente1.numregistro or '',
                    'numpartida':  cliente1.numpartida or '',
                    'actmunicipal': cliente1.actmunicipal or '',
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
                'idcontratante', 'nombre', 'numdoc', 'idcliente', 'razonsocial'
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

    @action(detail=False, methods=['get'])
    def by_ruc(self, request):
        """
        Get Cliente records by RUC.
        """
        ruc = request.query_params.get('ruc')
        if not ruc:
            return Response(
                {"error": "ruc parameter is required."},
                status=400
            )

        clientes = models.Cliente.objects.filter(numdoc=ruc)
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

    @action(detail=False, methods=['get'])
    def by_kardex_tipoacto(self, request):
        """
        Get DetalleActosKardex records by kardex and tipoacto.
        """
        kardex = request.query_params.get('kardex')
        tipoacto = request.query_params.get('tipoacto')

        if not kardex or not tipoacto:
            return Response(
                {"error": "kardex and tipoacto parameters are required."},
                status=400
            )
        
        try:
            detalle_actos = models.DetalleActosKardex.objects.get(
                kardex=kardex,
                idtipoacto=tipoacto
            )

        except models.DetalleActosKardex.DoesNotExist:
            return Response(
                {"error": "No DetalleActosKardex found for the given kardex and tipoacto."},
                status=404
            )
        

        serializer = serializers.DetalleActosKardexSerializer(detalle_actos)
        return Response(serializer.data)


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

    def update(self, request, *args, **kwargs):
        """ Update a Patrimonial record.
        This method will ensure that the itemmp field is not modified.
        """
        data = request.data
        instance = self.get_object()

        if data.get('idtipoacto') != instance.idtipoacto:
            vehicular = models.Detallevehicular.objects.filter(
                kardex=instance.kardex,
                idtipacto=instance.idtipoacto
            ).first()
            if vehicular:
                return Response(
                    {"error": "No se puede cambiar el idtipoacto de un Patrimonial que tiene un DetalleVehicular asociado."},
                    status=400
                )

        return super().update(request, *args, **kwargs)

    # remove patrimonial and also remove medio de pago
    def destroy(self, request, *args, **kwargs):
        """
        Delete a Patrimonial record and its related Detallemediopago and DetalleVehicular records.
        """
        instance = self.get_object()
        kardex = instance.kardex
        idtipoacto = instance.idtipoacto

        # Remove related Detallemediopago records
        models.Detallemediopago.objects.filter(itemmp=instance.itemmp).delete()

        # Remove related DetalleVehicular records
        models.Detallevehicular.objects.filter(
            kardex=kardex,
            idtipacto=idtipoacto
        ).delete()

        # Remove the Patrimonial record
        instance.delete()

        return Response(status=status.HTTP_204_NO_CONTENT)
        

    @transaction.atomic
    def create(self, request, *args, **kwargs):

        for attempt in range(5):
            try:
                sid = transaction.savepoint()
                # Generate ID
                itemmp = utils.generate_new_id(models.Patrimonial, 'itemmp', 6)

            except Exception as e:
                transaction.savepoint_rollback(sid)
                if attempt == 4:
                    return Response({"error": f"Error al crear Patrimonial: {str(e)}"}, status=400)
                continue

            data = request.data
            data['itemmp'] = itemmp
            serializer = self.get_serializer(data=data)
            serializer.is_valid(raise_exception=True)
            serializer.save()

            return Response(serializer.data, status=status.HTTP_201_CREATED)
        
        return Response({"error": "No se pudo generar un ID válido tras varios intentos"}, status=400)
        

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
        

class DetalleVehicularViewSet(ModelViewSet):
    """
    ViewSet for the DetalleVehicular model.
    """
    queryset = models.Detallevehicular.objects.all()
    serializer_class = serializers.DetallevehicularSerializer
    pagination_class = pagination.KardexPagination


    @action(detail=False, methods=['get'])
    def by_kardex(self, request):
        """
        Get DetalleVehicular records by Kardex.
        """
        kardex = request.query_params.get('kardex')
        idtipoacto = request.query_params.get('idtipoacto')
        if not kardex:
            return Response(
                {"error": "kardex parameter is required."},
                status=400
            )
        
        detalle_vehicular = models.Detallevehicular.objects.filter(kardex=kardex, idtipacto=idtipoacto)
        if not detalle_vehicular.exists():
            return Response([], status=200)

        serializer = serializers.DetallevehicularSerializer(detalle_vehicular, many=True)
        return Response(serializer.data)


    @action(detail=False, methods=['get'])
    def by_numplaca(self, request):
        """
        Get DetalleVehicular records by numplaca.
        """
        numplaca = request.query_params.get('numplaca')
        if not numplaca:
            return Response(
                {"error": "numplaca parameter is required."},
                status=400
            )
        
        detalle_vehicular = models.Detallevehicular.objects.filter(numplaca=numplaca).first()
        if not detalle_vehicular:
            return Response({"error": "No DetalleVehicular found for the given numplaca."}, status=404)

        serializer = serializers.DetallevehicularSerializer(detalle_vehicular)
        return Response(serializer.data)


class DetallebienesViewSet(ModelViewSet):
    """
    ViewSet for the Detallebienes model.
    """
    queryset = models.Detallebienes.objects.all()
    serializer_class = serializers.DetallebienesSerializer
    pagination_class = pagination.KardexPagination

    @action(detail=False, methods=['get'])
    def by_kardex(self, request):
        """
        Get Detallebienes records by Kardex.
        """
        kardex = request.query_params.get('kardex')
        if not kardex:
            return Response(
                {"error": "kardex parameter is required."},
                status=400
            )
        
        detalle_bienes = models.Detallebienes.objects.filter(kardex=kardex)
        if not detalle_bienes.exists():
            return Response([], status=200)

        serializer = serializers.DetallebienesSerializer(detalle_bienes, many=True)
        return Response(serializer.data)


class PrediosViewSet(ModelViewSet):
    """
    ViewSet for the Predios model.
    """
    queryset = models.Predios.objects.all()
    serializer_class = serializers.PrediosSerializer
    pagination_class = pagination.KardexPagination

    @action(detail=False, methods=['get'])
    def by_kardex(self, request):
        """
        Get Predios records by Kardex.
        """
        kardex = request.query_params.get('kardex')
        if not kardex:
            return Response(
                {"error": "kardex parameter is required."},
                status=400
            )
        
        predios = models.Predios.objects.filter(kardex=kardex)
        if not predios.exists():
            return Response([], status=200)

        serializer = serializers.PrediosSerializer(predios, many=True)
        return Response(serializer.data)


class DetallemediopagoViewSet(ModelViewSet):
    """
    ViewSet for the Detallemediopago model.
    """
    queryset = models.Detallemediopago.objects.all()
    serializer_class = serializers.DetallemediopagoSerializer
    pagination_class = pagination.KardexPagination

    @action(detail=False, methods=['get'])
    def by_kardex(self, request):
        """
        Get Detallemediopago records by Kardex.
        """
        kardex = request.query_params.get('kardex')
        if not kardex:
            return Response(
                {"error": "kardex parameter is required."},
                status=400
            )
        
        detalle_mediopago = models.Detallemediopago.objects.filter(kardex=kardex)
        if not detalle_mediopago.exists():
            return Response([], status=200)

        serializer = serializers.DetallemediopagoSerializer(detalle_mediopago, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def by_patrimonial(self, request):
        """
        Get Detallemediopago records by Patrimonial itemmp.
        """
        itemmp = request.query_params.get('itemmp')
        if not itemmp:
            return Response(
                {"error": "itemmp parameter is required."},
                status=400
            )
        
        detalle_mediopago = models.Detallemediopago.objects.filter(itemmp=itemmp)
        if not detalle_mediopago.exists():
            return Response([], status=200)

        serializer = serializers.DetallemediopagoSerializer(detalle_mediopago, many=True)
        return Response(serializer.data)


class TemplateViewSet(ModelViewSet):
    """
    ViewSet for the TplTemplate model.
    """
    queryset = models.TplTemplate.objects.all()
    serializer_class = serializers.TemplateSerializer
    pagination_class = pagination.KardexPagination

    @action(detail=False, methods=['get'])
    def by_actos(self, request):
        """
        Get TplTemplate records by acto.
        """
        codactos = request.query_params.get('codactos')
        if not codactos:
            return Response(
                {"error": "acto parameter is required."},
                status=400
            )
        codactos_array = [codactos[i:i+3] for i in range(0, len(codactos), 3)]
        templates = models.TplTemplate.objects.filter(codeacts__in=codactos_array)
        if not templates.exists():
            return Response([], status=200)

        serializer = serializers.TemplateSerializer(templates, many=True)
        return Response(serializer.data)


class LegalizacionViewSet(ModelViewSet):
    """
    ViewSet for the Legalizacion model.
    """
    queryset = models.Legalizacion.objects.all().order_by('-idlegalizacion')
    serializer_class = serializers.LegalizacionSerializer
    pagination_class = pagination.KardexPagination

    def list(self, request, *args, **kwargs):
        dateFrom = request.query_params.get('dateFrom', '')
        dateTo = request.query_params.get('dateTo', '')

        print('dateFrom', dateFrom)
        print('dateTo', dateTo)

        if dateFrom and dateTo:
            self.queryset = self.queryset.filter(fechaingreso__range=(dateFrom, dateTo))
        elif dateFrom:
            self.queryset = self.queryset.filter(fechaingreso__gte=dateFrom)
        elif dateTo:
            self.queryset = self.queryset.filter(fechaingreso__lte=dateTo)

        return super().list(request, *args, **kwargs)

class PermiViajeViewSet(ModelViewSet):
    """
    ViewSet for the PermiViaje model.
    """
    queryset = models.PermiViaje.objects.all()
    serializer_class = serializers.PermiViajeSerializer
    pagination_class = pagination.KardexPagination

    # def list(self, request, *args, **kwargs):