from rest_framework import serializers
from . import models

'''
Serializers for the Notaria app.
These serializers are used to convert complex data types,
such as querysets and model instances, into native Python datatypes
that can then be easily rendered into JSON, XML or other content types.
'''


class UsuariosSerializer(serializers.ModelSerializer):
    """
    Serializer for the Usuarios model.
    """
    class Meta:
        model = models.Usuarios
        fields = '__all__'


class PermisosUsuariosSerializer(serializers.ModelSerializer):
    """
    Serializer for the PermisosUsuarios model.
    """
    class Meta:
        model = models.PermisosUsuarios
        fields = '__all__'


class TipoKarSerializer(serializers.ModelSerializer):
    """
    Serializer for the TipoKar model.
    """
    class Meta:
        model = models.Tipokar
        fields = '__all__'


class CreateKardexSerializer(serializers.ModelSerializer):
    """
    Serializer for creating a Kardex instance.
    This serializer is used to validate and create a new Kardex record.
    """

    class Meta:
        model = models.Kardex
        fields = [
            'idkardex',
            'kardex',
            'idtipkar',
            'fechaingreso',
            'idtipkar',
            'referencia',
            'codactos',
            'contrato',
            'idusuario',
            'responsable',
            'retenido',
            'desistido',
            'autorizado',
            'idrecogio',
            'pagado',
            'visita',
            'idnotario',
        ]


class KardexSerializer(serializers.ModelSerializer):
    """
    Serializer for the Kardex model.
    """
    # class Meta:
    #     model = models.Kardex
    #     fields = '__all__'

    usuario = serializers.SerializerMethodField()
    # contratantes = serializers.SerializerMethodField()
    cliente = serializers.SerializerMethodField()

    class Meta:
        model = models.Kardex
        fields = [
            'idkardex',
            'kardex',
            'fechaingreso',
            'contrato',
            'fechaescritura',
            'numescritura',
            'numminuta',
            'folioini',
            'foliofin',
            'numinstrmento',
            'txa_minuta',
            'idusuario',
            'usuario',
            'idtipkar',
            # 'contratantes',
            'cliente',
            'retenido',
            'desistido',
            'autorizado',
            'idrecogio',
            'pagado',
            'visita',
        ]

    def get_usuario(self, obj):
        usuarios_map = self.context.get('usuarios_map', {})
        usuario = usuarios_map.get(obj.idusuario)
        if usuario:
            return (
                f"{usuario.prinom} {usuario.segnom} "
                f"{usuario.apepat} {usuario.apemat}"
            )
        return ''

    # def get_contratantes(self, obj):
    #     contratantes_map = self.context.get('contratantes_map', {})
    #     contratante = contratantes_map.get(obj.kardex)
    #     if contratante:
    #         return (
    #             f"{contratante}"
    #         )
    #     return ''

    def get_cliente(self, obj):
        contratantes_map = self.context.get('contratantes_map', {})
        clientes_map = self.context.get('clientes_map', {})

        idscontratante = contratantes_map.get(obj.kardex)

        if not idscontratante:
            return ''

        clientes = []
        for idcontratante in idscontratante:
            cliente = clientes_map.get(idcontratante)
            if cliente:
                clientes.append(cliente)

        if cliente:
            return (
                # f"{cliente['nombre']}"
                ', '.join(f"{c['nombre']}" for c in clientes)
            )

        return ''


class ContratantesSerializer(serializers.ModelSerializer):
    """
    Serializer for the Contratantes model.
    """
    class Meta:
        model = models.Contratantes
        fields = '__all__'


    # idcontratante = models.CharField(primary_key=True, max_length=10)
    # idtipkar = models.IntegerField()
    # kardex = models.CharField(max_length=30, blank=True, null=True)
    # condicion = models.CharField(max_length=100)
    # firma = models.CharField(max_length=3)
    # fechafirma = models.CharField(max_length=10)
    # resfirma = models.IntegerField()
    # tiporepresentacion = models.CharField(max_length=2)
    # idcontratanterp = models.CharField(max_length=3000)
    # idsedereg = models.CharField(max_length=3, blank=True, null=True)
    # numpartida = models.CharField(max_length=50, blank=True, null=True)
    # facultades = models.CharField(max_length=500)
    # indice = models.CharField(max_length=3)
    # visita = models.CharField(max_length=3)
    # inscrito = models.CharField(max_length=1, blank=True, null=True)
    # plantilla = models.CharField(max_length=3, blank=True, null=True)

