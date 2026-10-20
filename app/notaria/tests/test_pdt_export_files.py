from django.test import SimpleTestCase

from notaria.services.pdt_file_service import (
    BienesFormatter,
    FormularioFormatter,
    LibrosFormatter,
    MediosPagoFormatter,
    OtorgantesFormatter,
    _otg_preguntas,
    format_bie_line,
    format_for_line,
    format_lib_line,
    format_mpa_line,
    format_otg_line,
)


def _bie(**overrides):
    row = {
        "tipo_kardex_pdt": "1",
        "numescritura": "12",
        "fecha_escritura_fmt": "15/04/2026",
        "secuencial_acto": 3,
        "secuencial_bien": 2,
        "tipo_bien": "B",
        "codigo_bien": "04",
        "opcion_psm": "",
        "numero_psm": "",
        "numero_serie": "",
        "origen_bien": "1",
        "codigo_ubicacion": "150101",
        "fecha_adquisicion": "01/01/2020",
        "descripcion_otros": "",
    }
    row.update(overrides)
    return row


def _otg(**overrides):
    row = {
        "tipo_kardex_pdt": "1",
        "numescritura": "12",
        "fecha_escritura_fmt": "15/04/2026",
        "secuencial_acto": 3,
        "secuencial_bien": "",
        "secuencial_otorgante": 1,
        "tipo_documento": "01",
        "numero_documento": "12345678",
        "tipo_otorgante": "01",
        "tipo_persona": "1",
        "ubigeo": "150101",
        "porcentaje": "50.00",
        "razon_social": "",
        "apellido_paterno": "PEREZ",
        "apellido_materno": "LOPEZ",
        "primer_nombre": "JUAN",
        "segundo_nombre": "",
        "pregunta1": "0",
        "pregunta2": "0",
        "pregunta3": "1",
    }
    row.update(overrides)
    return row


def _mpa(**overrides):
    row = {
        "tipo_kardex_pdt": "1",
        "numescritura": "12",
        "secuencial_acto": 3,
        "medio_pago": "001",
        "moneda": "2",
        "monto": "15000.00",
        "fecha_pago": "15/04/2026",
        "documentos": "OP-1",
        "entidad_financiera": "02",
    }
    row.update(overrides)
    return row


def _form(**overrides):
    row = {
        "idtipkar": 1,
        "numescritura": "12",
        "secuencial_acto": 3,
        "secuencial_otorgante": 1,
        "tipo_otorgante": "01",
        "numero_formulario": "1234567890",
        "pago_cuenta": "100.50",
    }
    row.update(overrides)
    return row


def _lib(**overrides):
    row = {
        "numero_libro": "15",
        "fecha_ingreso": "15/04/2026",
        "id_tipo_libro": "3",
        "folio": "8",
        "tipo_persona": "1",
        "ruc": "20123456789",
        "apellido_paterno": "Perez",
        "apellido_materno": "Lopez",
        "primer_nombre": "Juan",
        "segundo_nombre": "",
        "razon_social": "",
    }
    row.update(overrides)
    return row


class PdtBieLineTests(SimpleTestCase):
    def test_bienfilepdt_has_fourteen_fields(self):
        self.assertEqual(len(format_bie_line(_bie()).split("|")), 14)

    def test_php_padding_matches_generate_file_bien(self):
        parts = format_bie_line(_bie()).split("|")
        self.assertEqual(parts[0], "1")
        self.assertEqual(parts[1], "12   ")
        self.assertEqual(parts[2], "15/04/2026")
        self.assertEqual(parts[3], "3    ")
        self.assertEqual(parts[4], "2    ")
        self.assertEqual(parts[5], "B")
        self.assertEqual(parts[6], "04")
        self.assertEqual(parts[10], "1")
        self.assertEqual(parts[11], "150101")
        self.assertEqual(len(parts[13]), 30)


