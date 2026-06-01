from django.test import SimpleTestCase

from sisgen.sisgen_document_rules import (
    juridica_requiere_formato_ruc,
    validar_documento_juridica,
)


class SisgenDocumentRulesTest(SimpleTestCase):
    def test_tipo_10_sin_numero_ok_constitucion(self):
        err, msg, tipo = validar_documento_juridica("10", "", "1")
        self.assertEqual(err, 0)
        self.assertEqual(msg, "")
        self.assertEqual(tipo, "10")
        self.assertFalse(juridica_requiere_formato_ruc(tipo))

    def test_tipo_15_sin_numero_ok(self):
        err, msg, _ = validar_documento_juridica("15", "", "1")
        self.assertEqual(err, 0)
        self.assertEqual(msg, "")

    def test_tipo_08_sin_numero_error(self):
        err, msg, _ = validar_documento_juridica("08", "", "1")
        self.assertEqual(err, 1)
        self.assertEqual(msg, "Falta el numero de documento")

    def test_once_digitos_asigna_08(self):
        err, msg, tipo = validar_documento_juridica("10", "20123456789", "1")
        self.assertEqual(err, 0)
        self.assertEqual(tipo, "08")

    def test_tipo_10_con_doc_corto_error(self):
        err, msg, _ = validar_documento_juridica("10", "ABC", "1")
        self.assertEqual(err, 1)
        self.assertEqual(msg, "Tipo de documento no corresponde")

    def test_instrumento_2_sin_validacion(self):
        err, msg, _ = validar_documento_juridica("", "", "2")
        self.assertEqual(err, 0)
