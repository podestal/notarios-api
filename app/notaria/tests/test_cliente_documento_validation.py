import pytest
from rest_framework.exceptions import ValidationError

from notaria import utils
from notaria.serializers import CreateClienteSerializer, ClienteSerializer


class _JuridicaInstance:
    def __init__(self, tipper="J", idtipdoc=8, numdoc="20555555555"):
        self.tipper = tipper
        self.idtipdoc = idtipdoc
        self.numdoc = numdoc


@pytest.mark.parametrize(
    "attrs,expected_numdoc",
    [
        ({"tipper": "J", "idtipdoc": 8, "numdoc": "20555555555"}, "20555555555"),
        ({"tipper": "J", "idtipdoc": "8", "numdoc": " 20555555555 "}, "20555555555"),
        ({"tipper": "J", "idtipdoc": 10, "numdoc": ""}, ""),
        ({"tipper": "J", "idtipdoc": 10}, ""),
    ],
)
def test_validate_juridica_documento_accepts_valid_cases(attrs, expected_numdoc):
    result = utils.validate_juridica_documento(attrs)
    assert result.get("numdoc") == expected_numdoc


@pytest.mark.parametrize(
    "attrs,field",
    [
        ({"tipper": "J", "idtipdoc": 8, "numdoc": ""}, "numdoc"),
        ({"tipper": "J", "idtipdoc": 8, "numdoc": "123"}, "numdoc"),
        ({"tipper": "J", "idtipdoc": 10, "numdoc": "20555555555"}, "numdoc"),
    ],
)
def test_validate_juridica_documento_rejects_invalid_cases(attrs, field):
    with pytest.raises(ValidationError) as exc:
        utils.validate_juridica_documento(attrs)
    assert field in exc.value.detail


def test_validate_juridica_documento_skips_natural_person():
    attrs = {"tipper": "N", "idtipdoc": 8, "numdoc": ""}
    assert utils.validate_juridica_documento(attrs) == attrs


def test_validate_juridica_documento_partial_update_uses_instance():
    instance = _JuridicaInstance()
    assert utils.validate_juridica_documento({}, instance) == {}


def test_validate_juridica_documento_partial_update_rejects_clearing_ruc():
    instance = _JuridicaInstance()
    with pytest.raises(ValidationError) as exc:
        utils.validate_juridica_documento({"numdoc": ""}, instance)
    assert "numdoc" in exc.value.detail


def test_create_cliente_serializer_rejects_juridica_without_ruc():
    serializer = CreateClienteSerializer(
        data={
            "tipper": "J",
            "idtipdoc": 8,
            "numdoc": "",
            "apepat": "",
            "apemat": "",
            "prinom": "EMPRESA",
            "segnom": "",
            "nombre": "EMPRESA SAC",
            "direccion": "LIMA",
            "email": "",
            "telfijo": "",
            "telcel": "",
            "telofi": "",
            "sexo": "",
            "idestcivil": 0,
            "natper": "",
            "conyuge": "",
            "nacionalidad": "",
            "idprofesion": 0,
            "detaprofesion": "",
            "idcargoprofe": 0,
            "profocupa": "",
            "dirfer": "",
            "idubigeo": ".",
            "cumpclie": ".",
            "razonsocial": "EMPRESA SAC",
            "domfiscal": "",
            "idsedereg": 0,
            "numpartida": "",
            "telempresa": "",
            "actmunicipal": "",
            "contacempresa": "",
            "fechaconstitu": "",
            "numregistro": "",
            "numdoc_plantilla": "",
            "residente": "",
        }
    )
    assert not serializer.is_valid()
    assert "numdoc" in serializer.errors


def test_cliente_serializer_update_rejects_sin_documento_with_ruc():
    instance = _JuridicaInstance(idtipdoc=10, numdoc="")
    serializer = ClienteSerializer(
        instance=instance,
        data={"idtipdoc": 10, "numdoc": "20555555555"},
        partial=True,
    )
    assert not serializer.is_valid()
    assert "numdoc" in serializer.errors
