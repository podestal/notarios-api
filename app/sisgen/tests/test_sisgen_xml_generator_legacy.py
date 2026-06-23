from django.test import SimpleTestCase

from sisgen.services.xml_generator_service import SISGENXmlGenerator
from sisgen.sisgen_acto_xml_rules import doc_permite_objetos_xml


class SisgenXmlGeneratorLegacyTest(SimpleTestCase):
    def setUp(self):
        self.generator = SISGENXmlGenerator()

    def test_medios_pagos_wrapper_when_uif_act_without_rows(self):
        doc = {"cod_ancert": "0215"}
        xml = self.generator._medios_pagos_xml_for_doc(
            doc,
            pat_row=None,
            mp_rows=[],
            tipo_moneda_doc="01",
            total_monto=137000.0,
        )
        self.assertIn("<MediosPagos>", xml)
        self.assertIn("</MediosPagos>", xml)
        self.assertNotIn("<MediosPago>", xml)

    def test_medios_pagos_omitted_for_acto_excluido(self):
        doc = {"cod_ancert": "0604"}
        xml = self.generator._medios_pagos_xml_for_doc(
            doc,
            pat_row=None,
            mp_rows=[],
            tipo_moneda_doc="01",
            total_monto=0.0,
        )
        self.assertEqual(xml, "")

    def test_poder_sin_bienes_cuando_acto_0604(self):
        """EC05: 0604 no carga bienes aunque el kardex tenga detallevehicular."""
        doc = {"cod_ancert": "0604", "codactos": "067", "kardex": "K17-2026"}
        self.assertFalse(doc_permite_objetos_xml(doc))
        bienes = (
            self.generator._load_bienes_for_doc(doc)
            if doc_permite_objetos_xml(doc)
            else {
                "predios": [],
                "vehiculos_bienes": [],
                "vehiculos_detalle": [],
                "otros": [],
            }
        )
        self.assertEqual(bienes["vehiculos_detalle"], [])
        self.assertEqual(bienes["vehiculos_bienes"], [])

    def test_rol_n_va_a_no_intervinientes_no_intervenciones(self):
        participants = [
            {
                "idcliente": "8428",
                "uif": "O",
                "idcondicion": "1",
                "idcontratante": "1",
            },
            {
                "idcliente": "8402",
                "uif": "N",
                "idcontratante": "2",
            },
        ]
        xml = self.generator._no_intervinientes_xml(participants, {"8428"})
        self.assertIn("<TipoComparecencia>2</TipoComparecencia>", xml)
        self.assertIn("<ClaseIntervencion>3</ClaseIntervencion>", xml)
        self.assertIn("<IdMaestro>8402</IdMaestro>", xml)

    def test_intervencion_roles_solo_o_b_g(self):
        self.assertEqual(self.generator.INTERVENCION_ROLES, ("O", "B", "G"))
        self.assertEqual(self.generator._participant_rol_representante({"uif": "N"}), "N")
        self.assertEqual(
            self.generator._participant_rol_representante({"repre": "B", "uif": "O"}),
            "B",
        )
