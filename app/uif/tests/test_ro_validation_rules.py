from decimal import Decimal

from django.test import SimpleTestCase

from uif.services.ro_validation_rules import (
    group_detalle_medio_importe_sums,
    matches_mysql_regexp,
    medio_pago_uif_validation_value,
    monto_tipo_fondo_validation_value,
    oportunidad_pago_validation_value,
    validation_code,
)


class RegexpRuleTests(SimpleTestCase):
    def test_monto_operacion_pattern_accepts_valid(self):
        pattern = r"^[^0]{1}[0-9]*[.][0-9]{2}$"
        self.assertTrue(matches_mysql_regexp("150000.00", pattern))
        self.assertEqual(validation_code("150000.00", pattern), 0)

    def test_monto_operacion_pattern_rejects_zero(self):
        pattern = r"^[^0]{1}[0-9]*[.][0-9]{2}$"
        self.assertFalse(matches_mysql_regexp("0.00", pattern))
        self.assertEqual(validation_code("0.00", pattern), 1)

    def test_forma_pago_codigo_c(self):
        pattern = "C|P|S"
        self.assertTrue(matches_mysql_regexp("C", pattern))
        self.assertFalse(matches_mysql_regexp("X", pattern))

    def test_oportunidad_vacio_catalog_id_maps_to_v_for_validation(self):
        self.assertEqual(oportunidad_pago_validation_value(""), "V")
        self.assertEqual(oportunidad_pago_validation_value(10), "V")
        self.assertEqual(oportunidad_pago_validation_value("10"), "V")
        self.assertEqual(oportunidad_pago_validation_value(1), "01")
        self.assertEqual(validation_code(oportunidad_pago_validation_value(10), "V"), 0)

    def test_medio_pago_empty_uif_maps_to_v_for_validation(self):
        self.assertEqual(medio_pago_uif_validation_value(""), "V")
        self.assertEqual(medio_pago_uif_validation_value(None), "V")
        self.assertEqual(medio_pago_uif_validation_value("16"), "16")
        self.assertEqual(validation_code(medio_pago_uif_validation_value(""), "V"), 0)

    def test_monto_tipo_fondo_null_sum_maps_to_v_for_validation(self):
        self.assertEqual(
            monto_tipo_fondo_validation_value(None, has_importemp=False),
            "V",
        )
        self.assertEqual(
            monto_tipo_fondo_validation_value(
                Decimal("137000"), has_importemp=True
            ),
            "137000.00",
        )
        self.assertEqual(validation_code("V", "V"), 0)

    def test_group_detalle_medio_importe_sums_matches_php_group_by(self):
        rows = [
            type("R", (), {"codmepag": 1, "tipacto": "119", "importemp": None})(),
            type("R", (), {"codmepag": 1, "tipacto": "119", "importemp": None})(),
            type("R", (), {"codmepag": 2, "tipacto": "119", "importemp": 68500})(),
        ]
        grouped = group_detalle_medio_importe_sums(rows)
        self.assertEqual(grouped[(1, "119")]["has_importemp"], False)
        self.assertEqual(grouped[(2, "119")]["total"], Decimal("68500"))
