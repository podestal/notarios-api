from django.test import SimpleTestCase

from sisgen.sisgen_acto_xml_rules import (
    ACTOS_NO_UIF_SUNAT,
    ACTOS_SIN_OBJETOS_XML,
    cod_ancert_requires_uif_sunat_xml,
    cod_ancert_permite_objetos_xml,
    codigo_uif_o_sunat_presente,
    doc_permite_objetos_xml,
    doc_requires_cuantia_operacion_xml,
    doc_requires_medios_pago_xml,
    doc_requires_uif_sunat_xml,
    tiposdeacto_flag_on,
)


class SisgenActoXmlRulesTest(SimpleTestCase):
    def test_poder_excluido_validar_uif_sunat(self):
        doc = {
            "cod_ancert": "0604",
            "actouif": "",
            "actosunat": "",
            "mediospago": "S",
            "cuantia": "S",
        }
        self.assertIn("0604", ACTOS_NO_UIF_SUNAT)
        self.assertIn("0604", ACTOS_SIN_OBJETOS_XML)
        self.assertFalse(cod_ancert_requires_uif_sunat_xml("0604"))
        self.assertFalse(cod_ancert_permite_objetos_xml("0604"))
        self.assertFalse(doc_permite_objetos_xml(doc))
        self.assertFalse(doc_requires_uif_sunat_xml(doc))
        self.assertFalse(doc_requires_medios_pago_xml(doc))
        self.assertFalse(doc_requires_cuantia_operacion_xml(doc))

    def test_transferencia_0215_siempre_uif(self):
        doc = {
            "cod_ancert": "0215",
            "actouif": "053",
            "mediospago": "N",
            "cuantia": "S",
        }
        self.assertTrue(codigo_uif_o_sunat_presente("053"))
        self.assertTrue(doc_requires_uif_sunat_xml(doc))
        self.assertTrue(doc_requires_medios_pago_xml(doc))
        self.assertTrue(doc_requires_cuantia_operacion_xml(doc))

    def test_sin_cod_ancert_no_uif(self):
        doc = {"actouif": "", "mediospago": "S", "cuantia": "N"}
        self.assertFalse(doc_requires_uif_sunat_xml(doc))
        self.assertFalse(doc_requires_medios_pago_xml(doc))
        self.assertFalse(doc_requires_cuantia_operacion_xml(doc))

    def test_tiposdeacto_flag_on(self):
        self.assertTrue(tiposdeacto_flag_on("S"))
        self.assertFalse(tiposdeacto_flag_on("0"))
        self.assertFalse(tiposdeacto_flag_on("N"))
