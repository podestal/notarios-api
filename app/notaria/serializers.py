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

        idcontratante = contratantes_map.get(obj.kardex)
        cliente = clientes_map.get(idcontratante)

        if cliente:
            return (
                f"{cliente['nombre']}"
            )

        return ''


class ContratantesSerializer(serializers.ModelSerializer):
    """
    Serializer for the Contratantes model.
    """
    class Meta:
        model = models.Contratantes
        fields = '__all__'


class Cliente2Serializer(serializers.ModelSerializer):
    """
    Serializer for the Cliente2 model.
    """
    class Meta:
        model = models.Cliente2
        fields = '__all__'


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
