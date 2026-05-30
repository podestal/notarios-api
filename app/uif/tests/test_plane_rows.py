from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from uif.services.keys import normalize_act_code, resolve_instrumento_letter
from uif.services.plane_rows import (
    PLANE_BODY_LINE_LENGTH,
    PHP_PLANE_FIELD_WIDTHS,
    PlaneRowBuilder,
    format_plane_body_line,
)
from uif.services.ro_text import remplace_string_ro


class PlaneRowBuilderTests(SimpleTestCase):
    def test_php_plane_body_line_length_constant(self):
        self.assertEqual(PLANE_BODY_LINE_LENGTH, 858)

    def test_resolve_instrumento_letter_ignores_tipo_envio(self):
        self.assertEqual(
            resolve_instrumento_letter({"tipo": "I", "idtipkar": 1}),
            "E",
        )
        self.assertEqual(
            resolve_instrumento_letter({"tipo_instrumento": "T", "tipo": "I"}),
            "T",
        )

    def test_normalize_act_code_zfills_three_digits(self):
        self.assertEqual(normalize_act_code("12"), "012")
        self.assertEqual(normalize_act_code("094"), "094")

    def test_format_plane_body_line_matches_php_sample(self):
        row = {f"item_{i}": "" for i in range(1, 58)}
        row.update(
            {
                "item_1": "1",
                "item_2": "7",
                "item_3": "I",
                "item_4": "E",
                "item_5": "619",
                "item_6": "20260401",
                "item_9": "C",
                "item_11": "U",
                "item_50": "PEN",
                "item_51": "20000.00",
                "item_52": "0.00",
                "item_53": "20000.00",
                "item_54": "0.00",
                "item_55": "N",
            }
        )
        line = format_plane_body_line(row)
        self.assertEqual(len(line), 858)
        self.assertTrue(line.startswith("       1       7IE 619   "))
        idx = line.index("PEN")
        self.assertEqual(line[idx + 3 : idx + 21], "          20000.00")
        self.assertTrue(line.rstrip().endswith("N"))

    def test_reemplace_string_ro_accents(self):
        self.assertEqual(remplace_string_ro("José"), "Jose")

    def test_format_plane_body_line_sanitizes_juridical_razon_social(self):
        row = {f"item_{i}": "" for i in range(1, 58)}
        row["item_23"] = "S & V TRANSPORTES Y SERVICIOS TURISTICOS E.I.R.L."
        line = format_plane_body_line(row)
        self.assertEqual(len(line), 858)
        pos = sum(
            PHP_PLANE_FIELD_WIDTHS[i]
            for i in range(1, 23)
        )
        field_23 = line[pos : pos + PHP_PLANE_FIELD_WIDTHS[23]]
        self.assertEqual(
            field_23,
            "S  V TRANSPORTES Y SERVICIOS TURISTICOS EIRL".ljust(120),
        )

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

    @patch.object(PlaneRowBuilder, "_bien_registral", return_value=("N", "", ""))
    @patch.object(PlaneRowBuilder, "_load_contratantes")
    @patch.object(PlaneRowBuilder, "_load_detalle_medio")
    @patch.object(PlaneRowBuilder, "_load_participants")
    @patch.object(PlaneRowBuilder, "_load_patrimonial")
    def test_no_operation_row_without_detalle_medio_php_parity(
        self,
        mock_pat,
        mock_participants,
        mock_detalle,
        mock_contratantes,
        _mock_bien,
    ):
        """PHP only emits tipoFila=1 rows when detallemediopago has rows for the act."""
        mock_pat.return_value = {
            ("K1-2026", "094"): MagicMock(
                idmon=1, importetrans=1000, tipocambio="1.00", fpago="1", idoppago="1"
            )
        }
        mock_detalle.return_value = {}
        mock_contratantes.return_value = {"K1-2026": []}
        mock_participants.return_value = []

        builder = PlaneRowBuilder()
        builder._fpago_map = {"1": "C"}
        builder._medio_map = {}
        builder._moneda_map = {1: "PEN"}

        rows = builder.build_rows(
            [
                {
                    "kardex": "K1-2026",
                    "codacto": "094",
                    "tipo": "I",
                    "tipo_instrumento": "E",
                    "idtipkar": 1,
                    "numescritura": "1",
                    "fechaescritura": "2026-04-15",
                    "uif_code": "010",
                }
            ]
        )
        self.assertEqual(rows, [])

    @patch.object(PlaneRowBuilder, "_bien_registral")
    @patch.object(PlaneRowBuilder, "_load_contratantes")
    @patch.object(PlaneRowBuilder, "_load_detalle_medio")
    @patch.object(PlaneRowBuilder, "_load_participants", return_value=[])
    @patch.object(PlaneRowBuilder, "_load_patrimonial")
    def test_bien_registral_uses_escritura_not_tipo_envio(
        self,
        mock_pat,
        _mock_participants,
        mock_detalle,
        mock_contratantes,
        mock_bien,
    ):
        mock_pat.return_value = {}
        mock_detalle.return_value = {}
        mock_contratantes.return_value = {}
        mock_bien.return_value = ("N", "", "")

        builder = PlaneRowBuilder()
        builder._fpago_map = {}
        builder._medio_map = {1: "01"}
        builder._moneda_map = {1: "PEN"}
        builder.build_rows(
            [
                {
                    "kardex": "K1-2026",
                    "codacto": "094",
                    "tipo": "I",
                    "tipo_instrumento": "E",
                    "idtipkar": 1,
                    "numescritura": "1",
                    "fechaescritura": "2026-04-15",
                    "uif_code": "010",
                }
            ]
        )
        mock_bien.assert_called_once()
        ro_arg = mock_bien.call_args[0][2]
        self.assertEqual(resolve_instrumento_letter(ro_arg), "E")
