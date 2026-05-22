from django.test import SimpleTestCase

from uif.services.ro_validation_rules import matches_mysql_regexp, validation_code


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
