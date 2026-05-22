from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from uif.services.conyuge_fields import (
    lookup_spouse_in_act,
    participacion_conyuge_sql_default,
    resolve_conyuge_fields,
)
from uif.services.participant_fields_validator import ParticipantFieldsValidator
from uif.services.ro_validation_rules import RoValidationRulesRepository


class ConyugeFieldsTests(SimpleTestCase):
    def test_participacion_default_natural_with_conyuge(self):
        cliente = MagicMock(tipper="N", conyuge="99")
        self.assertEqual(participacion_conyuge_sql_default(cliente), "N")

    def test_participacion_default_juridica_sin_conyuge(self):
        cliente = MagicMock(tipper="J", conyuge="")
        self.assertEqual(participacion_conyuge_sql_default(cliente), "")

    @patch("uif.services.conyuge_fields.Cliente2")
    @patch("uif.services.conyuge_fields.Contratantesxacto")
    def test_resolve_spouse_in_act(self, mock_cxa, mock_cliente):
        spouse = MagicMock(
            apepat="QUISPE",
            apemat="LUQUE",
            prinom="JOVITA",
            segnom="",
            idcontratante="C2",
        )
        mock_cliente.objects.filter.return_value.first.return_value = spouse
        mock_cxa.objects.filter.return_value.first.return_value = MagicMock()

        participacion, ap_pat, ap_mat, nom = resolve_conyuge_fields(
            MagicMock(tipper="N", conyuge="99"),
            "O",
            "K1",
            "094",
        )
        self.assertEqual(participacion, "S")
        self.assertEqual(ap_pat, "QUISPE")
        self.assertEqual(ap_mat, "LUQUE")
        self.assertIn("JOVITA", nom)

    @patch("uif.services.conyuge_fields.lookup_spouse_in_act", return_value=None)
    def test_resolve_spouse_missing_returns_n(self, _lookup):
        participacion, ap_pat, ap_mat, nom = resolve_conyuge_fields(
            MagicMock(tipper="N", conyuge="99"),
            "O",
            "K1",
            "094",
        )
        self.assertEqual(participacion, "N")
        self.assertEqual(ap_pat, "")


class ConyugeValidatorTests(SimpleTestCase):
    def setUp(self):
        rules = RoValidationRulesRepository()
        rules._loaded = True
        self.validator = ParticipantFieldsValidator(rules)

    @patch.object(ParticipantFieldsValidator, "_ubigeo")
    @patch(
        "uif.services.participant_fields_validator.resolve_conyuge_fields",
        return_value=("N", "", "", ""),
    )
    def test_spouse_not_in_act_raises_four_errors(self, _resolve, mock_ubigeo):
        mock_ubigeo.return_value = MagicMock(coddis="150101")
        cliente = MagicMock(
            tipper="N",
            conyuge="99",
            idtipdoc=1,
            numdoc="12345678",
            apepat="A",
            apemat="B",
            prinom="C",
            segnom="",
            nacionalidad="1",
            idestcivil=1,
            idprofesion=1,
            idcargoprofe=1,
            direccion="X",
            idubigeo="150101",
            residente="1",
            razonsocial="",
            domfiscal="",
            contacempresa="",
            actmunicipal="",
        )
        self.validator._tipodoc_map = {1: "1"}
        self.validator._prof_map = {1: True}
        self.validator._cargo_map = {1: True}
        self.validator._civil_map = {1: True}
        self.validator._nacion_map = {"1": "PE"}
        self.validator._ciiu_keys = set()

        item = {
            "role": "O",
            "cxa": MagicMock(uif="O"),
            "cliente": cliente,
            "contratante": MagicMock(
                firma="1",
                fechafirma="15/04/2026",
                inscrito=None,
                idsedereg="",
                numpartida="",
                idcontratanterp="",
                idcontratante="C1",
            ),
            "nombre": "A B C",
        }
        staged = MagicMock(
            kardex="K1",
            cod_acto="094",
            uif_code="010",
            id_kardex=1,
        )
        errors = self.validator._validate_one(
            item=item,
            staged=staged,
            act_description="ACTO",
            uif_code="010",
            cod_acto_spouse="094",
        )
        types = {e["error_type"] for e in errors}
        self.assertIn("spouse_not_in_act", types)
        self.assertIn("missing_nombres_conyuge", types)
