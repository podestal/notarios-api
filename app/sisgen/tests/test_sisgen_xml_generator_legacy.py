from django.test import SimpleTestCase

from sisgen.services.xml_generator_service import SISGENXmlGenerator


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
