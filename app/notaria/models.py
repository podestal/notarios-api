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
    referencia = models.CharField(max_length=3000, blank=True, null=True)
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
    numescritura = models.CharField(max_length=100, blank=True, null=True)
    fechaescritura = models.CharField(max_length=10, blank=True, null=True)
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
    fechafirma = models.CharField(max_length=10, blank=True, null=True)
    resfirma = models.IntegerField()
    tiporepresentacion = models.CharField(max_length=2)
    idcontratanterp = models.CharField(max_length=3000, blank=True, null=True)
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


class Contratantesxacto(models.Model):
    id = models.AutoField(primary_key=True)
    idtipkar = models.IntegerField()
    kardex = models.CharField(max_length=30, blank=True, null=True)
    idtipoacto = models.CharField(max_length=6)
    idcontratante = models.CharField(max_length=10)
    item = models.IntegerField()
    idcondicion = models.CharField(max_length=3)
    parte = models.CharField(max_length=3)
    porcentaje = models.CharField(max_length=50)
    uif = models.CharField(max_length=5)
    formulario = models.CharField(max_length=2)
    monto = models.CharField(max_length=100)
    opago = models.CharField(max_length=2)
    ofondo = models.CharField(max_length=300)
    montop = models.CharField(max_length=2)

    class Meta:
        managed = False
        db_table = 'contratantesxacto'


class Cliente(models.Model):
    idcliente = models.CharField(primary_key=True, max_length=10)
    tipper = models.CharField(max_length=1, blank=True, null=True)
    apepat = models.CharField(max_length=100, blank=True, null=True)
    apemat = models.CharField(max_length=100, blank=True, null=True)
    prinom = models.CharField(max_length=100, blank=True, null=True)
    segnom = models.CharField(max_length=100, blank=True, null=True)
    nombre = models.CharField(max_length=1000, blank=True, null=True)
    direccion = models.CharField(max_length=3000, db_collation='utf8_general_ci', blank=True, null=True)
    idtipdoc = models.IntegerField(blank=True, null=True)
    numdoc = models.CharField(max_length=50, blank=True, null=True)
    email = models.CharField(max_length=300, blank=True, null=True)
    telfijo = models.CharField(max_length=20, blank=True, null=True)
    telcel = models.CharField(max_length=20, blank=True, null=True)
    telofi = models.CharField(max_length=20, blank=True, null=True)
    sexo = models.CharField(max_length=1, blank=True, null=True)
    idestcivil = models.IntegerField(blank=True, null=True)
    natper = models.CharField(max_length=50, blank=True, null=True)
    conyuge = models.CharField(max_length=10, blank=True, null=True)
    nacionalidad = models.CharField(max_length=100, blank=True, null=True)
    idprofesion = models.IntegerField(blank=True, null=True)
    detaprofesion = models.CharField(max_length=1000, blank=True, null=True)
    idcargoprofe = models.IntegerField(blank=True, null=True)
    profocupa = models.CharField(max_length=1000, blank=True, null=True)
    dirfer = models.CharField(max_length=3000, blank=True, null=True)
    idubigeo = models.CharField(max_length=6, blank=True, null=True)
    cumpclie = models.CharField(max_length=15, blank=True, null=True)
    fechaing = models.CharField(max_length=10, blank=True, null=True)
    razonsocial = models.CharField(max_length=3000, db_collation='utf8_general_ci', blank=True, null=True)
    domfiscal = models.CharField(max_length=3000, db_collation='utf8_general_ci', blank=True, null=True)
    telempresa = models.CharField(max_length=12, blank=True, null=True)
    mailempresa = models.CharField(max_length=200, blank=True, null=True)
    contacempresa = models.CharField(max_length=1000, blank=True, null=True)
    fechaconstitu = models.CharField(max_length=12, blank=True, null=True)
    idsedereg = models.IntegerField(blank=True, null=True)
    numregistro = models.CharField(max_length=50, blank=True, null=True)
    numpartida = models.CharField(max_length=50, blank=True, null=True)
    actmunicipal = models.CharField(max_length=3000, blank=True, null=True)
    tipocli = models.CharField(max_length=1, blank=True, null=True)
    impeingre = models.CharField(max_length=10, blank=True, null=True)
    impnumof = models.CharField(max_length=50, blank=True, null=True)
    impeorigen = models.CharField(max_length=3000, blank=True, null=True)
    impentidad = models.CharField(max_length=3000, blank=True, null=True)
    impremite = models.CharField(max_length=3000, blank=True, null=True)
    impmotivo = models.CharField(max_length=3000, blank=True, null=True)
    residente = models.CharField(max_length=2, blank=True, null=True)
    docpaisemi = models.CharField(max_length=100, blank=True, null=True)
    partidaconyuge = models.CharField(max_length=15, blank=True, null=True)
    separaciondebienes = models.CharField(max_length=1, blank=True, null=True)
    idsedeconyuge = models.CharField(max_length=11, blank=True, null=True)
    numdoc_plantilla = models.CharField(max_length=11, blank=True, null=True)
    profesion_plantilla = models.CharField(max_length=200, blank=True, null=True)
    ubigeo_plantilla = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'cliente'


