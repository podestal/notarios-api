from rest_framework import serializers
from . import models
from django.db import IntegrityError
from .constants import MONEDAS

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
            'numescritura',
            'fktemplate',
            'papelini',
            'papelfin',
            'folioini',
            'foliofin',
            'fechaescritura',
            'responsable',
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
            'codactos',
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
            'fktemplate',
            'papelini',
            'papelfin',
            'responsable',
            'referencia',
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
        # print('clientes',clientes)
        if cliente:

            return (
                # f"{cliente['nombre']}"
                # ', '.join(f"{c['nombre'] if c['nombre'] else c['razonsocial']}" for c in clientes)
                ', '.join(
                    f"{c['razonsocial'] if c['razonsocial'] else c['nombre']}"
                    for c in clientes
                )
            )

        return ''


class ContratantesSerializer(serializers.ModelSerializer):
    """
    Serializer for the Contratantes model.
    """
    class Meta:
        model = models.Contratantes
        fields = '__all__'

            # "idcontratante": "0000147215",
            # "idtipkar": 1,
            # "kardex": "KAR2315-2025",
            # "condicion": "044.57535/",
            # "firma": "1",
            # "fechafirma": "",
            # "resfirma": 0,
            # "tiporepresentacion": "0",
            # "idcontratanterp": "",
            # "idsedereg": "",
            # "numpartida": "",
            # "facultades": "",
            # "indice": "1",
            # "visita": "0",
            # "inscrito": "0",
            # "plantilla": null

class CreateContratantesSerializer(serializers.ModelSerializer):
    """
    Serializer for creating a Contratantes instance.
    This serializer is used to validate and create a new Contratantes record.
    """

    idcontratante = serializers.CharField(read_only=True)

    class Meta:
        model = models.Contratantes
        fields = [
            'idcontratante',
            'idtipkar',
            'kardex',
            'condicion',
            'firma',
            'fechafirma',
            'resfirma',
            'tiporepresentacion',
            'indice',
            'visita',
            'inscrito',
            'idcontratanterp',
        ]


class ContratantesKardexSerializer(serializers.ModelSerializer):
    """
    Serializer for the ContratantesKardex model.
    This serializer is used to validate and serialize the
    ContratantesKardex data.
    """

    cliente = serializers.SerializerMethodField()
    condicion_str = serializers.SerializerMethodField()
    cliente_id = serializers.SerializerMethodField()

    class Meta:
        model = models.Contratantes
        fields = [
            'idcontratante',
            'idtipkar',
            'kardex',
            'condicion',
            'condicion_str',
            'firma',
            'fechafirma',
            'cliente',
            'cliente_id',
            'idcontratanterp'
        ]

    def get_cliente(self, obj):
        clientes_map = self.context.get('clientes_map', {})
        cliente = clientes_map.get(obj.idcontratante)
        if cliente:
            if cliente.get('razonsocial'):
                return (
                    f"{cliente['razonsocial']}"
                )
            elif cliente.get('nombre'):
                return (
                    f"{cliente['nombre']}"
                )
        return ''
    
    def get_cliente_id(self, obj):
        clientes_map = self.context.get('clientes_map', {})
        cliente = clientes_map.get(obj.idcontratante)
        if cliente:
            return (
                f"{cliente['idcliente']}"
            )
        return ''
    
    def get_condicion_str(self, obj):
        condicion_map = self.context.get('condicion_map', {})
        condicion = condicion_map.get(obj.condicion.split('.')[0])
        if condicion:
            return (
                f"{condicion['condicion']}"
            )
        return ''
    

class ContratantesxactoSerializer(serializers.ModelSerializer):
    """
    Serializer for the Contratantesxacto model.
    This serializer is used to validate and serialize the Contratantesxacto data.
    """

    class Meta:
        model = models.Contratantesxacto
        fields = '__all__'


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

class CreateCliente2Serializer(serializers.ModelSerializer):
    """
    Serializer for creating a Cliente2 instance.
    This serializer is used to validate and create a new Cliente2 record.
    """

    idcliente = serializers.CharField(read_only=True)

    class Meta:
        model = models.Cliente2
        fields = [
            'idcliente',
            'idcontratante',
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
            'cumpclie',
            'razonsocial',
            'fechaing',
            'residente',
            'tipocli',
            'profesion_plantilla',
            'ubigeo_plantilla',
            'fechaconstitu',
            'idsedereg',
            'razonsocial',
            'domfiscal',
            'idsedereg',
            'numpartida',
            'telempresa',
            'actmunicipal',
            'contacempresa',
            'fechaconstitu',
        ]

    # def create(self, validated_data):
    #     attempts = 0
    #     max_attempts = 5

    #     while attempts < max_attempts:
    #         last_cliente = models.Cliente2.objects.order_by('-idcliente').first()
    #         if last_cliente and last_cliente.idcliente.isdigit():
    #             new_id = str(int(last_cliente.idcliente) + 1).zfill(10)
    #         else:
    #             new_id = '0000000001'

    #         try:
    #             return models.Cliente2.objects.create(
    #                 idcliente=new_id,
    #                 **validated_data
    #             )
    #         except IntegrityError:
    #             attempts += 1

    #     raise serializers.ValidationError("Could not generate a unique client ID after several attempts.")
        


