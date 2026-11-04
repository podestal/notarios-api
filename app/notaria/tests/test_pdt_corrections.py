from unittest import mock

from django.test import SimpleTestCase

from notaria.services.pdt_corrections_service import PdtCorrectionService
from notaria.services.pdt_error_item import (
    CATEGORY_ACTOS,
    CATEGORY_BIENES,
    CATEGORY_MEDIO_PAGO,
    CATEGORY_OTORGANTES,
    TYPE_ACT_MINUTA,
    TYPE_BIEN_INSERT,
    TYPE_BIEN_RELINK,
    TYPE_MP_DOCUMENTOS,
    TYPE_OTG_RENTA,
    TYPE_OTG_RUC,
    build_pdt_error_item,
)


class PdtErrorItemTests(SimpleTestCase):
    def test_build_item_php_shape(self):
        item = build_pdt_error_item(
            kardex="K1-2026",
            id_kardex=10,
            error_item="No existe bien, ingrese un bien",
            act="COMPRAVENTA",
            file_type="BIE",
            type_act="030",
            item_mp="000123",
            writing_date="2026-10-01",
            category_correct=CATEGORY_BIENES,
            type_of_correction=TYPE_BIEN_INSERT,
            is_correctable=True,
        )
        self.assertEqual(item["isCorrectable"], 1)
        self.assertEqual(item["categoryCorrect"], 2)
        self.assertEqual(item["typeOfCorrection"], 2)
        self.assertEqual(item["typeAct"], "030")
        self.assertEqual(item["writingDate"], "01/10/2026")


class PdtCorrectionServiceTests(SimpleTestCase):
    def test_parse_list_error_json(self):
        payload = {
            "listError": '[{"kardex":"K1","categoryCorrect":1,"typeOfCorrection":1}]'
        }
        parsed = PdtCorrectionService.parse_payload(payload)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["kardex"], "K1")

    @mock.patch("notaria.services.pdt_corrections_service.connection")
    def test_actos_updates_nminuta(self, mock_connection):
        cursor = mock.MagicMock()
        cursor.rowcount = 1
        mock_connection.cursor.return_value.__enter__.return_value = cursor

        result = PdtCorrectionService().apply(
            [
                {
                    "kardex": "K1",
                    "itemMp": "0001",
                    "writingDate": "15/10/2026",
                    "categoryCorrect": CATEGORY_ACTOS,
                    "typeOfCorrection": TYPE_ACT_MINUTA,
                }
            ]
        )
        self.assertEqual(result["error"], 0)
        self.assertIn("Se afectaron 1", result["errorDescription"])
        cursor.execute.assert_called()
        sql, params = cursor.execute.call_args[0]
        self.assertIn("UPDATE patrimonial SET nminuta", sql)
        self.assertEqual(params, ["15/10/2026", "0001"])

    @mock.patch("notaria.services.pdt_corrections_service.connection")
    def test_bien_insert_defaults(self, mock_connection):
        cursor = mock.MagicMock()
        cursor.rowcount = 1
        mock_connection.cursor.return_value.__enter__.return_value = cursor

        PdtCorrectionService().apply(
            [
                {
                    "kardex": "K1",
                    "tipoActo": "030",
                    "itemMp": "0001",
                    "categoryCorrect": CATEGORY_BIENES,
                    "typeOfCorrection": TYPE_BIEN_INSERT,
                }
            ]
        )
        sql, params = cursor.execute.call_args[0]
        self.assertIn("INSERT INTO detallebienes", sql)
        self.assertEqual(params[3], "BIENES")
        self.assertEqual(params[4], 10)
        self.assertEqual(params[5], "VARIOS")

    @mock.patch("notaria.services.pdt_corrections_service.connection")
    def test_otorgante_ruc_and_renta(self, mock_connection):
        cursor = mock.MagicMock()
        cursor.rowcount = 1
        cursor.fetchone.return_value = ("000042",)
        mock_connection.cursor.return_value.__enter__.return_value = cursor

        svc = PdtCorrectionService()
        svc.apply(
            [
                {
                    "idContractor": "0000000001",
                    "categoryCorrect": CATEGORY_OTORGANTES,
                    "typeOfCorrection": TYPE_OTG_RUC,
                },
                {
                    "kardex": "K1",
                    "idContractor": "0000000001",
                    "categoryCorrect": CATEGORY_OTORGANTES,
                    "typeOfCorrection": TYPE_OTG_RENTA,
                },
            ]
        )
        executed = [c[0][0] for c in cursor.execute.call_args_list]
        self.assertTrue(any("UPDATE cliente2" in s for s in executed))
        self.assertTrue(any("INSERT INTO renta" in s for s in executed))

    @mock.patch("notaria.services.pdt_corrections_service.connection")
    def test_medio_documentos_voucher(self, mock_connection):
        cursor = mock.MagicMock()
        cursor.rowcount = 1
        mock_connection.cursor.return_value.__enter__.return_value = cursor

        PdtCorrectionService().apply(
            [
                {
                    "itemMp": "0001",
                    "categoryCorrect": CATEGORY_MEDIO_PAGO,
                    "typeOfCorrection": TYPE_MP_DOCUMENTOS,
                }
            ]
        )
        sql, params = cursor.execute.call_args[0]
        self.assertIn("UPDATE detallemediopago SET documentos", sql)
        self.assertEqual(params, ["VOUCHER", "0001"])

    @mock.patch("notaria.services.pdt_corrections_service.connection")
    def test_bien_relink(self, mock_connection):
        cursor = mock.MagicMock()
        cursor.rowcount = 2
        mock_connection.cursor.return_value.__enter__.return_value = cursor

        result = PdtCorrectionService().apply(
            [
                {
                    "kardex": "K1",
                    "tipoActo": "030",
                    "itemMp": "0099",
                    "categoryCorrect": CATEGORY_BIENES,
                    "typeOfCorrection": TYPE_BIEN_RELINK,
                }
            ]
        )
        self.assertIn("Se afectaron 1", result["errorDescription"])