class Cliente2(models.Model):
    """
    Model representing the client in the system.
    This table stores information about the clients and their details.
    """

    idcontratante = models.CharField(primary_key=True, max_length=10)
    idcliente = models.CharField(max_length=10)
    tipper = models.CharField(max_length=1)
    apepat = models.CharField(max_length=100, blank=True, null=True)
    apemat = models.CharField(max_length=100, blank=True, null=True)
    prinom = models.CharField(max_length=100, blank=True, null=True)
    segnom = models.CharField(max_length=100, blank=True, null=True)
    nombre = models.CharField(max_length=1000, blank=True, null=True)
    direccion = models.CharField(max_length=3000, blank=True, null=True)
    idtipdoc = models.IntegerField()
    numdoc = models.CharField(max_length=50)
    email = models.CharField(max_length=300, blank=True, null=True)
    telfijo = models.CharField(max_length=20, blank=True, null=True)
    telcel = models.CharField(max_length=20, blank=True, null=True)
    telofi = models.CharField(max_length=20, blank=True, null=True)
    sexo = models.CharField(max_length=1, blank=True, null=True)
    idestcivil = models.IntegerField()
    natper = models.CharField(max_length=50, blank=True, null=True)
    conyuge = models.CharField(max_length=10, blank=True, null=True)
    nacionalidad = models.CharField(max_length=100, blank=True, null=True)
    idprofesion = models.IntegerField(blank=True, null=True)
    detaprofesion = models.CharField(max_length=1000, blank=True, null=True)
    idcargoprofe = models.IntegerField(blank=True, null=True)
    profocupa = models.CharField(max_length=1000, blank=True, null=True)
    dirfer = models.CharField(max_length=300, blank=True, null=True)
    idubigeo = models.CharField(max_length=6)
    cumpclie = models.CharField(max_length=15)
    fechaing = models.CharField(max_length=10, blank=True, null=True)
    razonsocial = models.CharField(max_length=3000, blank=True, null=True)
    domfiscal = models.CharField(max_length=3000, blank=True, null=True)
    telempresa = models.CharField(max_length=12, blank=True, null=True)
    mailempresa = models.CharField(max_length=200, blank=True, null=True)
    contacempresa = models.CharField(max_length=3000, blank=True, null=True)
    fechaconstitu = models.CharField(max_length=12, blank=True, null=True)
    idsedereg = models.IntegerField()
    numregistro = models.CharField(max_length=50, blank=True, null=True)
    numpartida = models.CharField(max_length=50, blank=True, null=True)
    actmunicipal = models.CharField(max_length=3000, blank=True, null=True)
    tipocli = models.CharField(max_length=1, blank=True, null=True)
    impeingre = models.CharField(max_length=10, blank=True, null=True)
    impnumof = models.CharField(max_length=50, blank=True, null=True)
    impeorigen = models.CharField(max_length=3000, blank=True, null=True)
    impentidad = models.CharField(max_length=3000, blank=True, null=True)
    impremite = models.CharField(max_length=3000, blank=True, null=True)
    impmotivo = models.CharField(max_length=3000, blank=True, null=True)
    residente = models.CharField(max_length=2)
    docpaisemi = models.CharField(max_length=100, blank=True, null=True)
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


