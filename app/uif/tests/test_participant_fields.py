from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from uif.services.participant_fields_validator import ParticipantFieldsValidator
from uif.services.ro_validation_rules import RoValidationRulesRepository


class ParticipantFieldsValidatorTests(SimpleTestCase):
    def setUp(self):
        rules = RoValidationRulesRepository()
        rules._loaded = True
        rules._rules = {}
        rules._field_labels = {}
        self.validator = ParticipantFieldsValidator(rules)
        self.validator._tipodoc_map = {1: "1"}
        self.validator._prof_map = {1: True}
        self.validator._cargo_map = {1: True}
        self.validator._civil_map = {1: True}
        self.validator._nacion_map = {"1": "PE"}
        self.validator._ciiu_keys = set()
        self.validator._ubigeo_cache = {"150101": MagicMock(codpto="15", codprov="01", coddist="01")}

    def _staged(self, tipo="I", uif="010"):
        s = MagicMock()
        s.tipo = tipo
        s.kardex = "K1"
        s.cod_acto = "094"
        s.uif_code = uif
        s.id_kardex = 1
        return s

    def _cliente_natural(self, **kwargs):
        c = MagicMock()
        c.tipper = "N"
        c.idtipdoc = 1
        c.numdoc = "12345678"
        c.apepat = "PEREZ"
        c.apemat = "GARCIA"
        c.prinom = "JUAN"
        c.segnom = ""
        c.nacionalidad = "1"
        c.idestcivil = 1
        c.idprofesion = 1
        c.idcargoprofe = 1
        c.direccion = "LIMA"
        c.idubigeo = "150101"
        c.residente = "1"
        c.cumpclie = "01/01/1990"
        c.conyuge = ""
        for k, v in kwargs.items():
            setattr(c, k, v)
        return c

    def test_missing_participants_structural(self):
        staged = self._staged()
        errors = self.validator.validate(
            staged=staged,
            act_description="COMPRA VENTA",
            contratantes_map={"K1": []},
            clientes_map={},
            contratantesxacto_map={},
        )
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["error_type"], "missing_participants")
        self.assertEqual(errors[0]["codeElement"], 590)

    def test_invalid_dni(self):
        staged = self._staged()
        contratante = MagicMock(idcontratante="1", idcontratanterp="", inscrito=None, firma="1", fechafirma="15/04/2026", idsedereg="", numpartida="")
        cliente = self._cliente_natural(numdoc="123")
        cxa = MagicMock(uif="O", monto="100")
        errors = self.validator.validate(
            staged=staged,
            act_description="ACTO",
            contratantes_map={"K1": [contratante]},
            clientes_map={"1": cliente},
            contratantesxacto_map={"K1_094_1": cxa},
        )
        self.assertTrue(any(e["error_type"] == "invalid_dni" for e in errors))

    def test_missing_otorgante_role(self):
        staged = self._staged(uif="010")
        contratante = MagicMock(idcontratante="1", idcontratanterp="", inscrito=None, firma="1", fechafirma="15/04/2026", idsedereg="", numpartida="")
        cliente = self._cliente_natural()
        cxa = MagicMock(uif="B", monto="100")
        errors = self.validator.validate(
            staged=staged,
            act_description="ACTO",
            contratantes_map={"K1": [contratante]},
            clientes_map={"1": cliente},
            contratantesxacto_map={"K1_094_1": cxa},
        )
        self.assertFalse(any(e["error_type"] == "missing_beneficiario_role" for e in errors))
        self.assertTrue(any(e["error_type"] == "missing_otorgante_role" for e in errors))

    def test_skips_tipo_complementario(self):
        staged = self._staged(tipo="C")
        errors = self.validator.validate(
            staged=staged,
            act_description="ACTO",
            contratantes_map={},
            clientes_map={},
            contratantesxacto_map={},
        )
        self.assertEqual(errors, [])

    def test_natural_person_without_firma_does_not_raise_missing_fecha_firma(self):
        """PHP parity: missing firma/fechafirma only affects plane conclusion N, not RO errors."""
        staged = self._staged()
        contratante = MagicMock(
            idcontratante="1",
            idcontratanterp="",
            inscrito=None,
            firma="0",
            fechafirma="",
            idsedereg="",
            numpartida="",
        )
        cliente = self._cliente_natural()
        cxa = MagicMock(uif="O", monto="100")
        errors = self.validator.validate(
            staged=staged,
            act_description="TRANSFERENCIA DE ACCIONES SOCIALES A TITULO GRATUITO",
            contratantes_map={"K1": [contratante]},
            clientes_map={"1": cliente},
            contratantesxacto_map={"K1_094_1": cxa},
        )
        self.assertFalse(any(e["error_type"] == "missing_fecha_firma" for e in errors))

    @patch.object(ParticipantFieldsValidator, "_resolve_persona_que_representa", return_value="O")
    def test_representante_missing_inscrito(self, _mock_rep):
        staged = self._staged()
        contratante = MagicMock(
            idcontratante="1",
            idcontratanterp="2",
            inscrito=None,
            firma="1",
            fechafirma="15/04/2026",
            idsedereg="1",
            numpartida="123",
        )
        cliente = self._cliente_natural()
        cxa = MagicMock(uif="R", monto="0")
        errors = self.validator.validate(
            staged=staged,
            act_description="ACTO",
            contratantes_map={"K1": [contratante]},
            clientes_map={"1": cliente},
            contratantesxacto_map={"K1_094_1": cxa},
        )
        self.assertTrue(
            any(e["fieldNumber"] == 17 and e["error_type"] == "missing_tipo_representacion" for e in errors)
        )
