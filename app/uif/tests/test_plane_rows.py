from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from uif.services.plane_rows import PLANE_BODY_LINE_LENGTH, PlaneRowBuilder
from uif.services.ro_text import remplace_string_ro


class PlaneRowBuilderTests(SimpleTestCase):
    def test_php_plane_body_line_length_constant(self):
        self.assertEqual(PLANE_BODY_LINE_LENGTH, 858)

    def test_reemplace_string_ro_accents(self):
        self.assertEqual(remplace_string_ro("José"), "Jose")

    @patch.object(PlaneRowBuilder, "_bien_registral", return_value=("N", "", ""))
    @patch.object(PlaneRowBuilder, "_load_contratantes")
    @patch.object(PlaneRowBuilder, "_load_detalle_medio")
    @patch.object(PlaneRowBuilder, "_load_participants")
    @patch.object(PlaneRowBuilder, "_group_medios")
    @patch.object(PlaneRowBuilder, "_load_patrimonial")
    def test_participant_row_modalidad_u_and_shared_registration(
        self,
        mock_pat,
        mock_medios,
        mock_participants,
        mock_detalle,
        mock_contratantes,
        _mock_bien,
    ):
        mock_pat.return_value = {}
        mock_medios.return_value = []
        mock_detalle.return_value = {}
        mock_contratantes.return_value = {"K1-2026": []}

        mock_participants.return_value = [
            {
                "cxa": MagicMock(
                    uif="O",
                    monto="1000.50",
                    ofondo="origen",
                    kardex="K1-2026",
                    idtipoacto="094",
                ),
                "cliente": MagicMock(
                    tipper="N",
                    idtipdoc=1,
                    numdoc="12345678",
                    apepat="PEREZ",
                    apemat="GARCIA",
                    prinom="JUAN",
                    segnom="",
                    residente="1",
                    nacionalidad="1",
                    cumpclie="15/01/1990",
                    idestcivil=1,
                    idprofesion=1,
                    idcargoprofe=1,
                    detaprofesion="",
                    contacempresa="",
                    actmunicipal="",
                    direccion="LIMA",
                    domfiscal="",
                    idubigeo="",
                    conyuge="",
                    telcel="999888777",
                    telfijo="",
                    telofi="",
                ),
                "contratante": MagicMock(
                    firma="1",
                    fechafirma="15/04/2026",
                    inscrito=None,
                    idsedereg="",
                    numpartida="",
                    idcontratanterp="",
                ),
            },
            {
                "cxa": MagicMock(
                    uif="B",
                    monto="1000.50",
                    ofondo="",
                    kardex="K1-2026",
                    idtipoacto="094",
                ),
                "cliente": MagicMock(
                    tipper="N",
                    idtipdoc=1,
                    numdoc="87654321",
                    apepat="LOPEZ",
                    apemat="DIAZ",
                    prinom="MARIA",
                    segnom="",
                    residente="1",
                    nacionalidad="1",
                    cumpclie="20/05/1992",
                    idestcivil=2,
                    idprofesion=None,
                    idcargoprofe=None,
                    detaprofesion="",
                    contacempresa="",
                    actmunicipal="",
                    direccion="AREQUIPA",
                    domfiscal="",
                    idubigeo="",
                    conyuge="",
                ),
                "contratante": None,
            },
        ]

        builder = PlaneRowBuilder()
        builder._fpago_map = {}
        builder._medio_map = {}
        builder._moneda_map = {1: "PEN"}
        builder._tipodoc_map = {1: "1"}
        builder._prof_map = {1: "001"}
        builder._cargo_map = {}
        builder._civil_map = {1: "1"}
        builder._nacion_map = {"1": "PE"}
        builder._ciiu_map = {}

        ro_records = [
            {
                "kardex": "K1-2026",
                "codacto": "094",
                "tipo": "I",
                "tipo_instrumento": "E",
                "idtipkar": 1,
                "numescritura": "100",
                "fechaescritura": "2026-04-15",
                "fechaconclusion": "",
                "uif_code": "010",
            }
        ]
        rows = builder.build_rows(ro_records)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["item_2"], rows[1]["item_2"])
        self.assertEqual(rows[0]["item_11"], "U")
        self.assertEqual(rows[0]["item_14"], "O")
        self.assertEqual(rows[1]["item_15"], "B")
        self.assertEqual(rows[0]["item_51"], "0.00")
        self.assertEqual(rows[0]["item_52"], "1000.50")
        self.assertEqual(rows[0]["item_6"], "20260415")
        self.assertEqual(rows[0]["item_10"], "20260415")
        self.assertEqual(rows[0]["item_39"], "999888777")

    @patch.object(PlaneRowBuilder, "_bien_registral", return_value=("N", "", ""))
    @patch.object(PlaneRowBuilder, "_load_contratantes")
    @patch.object(PlaneRowBuilder, "_load_detalle_medio")
    @patch.object(PlaneRowBuilder, "_load_participants")
    @patch.object(PlaneRowBuilder, "_group_medios")
    @patch.object(PlaneRowBuilder, "_load_patrimonial")
    def test_medio_pago_row_before_participants(
        self,
        mock_pat,
        mock_medios,
        mock_participants,
        mock_detalle,
        mock_contratantes,
        _mock_bien,
    ):
        mock_pat.return_value = {}
        mock_medios.return_value = [{"codmepag": 1, "tipacto": "094", "monto": 500}]
        mock_participants.return_value = []
        mock_detalle.return_value = {}
        mock_contratantes.return_value = {"K1-2026": []}

        builder = PlaneRowBuilder()
        builder._fpago_map = {}
        builder._medio_map = {1: "01"}
        builder._moneda_map = {1: "PEN"}
        builder._tipodoc_map = {}

        ro_records = [
            {
                "kardex": "K1-2026",
                "codacto": "094",
                "tipo": "I",
                "tipo_instrumento": "E",
                "numescritura": "1",
                "fechaescritura": "2026-04-15",
                "fechaconclusion": "15/04/2026",
                "uif_code": "010",
            }
        ]
        rows = builder.build_rows(ro_records)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["item_44"], "01")
        self.assertEqual(rows[0]["item_52"], "0.00")
        self.assertEqual(rows[0]["item_53"], "500.00")
