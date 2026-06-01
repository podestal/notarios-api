from django.test import SimpleTestCase

from sisgen.sisgen_acto_xml_rules import (
    codigo_uif_o_sunat_presente,
    doc_requires_cuantia_operacion_xml,
    doc_requires_medios_pago_xml,
    doc_requires_uif_sunat_xml,
    tiposdeacto_flag_on,
)


class SisgenActoXmlRulesTest(SimpleTestCase):
    def test_poder_sin_codigo_uif(self):
        doc = {
            "cod_ancert": "0604",
            "actouif": "",
            "actosunat": "",
            "mediospago": "0",
            "cuantia": "0",
        }
        self.assertFalse(doc_requires_uif_sunat_xml(doc))
        self.assertFalse(doc_requires_medios_pago_xml(doc))
        self.assertFalse(doc_requires_cuantia_operacion_xml(doc))

    def test_transferencia_con_codigo_uif(self):
        doc = {
            "cod_ancert": "0215",
            "actouif": "053",
            "mediospago": "S",
            "cuantia": "S",
        }
        self.assertTrue(codigo_uif_o_sunat_presente("053"))
        self.assertTrue(doc_requires_uif_sunat_xml(doc))
        self.assertTrue(doc_requires_medios_pago_xml(doc))
        self.assertTrue(doc_requires_cuantia_operacion_xml(doc))

    def test_flags_s_sin_codigo(self):
        doc = {"actouif": "", "mediospago": "S", "cuantia": "N"}
        self.assertTrue(doc_requires_uif_sunat_xml(doc))
        self.assertTrue(doc_requires_medios_pago_xml(doc))
        self.assertFalse(doc_requires_cuantia_operacion_xml(doc))

    def test_tiposdeacto_flag_on(self):
        self.assertTrue(tiposdeacto_flag_on("S"))
        self.assertFalse(tiposdeacto_flag_on("0"))
        self.assertFalse(tiposdeacto_flag_on("N"))