class PdtOtgLineTests(SimpleTestCase):
    def test_otorgantefilepdt_has_twenty_fields(self):
        self.assertEqual(len(format_otg_line(_otg()).split("|")), 20)

    def test_php_padding_matches_generate_file_otorgante(self):
        parts = format_otg_line(_otg()).split("|")
        self.assertEqual(parts[0], "1")
        self.assertEqual(parts[1], "   12")
        self.assertEqual(parts[2], "15/04/2026")
        self.assertEqual(parts[3], "3    ")
        self.assertEqual(parts[4], "     ")
        self.assertEqual(parts[5], "1    ")
        self.assertEqual(parts[6], "01")
        self.assertEqual(parts[7], "12345678    ")
        self.assertEqual(parts[9], "1")
        self.assertEqual(parts[11], "50.00 ")
        self.assertEqual(len(parts[12]), 40)
        self.assertEqual(parts[17], "0")
        self.assertEqual(parts[18], "0")
        self.assertEqual(parts[19], "1")

    def test_renta_questions_php_rules(self):
        p1, p2, p3, id_renta = _otg_preguntas(
            {"actosunat": "01"}, tipper="N", parte=1, renta=None, fecha_adq=""
        )
        self.assertEqual((p1, p2, p3, id_renta), ("0", "0", "1", 0))

        p1, p2, p3, id_renta = _otg_preguntas(
            {"actosunat": "04"}, tipper="N", parte="1", renta=None, fecha_adq=""
        )
        self.assertEqual((p1, p2, p3), ("0", "0", "1"))

        p1, p2, p3, id_renta = _otg_preguntas(
            {"actosunat": "04"},
            tipper="N",
            parte="1",
            renta={"pregu1": "1", "pregu2": "0", "pregu3": "1", "idrenta": 9},
            fecha_adq="01/01/2020",
        )
        self.assertEqual((p1, p2, p3, id_renta), ("1", "0", "1", 9))

        p1, p2, p3, id_renta = _otg_preguntas(
            {"actosunat": "03"},
            tipper="N",
            parte="1",
            renta={"pregu1": "1", "idrenta": 4},
            fecha_adq="01/01/2020",
        )
        self.assertEqual((p1, p2, p3, id_renta), ("", "", "", 0))


class PdtMpaLineTests(SimpleTestCase):
    def test_mediofilepdt_has_nine_fields(self):
        self.assertEqual(len(format_mpa_line(_mpa()).split("|")), 9)

    def test_php_padding_matches_generate_file_medio(self):
        parts = format_mpa_line(_mpa()).split("|")
        self.assertEqual(parts[0], "1")
        self.assertEqual(parts[1], "   12")
        self.assertEqual(parts[2], "3    ")
        self.assertEqual(parts[3], "001")
        self.assertEqual(parts[4], "2")
        self.assertTrue(parts[5].startswith("15000.00"))
        self.assertEqual(len(parts[5]), 15)
        self.assertEqual(parts[6], "15/04/2026")
        self.assertEqual(parts[8], "02")


class PdtForLineTests(SimpleTestCase):
    def test_formfilepdt_has_seven_fields(self):
        self.assertEqual(len(format_for_line(_form()).split("|")), 7)

    def test_uses_raw_idtipkar_not_pdt_map(self):
        parts = format_for_line(_form(idtipkar=3)).split("|")
        self.assertEqual(parts[0], "3")
        self.assertEqual(parts[1], "   12")
        self.assertEqual(parts[2], "3    ")
        self.assertEqual(parts[5], "1234567890")
        self.assertTrue(parts[6].startswith("100.50"))


class PdtLibLineTests(SimpleTestCase):
    def test_libfilepdt_has_eleven_fields(self):
        self.assertEqual(len(format_lib_line(_lib()).split("|")), 11)

    def test_php_padding_and_uppercase(self):
        parts = format_lib_line(_lib()).split("|")
        self.assertEqual(parts[0], "        15")
        self.assertEqual(parts[1], "15/04/2026")
        self.assertEqual(parts[2], " 3")
        self.assertEqual(parts[3], "         8")
        self.assertEqual(parts[4], "1")
        self.assertEqual(parts[5], "20123456789")
        self.assertTrue(parts[6].startswith("PEREZ"))
        self.assertEqual(len(parts[6]), 15)
        self.assertEqual(len(parts[10]), 40)


class PdtExportExtensionsTests(SimpleTestCase):
    def test_php_filename_extensions(self):
        self.assertEqual(BienesFormatter("01/04/2026", "30/04/2026", 1).extension, "Bie")
        self.assertEqual(OtorgantesFormatter("01/04/2026", "30/04/2026", 1).extension, "Otg")
        self.assertEqual(MediosPagoFormatter("01/04/2026", "30/04/2026", 1).extension, "Mpa")
        self.assertEqual(FormularioFormatter("01/04/2026", "30/04/2026", 1).extension, "For")
        self.assertEqual(LibrosFormatter("01/04/2026", "30/04/2026").extension, "lib")
