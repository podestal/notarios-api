import pytest
from model_bakery import baker
from rest_framework.test import APIClient
from notaria import models

@pytest.fixture
def api_client():
    """Fixture to create an APIClient instance."""
    return APIClient()

# Simple approach: Use pytest-django's database fixtures and handle unmanaged models
@pytest.fixture(autouse=True)
def enable_db_access_for_all_tests(transactional_db):
    """
    Enable database access for all tests and temporarily make models managed.
    """
    # List of models that are unmanaged
    unmanaged_models = [
        models.Usuarios,
        models.Kardex,
        models.Contratantes,
        models.Contratantesxacto,
        models.Cliente2,
        models.Tipodocumento,
        models.Tipoestacivil,
        models.PermisosUsuarios,
    ]
    
    # Temporarily make models managed
    for model in unmanaged_models:
        model._meta.managed = True
    
    yield
    
    # Restore original state
    for model in unmanaged_models:
        model._meta.managed = False

@pytest.fixture
def sample_usuario():
    """Fixture to create a sample Usuario for testing."""
    return baker.make(
        models.Usuarios,
        idusuario=1,
        loginusuario='testuser',
        apepat='TestApellido',
        apemat='TestApellido2', 
        prinom='TestNombre',
        segnom='TestNombre2',
        dni='12345678',
        estado=1,
        fecnac='01/01/1990',
        domicilio='Test Address',
        idubigeo=1,
        telefono='123456789',
        idcargo=1,
        password='testpass'
    )

@pytest.fixture
def sample_kardex(sample_usuario):
    """Fixture to create a sample Kardex for testing."""
    return baker.make(
        models.Kardex,
        idkardex=1,
        kardex='KAR1-2024',
        idtipkar=1,
        kardexconexo='12345678',
        fechaingreso='01/01/2024',
        horaingreso='10:00:00',
        contrato='Test Contract',
        codactos='001',
        idusuario=sample_usuario.idusuario,
        responsable=1,
        observacion='Test observation',
        documentos='Test documents',
        fechacalificado='02/01/2024',
        fechainstrumento='03/01/2024',
        fechaconclusion='04/01/2024',
        comunica1='Test communication',
        contacto='Test contact',
        telecontacto='123456789',
        mailcontacto='test@test.com',
        retenido=0,
        desistido=0,
        autorizado=1,
        idrecogio=1,
        pagado=1,
        visita=0,
        dregistral='DR001',
        dnotarial='DN001',
        idnotario=1
    )

@pytest.fixture
def sample_contratante(sample_kardex):
    """Fixture to create a sample Contratante for testing."""
    return baker.make(
        models.Contratantes,
        idcontratante='1001',
        idtipkar=sample_kardex.idtipkar,
        kardex=sample_kardex.kardex,
        condicion='VENDEDOR',
        firma='0',
        resfirma=0,
        tiporepresentacion='01',
        facultades='Test facultades',
        indice='001',
        visita='0'
    )

@pytest.fixture
def sample_cliente(sample_contratante):
    """Fixture to create a sample Cliente2 for testing."""
    return baker.make(
        models.Cliente2,
        idcontratante=sample_contratante.idcontratante,
        idcliente='C001',
        tipper='N',
        nombre='Juan Perez',
        numdoc='12345678',
        idtipdoc=1,
        idestcivil=1,
        idubigeo='150101',
        cumpclie='123456789012345',
        idsedereg=1,
        residente='01'
    )