from django.db import models
'''
Models for the Notaria app.
These models define the database tables for the Notaria app.
They are used to define the fields and relationships between the tables.
They are also used to define the database constraints and indexes.
'''


class Usuarios(models.Model):
    """
    Model representing a user in the system.
    """
    idusuario = models.AutoField(primary_key=True)
    loginusuario = models.CharField(max_length=50)
    password = models.CharField(max_length=50)
    apepat = models.CharField(max_length=100)
    apemat = models.CharField(max_length=100)
    prinom = models.CharField(max_length=100)
    segnom = models.CharField(max_length=100)
    fecnac = models.CharField(max_length=10)
    estado = models.IntegerField()
    domicilio = models.CharField(max_length=100)
    idubigeo = models.IntegerField()
    telefono = models.CharField(max_length=30)
    idcargo = models.IntegerField()
    dni = models.CharField(max_length=8, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'usuarios'


class PermisosUsuarios(models.Model):
    """
    Model representing the permissions of a user in the system.
    """
    idusuario = models.CharField(primary_key=True, max_length=9)
    kardex = models.CharField(max_length=30, blank=True, null=True)
    newkar = models.CharField(max_length=1, blank=True, null=True)
    editkar = models.CharField(max_length=1, blank=True, null=True)
    protesto = models.CharField(max_length=1, blank=True, null=True)
    newprot = models.CharField(max_length=1, blank=True, null=True)
    editprot = models.CharField(max_length=1, blank=True, null=True)
    pviaje = models.CharField(max_length=1, blank=True, null=True)
    newvia = models.CharField(max_length=1, blank=True, null=True)
    editvia = models.CharField(max_length=1, blank=True, null=True)
    poder = models.CharField(max_length=1, blank=True, null=True)
    newpod = models.CharField(max_length=1, blank=True, null=True)
    editpod = models.CharField(max_length=1, blank=True, null=True)
    cartas = models.CharField(max_length=1, blank=True, null=True)
    newcar = models.CharField(max_length=1, blank=True, null=True)
    editcar = models.CharField(max_length=1, blank=True, null=True)
    libros = models.CharField(max_length=1, blank=True, null=True)
    newlib = models.CharField(max_length=1, blank=True, null=True)
    editlib = models.CharField(max_length=1, blank=True, null=True)
    capaz = models.CharField(max_length=1, blank=True, null=True)
    newcap = models.CharField(max_length=1, blank=True, null=True)
    editcap = models.CharField(max_length=1, blank=True, null=True)
    incapaz = models.CharField(max_length=1, blank=True, null=True)
    newinca = models.CharField(max_length=1, blank=True, null=True)
    editinca = models.CharField(max_length=1, blank=True, null=True)
    domiciliario = models.CharField(max_length=1, blank=True, null=True)
    newdom = models.CharField(max_length=1, blank=True, null=True)
    editdom = models.CharField(max_length=1, blank=True, null=True)
    caracteristicas = models.CharField(max_length=1, blank=True, null=True)
    newcarac = models.CharField(max_length=1, blank=True, null=True)
    editcarac = models.CharField(max_length=1, blank=True, null=True)
    indicronoep = models.CharField(max_length=1, blank=True, null=True)
    indicrononc = models.CharField(max_length=1, blank=True, null=True)
    indicronotv = models.CharField(max_length=1, blank=True, null=True)
    indicronogm = models.CharField(max_length=1, blank=True, null=True)
    indicronotest = models.CharField(max_length=1, blank=True, null=True)
    indicronoprot = models.CharField(max_length=1, blank=True, null=True)
    infocamacome = models.CharField(max_length=1, blank=True, null=True)
    indicronocar = models.CharField(max_length=1, blank=True, null=True)
    indicronolib = models.CharField(max_length=1, blank=True, null=True)
    indicronovia = models.CharField(max_length=1, blank=True, null=True)
    indicronopod = models.CharField(max_length=1, blank=True, null=True)
    indicronocapaz = models.CharField(max_length=1, blank=True, null=True)
    indicronoincapaz = models.CharField(max_length=1, blank=True, null=True)
    alfaep = models.CharField(max_length=1, blank=True, null=True)
    alfagm = models.CharField(max_length=1, blank=True, null=True)
    alfanc = models.CharField(max_length=1, blank=True, null=True)
    alfatv = models.CharField(max_length=1, blank=True, null=True)
    alfatesta = models.CharField(max_length=1, blank=True, null=True)
    pdtep = models.CharField(max_length=1, blank=True, null=True)
    pdtgm = models.CharField(max_length=1, blank=True, null=True)
    pdtveh = models.CharField(max_length=1, blank=True, null=True)
    pdtlib = models.CharField(max_length=1, blank=True, null=True)
    ro = models.CharField(max_length=1, blank=True, null=True)
    reportuif = models.CharField(max_length=1, blank=True, null=True)
    reportpendfirma = models.CharField(max_length=1, blank=True, null=True)
    emicompro = models.CharField(max_length=1, blank=True, null=True)
    anucompro = models.CharField(max_length=1, blank=True, null=True)
    cancelcompro = models.CharField(max_length=1, blank=True, null=True)
    reportcomproemi = models.CharField(max_length=1, blank=True, null=True)
    pendpago = models.CharField(max_length=1, blank=True, null=True)
    cancelados = models.CharField(max_length=1, blank=True, null=True)
    manteusu = models.CharField(max_length=1, blank=True, null=True)
    permiusu = models.CharField(max_length=1, blank=True, null=True)
    tipoacto = models.CharField(max_length=1, blank=True, null=True)
    mantecondi = models.CharField(max_length=1, blank=True, null=True)
    manteclie = models.CharField(max_length=1, blank=True, null=True)
    manteimpe = models.CharField(max_length=1, blank=True, null=True)
    sellocartas = models.CharField(max_length=1, blank=True, null=True)
    helpprot = models.CharField(max_length=1, blank=True, null=True)
    contpod = models.CharField(max_length=1, blank=True, null=True)
    manteservi = models.CharField(max_length=1, blank=True, null=True)
    asignaregis = models.CharField(max_length=1, blank=True, null=True)
    tipo_cambio = models.CharField(max_length=1, blank=True, null=True)
    seriescaja = models.CharField(max_length=1, blank=True, null=True)
    datonot = models.CharField(max_length=1, blank=True, null=True)
    editdatonot = models.CharField(max_length=1, blank=True, null=True)
    regserver = models.CharField(max_length=1, blank=True, null=True)
    editserver = models.CharField(max_length=1, blank=True, null=True)
    mant_abogado = models.CharField(max_length=1, blank=True, null=True)
    backup = models.CharField(max_length=1, blank=True, null=True)
    egreso = models.CharField(max_length=1, blank=True, null=True)
    sisgen = models.CharField(max_length=1, blank=True, null=True)
    userresponsable = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'permisos_usuarios'


class Kardex(models.Model):
    """
    Model representing the Kardex table.
    This table stores information about the documents and their
    status in the system.
    """
    idkardex = models.AutoField(primary_key=True)
    kardex = models.CharField(max_length=30, blank=True, null=True)
    idtipkar = models.IntegerField()
    kardexconexo = models.CharField(max_length=8)
    fechaingreso = models.CharField(max_length=10)
    horaingreso = models.CharField(max_length=10)
    referencia = models.CharField(max_length=3000)
    codactos = models.CharField(max_length=50)
    contrato = models.CharField(max_length=3000)
    idusuario = models.IntegerField()
    responsable = models.IntegerField()
    observacion = models.CharField(max_length=8000)
    documentos = models.CharField(max_length=8000)
    fechacalificado = models.CharField(max_length=10)
    fechainstrumento = models.CharField(max_length=10)
    fechaconclusion = models.CharField(max_length=10)
    numinstrmento = models.CharField(max_length=30, blank=True, null=True)
    folioini = models.CharField(max_length=30, blank=True, null=True)
    folioinivta = models.CharField(max_length=30, blank=True, null=True)
    foliofin = models.CharField(max_length=30, blank=True, null=True)
    foliofinvta = models.CharField(max_length=30, blank=True, null=True)
    papelini = models.CharField(max_length=30, blank=True, null=True)
    papelinivta = models.CharField(max_length=30, blank=True, null=True)
    papelfin = models.CharField(max_length=30, blank=True, null=True)
    papelfinvta = models.CharField(max_length=30, blank=True, null=True)
    comunica1 = models.CharField(max_length=3000)
    contacto = models.CharField(max_length=3000)
    telecontacto = models.CharField(max_length=50)
    mailcontacto = models.CharField(max_length=200)
    retenido = models.IntegerField()
    desistido = models.IntegerField()
    autorizado = models.IntegerField()
    idrecogio = models.IntegerField()
    pagado = models.IntegerField()
    visita = models.IntegerField()
    dregistral = models.CharField(max_length=30)
    dnotarial = models.CharField(max_length=30)
    idnotario = models.IntegerField()
    numminuta = models.CharField(max_length=100)
    numescritura = models.CharField(max_length=100)
    fechaescritura = models.CharField(max_length=10)
    insertos = models.CharField(max_length=6000, blank=True, null=True)
    direc_contacto = models.CharField(max_length=3000, blank=True, null=True)
    txa_minuta = models.CharField(max_length=30, blank=True, null=True)
    idabogado = models.CharField(max_length=10, blank=True, null=True)
    responsable_new = models.CharField(max_length=3000, blank=True, null=True)
    fechaminuta = models.CharField(max_length=15, blank=True, null=True)
    ob_nota = models.CharField(max_length=6000, blank=True, null=True)
    ins_espec = models.CharField(max_length=6000, blank=True, null=True)
    recepcion = models.CharField(max_length=30, blank=True, null=True)
    funcionario_new = models.CharField(max_length=3000, blank=True, null=True)
    nc = models.CharField(max_length=30, blank=True, null=True)
    fecha_modificacion = models.CharField(max_length=10, blank=True, null=True)
    idpresentante = models.IntegerField(db_column='idPresentante', blank=True,
                                        null=True)
    papeltrasladoini = models.CharField(db_column='papelTrasladoIni',
                                        max_length=30, blank=True, null=True)
    papeltrasladofin = models.CharField(db_column='papelTrasladoFin',
                                        max_length=30, blank=True, null=True)
    fktemplate = models.IntegerField(db_column='fkTemplate', blank=True,
                                     null=True)
    estado_sisgen = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'kardex'


class Tipokar(models.Model):
    """
    Model representing the type of Kardex.
    This table stores the different types of Kardex available in the system.
    """

    idtipkar = models.IntegerField(primary_key=True)
    nomtipkar = models.CharField(max_length=50)
    tipkar = models.CharField(max_length=1)

    class Meta:
        managed = False
        db_table = 'tipokar'


class Contratantes(models.Model):
    """
    Model representing the contractors in the system.
    This table stores information about the contractors and their details.
    """

    idcontratante = models.CharField(primary_key=True, max_length=10)
    idtipkar = models.IntegerField()
    kardex = models.CharField(max_length=30, blank=True, null=True)
    condicion = models.CharField(max_length=100)
    firma = models.CharField(max_length=3)
    fechafirma = models.CharField(max_length=10)
    resfirma = models.IntegerField()
    tiporepresentacion = models.CharField(max_length=2)
    idcontratanterp = models.CharField(max_length=3000)
    idsedereg = models.CharField(max_length=3, blank=True, null=True)
    numpartida = models.CharField(max_length=50, blank=True, null=True)
    facultades = models.CharField(max_length=500)
    indice = models.CharField(max_length=3)
    visita = models.CharField(max_length=3)
    inscrito = models.CharField(max_length=1, blank=True, null=True)
    plantilla = models.CharField(max_length=3, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'contratantes'


class Cliente2(models.Model):
    """
    Model representing the client in the system.
    This table stores information about the clients and their details.
    """

    idcontratante = models.CharField(primary_key=True, max_length=10)
    idcliente = models.CharField(max_length=10)
    tipper = models.CharField(max_length=1)
    apepat = models.CharField(max_length=100)
    apemat = models.CharField(max_length=100)
    prinom = models.CharField(max_length=100)
    segnom = models.CharField(max_length=100)
    nombre = models.CharField(max_length=1000)
    direccion = models.CharField(max_length=3000)
    idtipdoc = models.IntegerField()
    numdoc = models.CharField(max_length=50)
    email = models.CharField(max_length=300)
    telfijo = models.CharField(max_length=20)
    telcel = models.CharField(max_length=20)
    telofi = models.CharField(max_length=20)
    sexo = models.CharField(max_length=1)
    idestcivil = models.IntegerField()
    natper = models.CharField(max_length=50)
    conyuge = models.CharField(max_length=10)
    nacionalidad = models.CharField(max_length=100)
    idprofesion = models.IntegerField()
    detaprofesion = models.CharField(max_length=1000, blank=True, null=True)
    idcargoprofe = models.IntegerField()
    profocupa = models.CharField(max_length=1000)
    dirfer = models.CharField(max_length=300)
    idubigeo = models.CharField(max_length=6)
    cumpclie = models.CharField(max_length=15)
    fechaing = models.CharField(max_length=10)
    razonsocial = models.CharField(max_length=3000)
    domfiscal = models.CharField(max_length=3000)
    telempresa = models.CharField(max_length=12)
    mailempresa = models.CharField(max_length=200)
    contacempresa = models.CharField(max_length=3000)
    fechaconstitu = models.CharField(max_length=12)
    idsedereg = models.IntegerField()
    numregistro = models.CharField(max_length=50)
    numpartida = models.CharField(max_length=50)
    actmunicipal = models.CharField(max_length=3000)
    tipocli = models.CharField(max_length=1)
    impeingre = models.CharField(max_length=10)
    impnumof = models.CharField(max_length=50)
    impeorigen = models.CharField(max_length=3000)
    impentidad = models.CharField(max_length=3000)
    impremite = models.CharField(max_length=3000)
    impmotivo = models.CharField(max_length=3000)
    residente = models.CharField(max_length=2)
    docpaisemi = models.CharField(max_length=100)
    partidaconyuge = models.CharField(max_length=15, blank=True, null=True)
    separaciondebienes = models.CharField(max_length=1, blank=True, null=True)
    idsedeconyuge = models.CharField(max_length=11, blank=True, null=True)
    profesion_plantilla = models.CharField(
        max_length=200, blank=True, null=True
    )
    ubigeo_plantilla = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'cliente2'