class Tiposdeacto(models.Model):
    idtipoacto = models.CharField(primary_key=True, max_length=6)
    actosunat = models.CharField(max_length=25, blank=True, null=True)
    actouif = models.CharField(max_length=25, blank=True, null=True)
    idtipkar = models.IntegerField()
    desacto = models.CharField(max_length=300)
    umbral = models.IntegerField(blank=True, null=True)
    impuestos = models.IntegerField(blank=True, null=True)
    idcalnot = models.IntegerField(blank=True, null=True)
    idecalreg = models.IntegerField(blank=True, null=True)
    idmodelo = models.IntegerField(blank=True, null=True)
    rol_part = models.CharField(max_length=10, blank=True, null=True)
    cod_ancert = models.CharField(max_length=5, blank=True, null=True)
    tipoplantilla_default = models.CharField(max_length=1, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'tiposdeacto'


class Actocondicion(models.Model):
    idcondicion = models.CharField(primary_key=True, max_length=3)
    idtipoacto = models.CharField(max_length=6)
    condicion = models.CharField(max_length=100)
    parte = models.CharField(max_length=20, blank=True, null=True)
    uif = models.CharField(max_length=20, blank=True, null=True)
    formulario = models.CharField(max_length=20, blank=True, null=True)
    montop = models.CharField(max_length=20, blank=True, null=True)
    totorgante = models.CharField(max_length=2, blank=True, null=True)
    condicionsisgen = models.CharField(max_length=100, blank=True, null=True)
    codconsisgen = models.CharField(max_length=5, blank=True, null=True)
    parte_generacion = models.CharField(max_length=1, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'actocondicion'


class DetalleActosKardex(models.Model):
    item = models.AutoField(primary_key=True)
    kardex = models.CharField(max_length=30, blank=True, null=True)
    idtipoacto = models.CharField(max_length=6)
    actosunat = models.CharField(max_length=3)
    actouif = models.CharField(max_length=3)
    idtipkar = models.IntegerField()
    desacto = models.CharField(max_length=500)

    class Meta:
        managed = False
        db_table = 'detalle_actos_kardex'


class TbAbogado(models.Model):
    idabogado = models.CharField(primary_key=True, max_length=10)
    razonsocial = models.CharField(max_length=1000, blank=True, null=True)
    direccion = models.CharField(max_length=3000, blank=True, null=True)
    distrito = models.CharField(max_length=3000, blank=True, null=True)
    documento = models.CharField(max_length=11, blank=True, null=True)
    telefono = models.CharField(max_length=100, blank=True, null=True)
    matricula = models.CharField(max_length=50, blank=True, null=True)
    fax = models.CharField(max_length=100, blank=True, null=True)
    sede_colegio = models.CharField(max_length=1000, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'tb_abogado'


class Nacionalidades(models.Model):
    idnacionalidad = models.AutoField(primary_key=True)
    codnacion = models.CharField(max_length=10, blank=True, null=True)
    desnacionalidad = models.CharField(max_length=200)
    descripcion = models.CharField(max_length=500, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'nacionalidades'


class Profesiones(models.Model):
    idprofesion = models.AutoField(primary_key=True)
    codprof = models.CharField(max_length=3)
    desprofesion = models.CharField(max_length=200)

    class Meta:
        managed = False
        db_table = 'profesiones'


class Cargoprofe(models.Model):
    idcargoprofe = models.AutoField(primary_key=True)
    codcargoprofe = models.CharField(max_length=6)
    descripcrapro = models.CharField(max_length=200)

    class Meta:
        managed = False
        db_table = 'cargoprofe'


class Ubigeo(models.Model):
    coddis = models.CharField(primary_key=True, max_length=6, db_collation='latin1_swedish_ci')
    nomdis = models.CharField(max_length=50, db_collation='latin1_swedish_ci')
    nomprov = models.CharField(max_length=50, db_collation='latin1_swedish_ci')
    nomdpto = models.CharField(max_length=50, db_collation='latin1_swedish_ci')
    coddist = models.CharField(max_length=2, db_collation='latin1_swedish_ci')
    codprov = models.CharField(max_length=2, db_collation='latin1_swedish_ci')
    codpto = models.CharField(max_length=2, db_collation='latin1_swedish_ci')

    class Meta:
        managed = False
        db_table = 'ubigeo'

class Sedesregistrales(models.Model):
    idsedereg = models.CharField(primary_key=True ,max_length=3)
    dessede = models.CharField(max_length=50)
    num_zona = models.CharField(max_length=10, blank=True, null=True)
    zona_depar = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'sedesregistrales'


class Representantes(models.Model):
    id = models.AutoField(primary_key=True)
    idcontratante = models.CharField(max_length=15, blank=True, null=True)
    kardex = models.CharField(max_length=15, blank=True, null=True)
    idtipoacto = models.CharField(max_length=15, blank=True, null=True)
    facultades = models.CharField(max_length=150, blank=True, null=True)
    inscrito = models.CharField(max_length=50, blank=True, null=True)
    sede_registral = models.CharField(max_length=15, blank=True, null=True)
    partida = models.CharField(max_length=50, blank=True, null=True)
    idcontratante_r = models.CharField(max_length=15, blank=True, null=True)
    id_ro_repre = models.CharField(max_length=50, blank=True, null=True)
    ido = models.CharField(db_column='idO', max_length=5, blank=True, null=True)  # Field name made lowercase.
    odb = models.CharField(db_column='odB', max_length=5, blank=True, null=True)  # Field name made lowercase.

    class Meta:
        managed = False
        db_table = 'representantes'


class Patrimonial(models.Model):

    itemmp = models.CharField(max_length=6, primary_key=True)
    kardex = models.CharField(max_length=30, blank=True, null=True)
    idtipoacto = models.CharField(max_length=6)
    nminuta = models.CharField(max_length=30)
    idmon = models.IntegerField()
    tipocambio = models.CharField(max_length=10, blank=True, null=True)
    importetrans = models.DecimalField(max_digits=12, decimal_places=2)
    exhibiomp = models.CharField(max_length=2)
    presgistral = models.CharField(max_length=50, blank=True, null=True)
    nregistral = models.CharField(max_length=50, blank=True, null=True)
    idsedereg = models.CharField(max_length=3)
    fpago = models.CharField(max_length=3)
    idoppago = models.CharField(max_length=5)
    ofondos = models.CharField(max_length=150, blank=True, null=True)
    item = models.IntegerField()
    des_idoppago = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'patrimonial'


class Detallevehicular(models.Model):
    detveh = models.AutoField(primary_key=True)
    kardex = models.CharField(max_length=30, blank=True, null=True)
    idtipacto = models.CharField(max_length=20, blank=True, null=True)
    idplaca = models.CharField(max_length=3)
    numplaca = models.CharField(max_length=50)
    clase = models.CharField(max_length=50, blank=True, null=True)
    marca = models.CharField(max_length=100, blank=True, null=True)
    anofab = models.CharField(max_length=30, blank=True, null=True)
    modelo = models.CharField(max_length=100, blank=True, null=True)
    combustible = models.CharField(max_length=100, blank=True, null=True)
    carroceria = models.CharField(max_length=100, blank=True, null=True)
    fecinsc = models.CharField(max_length=30, blank=True, null=True)
    color = models.CharField(max_length=100, blank=True, null=True)
    motor = models.CharField(max_length=100, blank=True, null=True)
    numcil = models.CharField(max_length=3, blank=True, null=True)
    numserie = models.CharField(max_length=30, blank=True, null=True)
    numrueda = models.CharField(max_length=3, blank=True, null=True)
    idmon = models.CharField(max_length=5, blank=True, null=True)
    precio = models.DecimalField(max_digits=16, decimal_places=2, blank=True, null=True)
    codmepag = models.CharField(max_length=4, blank=True, null=True)
    pregistral = models.CharField(max_length=100, blank=True, null=True)
    idsedereg = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'detallevehicular'


class Detallebienes(models.Model):
    detbien = models.AutoField(primary_key=True)
    itemmp = models.CharField(max_length=6)
    kardex = models.CharField(max_length=30, blank=True, null=True)
    idtipacto = models.CharField(max_length=10, blank=True, null=True)
    tipob = models.CharField(max_length=100)
    idtipbien = models.IntegerField()
    coddis = models.CharField(max_length=6)
    fechaconst = models.CharField(max_length=12)
    oespecific = models.CharField(max_length=200)
    smaquiequipo = models.CharField(max_length=200)
    tpsm = models.CharField(max_length=3)
    npsm = models.CharField(max_length=200)
    pregistral = models.CharField(max_length=50, blank=True, null=True)
    idsedereg = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'detallebienes'


class Detallemediopago(models.Model):
    detmp = models.AutoField(primary_key=True)
    itemmp = models.CharField(max_length=6, blank=True, null=True)
    kardex = models.CharField(max_length=30, blank=True, null=True)
    tipacto = models.CharField(max_length=10, blank=True, null=True)
    codmepag = models.IntegerField(blank=True, null=True)
    fpago = models.CharField(max_length=10, blank=True, null=True)
    idbancos = models.IntegerField(blank=True, null=True)
    importemp = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    idmon = models.CharField(max_length=10, blank=True, null=True)
    foperacion = models.CharField(max_length=12, blank=True, null=True)
    documentos = models.CharField(max_length=500, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'detallemediopago'

class TplTemplate(models.Model):
    pktemplate = models.AutoField(db_column='pkTemplate', primary_key=True)  # Field name made lowercase.
    nametemplate = models.CharField(db_column='nameTemplate', max_length=250, blank=True, null=True)  # Field name made lowercase.
    fktypekardex = models.IntegerField(db_column='fkTypeKardex', blank=True, null=True)  # Field name made lowercase.
    codeacts = models.CharField(db_column='codeActs', max_length=50, blank=True, null=True)  # Field name made lowercase.
    contract = models.CharField(max_length=3000, blank=True, null=True)
    urltemplate = models.CharField(db_column='urlTemplate', max_length=250, blank=True, null=True)  # Field name made lowercase.
    filename = models.CharField(db_column='fileName', max_length=250, blank=True, null=True)  # Field name made lowercase.
    registrationdate = models.DateTimeField(db_column='registrationDate', blank=True, null=True)  # Field name made lowercase.
    statusregister = models.IntegerField(db_column='statusRegister', blank=True, null=True)  # Field name made lowercase.

    class Meta:
        managed = False
        db_table = 'tpl_template'