class CreateClienteSerializer(serializers.ModelSerializer):
    """
    Serializer for creating a Cliente instance.
    This serializer is used to validate and create a new Cliente record.
    """

    idcliente = serializers.CharField(read_only=True)
                #   razonsocial: razonSocial,
                #     domfiscal: domFiscal,
                #     idsedereg: selectedSedeRegistral ? parseInt(selectedSedeRegistral.id) : 0,
                #     numpartida: numeroPartida,
                #     telempresa: teleEmpresa,
                #     actmunicipal: ciiu,
                #     contacempresa: contacEmpresa,
                #     fechaconstitu: fechaConstitucion,
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
            'cumpclie',
            'razonsocial',
            'domfiscal',
            'idsedereg',
            'numpartida',
            'telempresa',
            'actmunicipal',
            'contacempresa',
            'fechaconstitu',
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


class SedesregistralesSerializer(serializers.ModelSerializer):
    """
    Serializer for the Sedesregistrales model.
    This serializer is used to validate and serialize the Sedesregistrales data.
    """
    class Meta:
        model = models.Sedesregistrales
        fields = ['idsedereg', 'dessede', 'num_zona', 'zona_depar']


class RepresentantesSerializer(serializers.ModelSerializer):
    """
    Serializer for creating a Sedesregistrales instance.
    This serializer is used to validate and create a new Sedesregistrales record.
    """

    class Meta:
        model = models.Representantes
        fields = '__all__'


class PatrimonialSerializer(serializers.ModelSerializer):
    """
    Serializer for the Patrimonial model.
    This serializer is used to validate and serialize the Patrimonial data.
    """

    moneda = serializers.SerializerMethodField()
    medios_pago_sum = serializers.SerializerMethodField()

    class Meta:
        model = models.Patrimonial
        fields = ['itemmp', 'kardex', 'idtipoacto', 'nminuta', 'idmon',
                  'tipocambio', 'importetrans', 'exhibiomp', 'presgistral',
                  'nregistral', 'idsedereg', 'fpago', 'idoppago', 'ofondos',
                  'item', 'des_idoppago', 'moneda', 'medios_pago_sum']
        
    def get_moneda(self, obj):
        """
        Returns the currency associated with the Patrimonial instance.
        """
        moneda_des = MONEDAS[obj.idmon]['desmon']
        return moneda_des
    
    def get_medios_pago_sum(self, obj):
        """
        Returns the sum of medios de pago for the Patrimonial instance.
        """
        medios_pago = models.Detallemediopago.objects.filter(itemmp=obj.itemmp)
        return sum(medio.importemp for medio in medios_pago)

    
class DetallevehicularSerializer(serializers.ModelSerializer):
    """
    Serializer for the Detallevehicular model.
    """
    class Meta:
        model = models.Detallevehicular
        fields = '__all__'


class DetallebienesSerializer(serializers.ModelSerializer):
    """
    Serializer for the Detallebienes model.
    """
    class Meta:
        model = models.Detallebienes
        fields = '__all__'


class DetallemediopagoSerializer(serializers.ModelSerializer):
    """
    Serializer for the Detallemediopago model.
    This serializer is used to validate and serialize the Detallemediopago data.
    """

    class Meta:
        model = models.Detallemediopago
        fields = '__all__'


class PrediosSerializer(serializers.ModelSerializer):
    """
    Serializer for the Predios model.
    """
    class Meta:
        model = models.Predios
        fields = '__all__'


class TemplateSerializer(serializers.ModelSerializer):
    """
    Serializer for the TplTemplate model.
    This serializer is used to validate and serialize the TplTemplate data.
    """

    class Meta:
        model = models.TplTemplate
        fields = '__all__'


class LegalizacionSerializer(serializers.ModelSerializer):
    """
    Serializer for the Legalizacion model.
    """
    class Meta:
        model = models.Legalizacion
        fields = '__all__'


class PermiViajeSerializer(serializers.ModelSerializer):
    """
    Serializer for the PermiViaje model.
    """
    class Meta:
        model = models.PermiViaje
        fields = '__all__'