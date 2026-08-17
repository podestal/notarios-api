from datetime import date
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from rest_framework.exceptions import ValidationError

from taxes.services.control_interno import (
    BOLETA_COMPROBANTE_ID,
    FACTURA_COMPROBANTE_ID,
)
from taxes.services.resumen import create_resumen_for_single_recibo


class CreateResumenForSingleReciboTests(SimpleTestCase):
    @patch("taxes.services.resumen.create_resumen")
    @patch("taxes.services.resumen.Recibos")
    def test_boleta_builds_one_item_resumen(self, mock_recibos, mock_create):
        recibo = MagicMock(
            id_recibo=99,
            negocio_id=1,
            comprobante_id=BOLETA_COMPROBANTE_ID,
            tipo_recibo_modificado_id=None,
            fecha_emision=date(2026, 8, 15),
        )
        mock_recibos.objects.using.return_value.filter.return_value.first.return_value = (
            recibo
        )
        mock_create.return_value = ("resumen", [recibo])

        create_resumen_for_single_recibo(
            recibo_id=99,
            usuario_id=7,
            negocio_id=1,
            fecha_comunicacion=date(2026, 8, 16),
        )

        mock_create.assert_called_once_with(
            fecha_resumen=date(2026, 8, 16),
            fecha_emision=date(2026, 8, 15),
            comprobante_id=BOLETA_COMPROBANTE_ID,
            recibo_ids=[99],
            usuario_id=7,
            negocio_id=1,
        )

    @patch("taxes.services.resumen.Recibos")
    def test_factura_is_rejected(self, mock_recibos):
        recibo = MagicMock(
            id_recibo=1,
            comprobante_id=FACTURA_COMPROBANTE_ID,
            tipo_recibo_modificado_id=None,
            fecha_emision=date(2026, 8, 15),
        )
        mock_recibos.objects.using.return_value.filter.return_value.first.return_value = (
            recibo
        )
        with self.assertRaises(ValidationError):
            create_resumen_for_single_recibo(
                recibo_id=1, usuario_id=7, negocio_id=1
            )