class ContratantesKardexSerializer(serializers.ModelSerializer):
    """
    Serializer for the ContratantesKardex model.
    This serializer is used to validate and serialize the
    ContratantesKardex data.
    """

    cliente = serializers.SerializerMethodField()
    condicion = serializers.SerializerMethodField()

    class Meta:
        model = models.Contratantes
        fields = [
            'idcontratante',
            'idtipkar',
            'kardex',
            'condicion',
            'firma',
            'fechafirma',
            'cliente',
        ]

    def get_cliente(self, obj):
        clientes_map = self.context.get('clientes_map', {})
        cliente = clientes_map.get(obj.idcontratante)
        if cliente:
            return (
                f"{cliente['nombre']}"
            )
        return ''
    
    def get_condicion(self, obj):
        condicion_map = self.context.get('condicion_map', {})
        condicion = condicion_map.get(obj.condicion.split('.')[0])
        if condicion:
            return (
                f"{condicion['condicion']}"
            )
        return ''
    

class ClienteSerializer(serializers.ModelSerializer):
    """
    Serializer for the Cliente model.
    This serializer is used to validate and serialize the Cliente data.
    """

    class Meta:
        model = models.Cliente
        fields = '__all__'


class Cliente2Serializer(serializers.ModelSerializer):
    """
    Serializer for the Cliente2 model.
    """
    class Meta:
        model = models.Cliente2
        fields = '__all__'


class CreateClienteSerializer(serializers.ModelSerializer):
    """
    Serializer for creating a Cliente instance.
    This serializer is used to validate and create a new Cliente record.
    """

    idcliente = serializers.CharField(read_only=True)

    class Meta:
        model = models.Cliente
        fields = [
            'idcliente',
            'tipper',
            'apepat',
            'apemat',
            'prinom',
            'segnom',
            'nombre',
            'direccion',
            'idtipdoc',
            'numdoc',
            'email',
            'telfijo',
            'telcel',
            'telofi',
            'sexo',
            'idestcivil',
            'natper',
            'conyuge',
            'nacionalidad',
            'idprofesion',
            'detaprofesion',
            'idcargoprofe',
            'profocupa',
            'dirfer',
            'idubigeo',
            'cumpclie'
        ]

    def create(self, validated_data):
        # Generate new idcliente
        last_cliente = models.Cliente.objects.order_by('-idcliente').first()
        if last_cliente and last_cliente.idcliente.isdigit():
            new_id = str(int(last_cliente.idcliente) + 1).zfill(10)
        else:
            new_id = '0000000001'
        return models.Cliente.objects.create(
            idcliente=new_id,
            **validated_data
        )


class CreateCliente2Serializer(serializers.ModelSerializer):
    """
    Serializer for creating a Cliente2 instance.
    This serializer is used to validate and create a new Cliente2 record.
    """

    class Meta:
        model = models.Cliente2
        fields = [
            'idcliente',
            'nombre',
            'apepat',
            'apemat',
            'numdoc',
            # 'ruc',
            'direccion',
            # 'telefono',
            'email',
            'nacionalidad',
            'idprofesion',
            'idcargoprofe',
        ]


class TiposDeActosSerializer(serializers.ModelSerializer):
    """
    Serializer for the TiposDeActos model.
    """
    class Meta:
        model = models.Tiposdeacto
        fields = [
            'idtipoacto',
            'actosunat',
            'actouif',
            'idtipkar',
            'desacto',
            'umbral',
            'impuestos'
        ]


class ActoCondicionSerializer(serializers.ModelSerializer):
    """
    Serializer for the ActoCondicion model.
    """
    class Meta:
        model = models.Actocondicion
        fields = '__all__'


class DetalleActosKardexSerializer(serializers.ModelSerializer):
    """
    Serializer for the DetalleActosKardex model.
    """
    class Meta:
        model = models.DetalleActosKardex
        fields = '__all__'


class TbAbogadoSerializer(serializers.ModelSerializer):
    """
    Serializer for the TbAbogado model.
    """
    class Meta:
        model = models.TbAbogado
        fields = '__all__'


class NacionalidadesSerializer(serializers.ModelSerializer):
    """
    Serializer for the Nacionalidades model.
    """
    class Meta:
        model = models.Nacionalidades
        fields = '__all__'


class ProfesionesSerializer(serializers.ModelSerializer):
    """
    Serializer for the Profesion model.
    """
    class Meta:
        model = models.Profesiones
        fields = '__all__'


class CargoprofeSerializer(serializers.ModelSerializer):
    """
    Serializer for the Cargoprofe model.
    """
    class Meta:
        model = models.Cargoprofe
        fields = '__all__'


class UbigeoSerializer(serializers.ModelSerializer):
    """
    Serializer for the Ubigeo model.
    This serializer is used to validate and serialize the Ubigeo data.
    """

    class Meta:
        model = models.Ubigeo
        fields = '__all__'
