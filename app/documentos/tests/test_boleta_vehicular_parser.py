from pathlib import Path

from django.test import SimpleTestCase, TestCase, override_settings

from documentos.services.boleta_vehicular_parser import parse_boleta_vehicular_text
from documentos.services.pdf_text import extract_pdf_text
from documentos.services.upload import submit_documento_vehicular

FIXTURE = (
    Path(__file__).resolve().parent.parent / "fixtures" / "boleta_informativa_vehicular.pdf"
)


class BoletaVehicularParserTests(SimpleTestCase):
    def test_parses_sample_boleta_fields(self):
        text = extract_pdf_text(FIXTURE)
        parsed = parse_boleta_vehicular_text(text)
        veh = parsed["vehiculo"]
        prop = parsed["propietario"]
        self.assertEqual(veh["placa"], "V5W564")
        self.assertEqual(veh["marca"], "DAEWOO")
        self.assertEqual(veh["modelo"], "TICO")
        self.assertEqual(veh["carroceria"], "SEDAN")
        self.assertEqual(veh["anio_fabricacion"], "1995")
        self.assertEqual(veh["numero_serie"], "KLY3S11BDSC260706")
        self.assertEqual(veh["numero_motor"], "F8C312031")
        self.assertEqual(veh["combustible"], "GASOLINA")
        self.assertEqual(veh["color_1"], "AMARILLO DORADO")
        self.assertEqual(veh["partida"], "60032609")
        self.assertEqual(veh["condicion"], "USADO")
        self.assertEqual(veh["fecha_inscripcion"], "29-05-2014")
        self.assertEqual(veh["tipo_uso"], "Taxis y Colectivos (Categoria M1)")
        self.assertEqual(veh["categoria"], "")
        self.assertEqual(veh["numero_ruedas"], "4")
        self.assertEqual(veh["numero_cilindros"], "3")
        self.assertEqual(veh["numero_ejes"], "2")
        self.assertEqual(veh["cilindrada"], "796 L")
        self.assertEqual(prop["nombre"], "TAIRO TAIRO MARIA DEL CARMEN")
        self.assertEqual(prop["dni"], "72750026")
        self.assertEqual(parsed["meta"].get("oficina"), "AREQUIPA")


@override_settings(DOCUMENTOS_NOTARIA_ROOT="/tmp/documentos_notaria_test")
class DocumentoVehicularUploadTests(TestCase):
    def test_submit_stores_file_and_parsed_json(self):
        with FIXTURE.open("rb") as handle:
            doc = submit_documento_vehicular(
                uploaded_file=handle,
                original_filename="Boleta_Informativa.pdf",
            )
        self.assertEqual(doc.status, "parsed")
        self.assertEqual(doc.placa, "V5W564")
        self.assertEqual(doc.partida, "60032609")
        self.assertTrue(doc.relative_path.startswith("vehiculares/"))
        self.assertEqual(doc.parsed["vehiculo"]["marca"], "DAEWOO")
        abs_path = Path("/tmp/documentos_notaria_test") / doc.relative_path
        self.assertTrue(abs_path.is_file())
