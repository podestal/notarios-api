from datetime import date
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from uif.services.complementary import (
    escritura_before_range,
    firma_in_report_range,
    has_medios_for_act,
)
from uif.services.participant_fields_validator import ParticipantFieldsValidator
from uif.services.ro_validation_rules import RoValidationRulesRepository


class ComplementaryHelpersTests(SimpleTestCase):
    def test_firma_in_report_range(self):
        self.assertTrue(
            firma_in_report_range("15/04/2026", date(2026, 4, 1), date(2026, 4, 30))
        )
        self.assertFalse(
            firma_in_report_range("01/03/2026", date(2026, 4, 1), date(2026, 4, 30))
        )

    @patch("uif.services.complementary.Kardex")
    def test_escritura_before_range(self, mock_kardex_model):
        mock_kardex_model.objects.filter.return_value.only.return_value.first.return_value = (
            MagicMock(fechaescritura=date(2025, 12, 1))
        )
        self.assertTrue(escritura_before_range("K1", date(2026, 4, 1)))

    def test_has_medios_for_act(self):
        det = MagicMock(kardex="K1", tipacto="094", codmepag=1)
        self.assertTrue(has_medios_for_act("K1", "094", [det]))


class ComplementaryValidatorTests(SimpleTestCase):
    def setUp(self):
        rules = RoValidationRulesRepository()
        rules._loaded = True
        self.validator = ParticipantFieldsValidator(rules)
        self.validator._tipodoc_map = {1: "1"}
        self.validator._prof_map = {1: True}
        self.validator._cargo_map = {1: True}
        self.validator._civil_map = {1: True}
        self.validator._nacion_map = {"1": "PE"}
        self.validator._ciiu_keys = set()

    @patch.object(ParticipantFieldsValidator, "_ubigeo")
    @patch.object(ParticipantFieldsValidator, "_collect_participants_complementary")
    @patch("uif.services.participant_fields_validator.has_medios_for_act", return_value=True)
    @patch("uif.services.participant_fields_validator.escritura_before_range", return_value=True)
    def test_tipo_c_runs_participant_validation(
        self, _esc, _medios, mock_collect, mock_ubigeo
    ):
        mock_ubigeo.return_value = MagicMock(coddis="150101")
        mock_collect.return_value = [
            {
                "role": "O",
                "cxa": MagicMock(uif="O", monto="100"),
                "cliente": MagicMock(
                    tipper="N",
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
                    conyuge="",
                ),
                "contratante": MagicMock(
                    firma="1",
                    fechafirma="15/04/2026",
                    inscrito=None,
                    idsedereg="",
                    numpartida="",
                    idcontratanterp="",
                ),
                "nombre": "A B C",
            }
        ]
        staged = MagicMock(
            tipo="C",
            kardex="K1",
            cod_acto="094",
            uif_code="010",
            id_kardex=1,
            fechaconclusion="",
        )
        errors = self.validator.validate(
            staged=staged,
            act_description="ACTO",
            contratantes_map={"K1": []},
            clientes_map={},
            contratantesxacto_map={},
            detalle_medio_pago_rows=[MagicMock()],
            range_start=date(2026, 4, 1),
            range_end=date(2026, 4, 30),
        )
        self.assertFalse(any(e["error_type"] == "missing_otorgante_role" for e in errors))
