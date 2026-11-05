from django.test import SimpleTestCase

from compliance.services.contratantes_progress import local_contratante_issues


def _issues(**overrides):
    base = dict(
        idcontratante="1",
        label="Perez Juan",
        tipper="N",
        prinom="Juan",
        apepat="Perez",
        razonsocial="",
        nombre="Perez Juan",
        numdoc="12345678",
        idtipdoc=1,
        idubigeo="150101",
        ubigeo_ok=True,
        has_condicion=True,
        has_cliente=True,
    )
    base.update(overrides)
    return local_contratante_issues(**base)


class LocalContratanteIssuesTests(SimpleTestCase):
    def test_complete_natural_person_has_no_issues(self):
        self.assertEqual(_issues(), [])

    def test_missing_name_ubigeo_and_condicion(self):
        fields = {item["field"] for item in _issues(
            prinom="",
            apepat="",
            ubigeo_ok=False,
            idubigeo="",
            has_condicion=False,
        )}
        self.assertIn("nombre", fields)
        self.assertIn("ubigeo", fields)
        self.assertIn("condicion", fields)

    def test_incorrect_dni(self):
        texts = [item["text"] for item in _issues(numdoc="12")]
        self.assertTrue(any("DNI no es correcto" in text for text in texts))

    def test_juridica_without_razon_social(self):
        texts = [item["text"] for item in _issues(
            tipper="J",
            label="Contratante 2",
            prinom="",
            apepat="",
            razonsocial="",
            numdoc="20123456789",
            idtipdoc=8,
        )]
        self.assertTrue(any("razón social" in text for text in texts))

    def test_bad_display_name(self):
        texts = [item["text"] for item in _issues(nombre="12")]
        self.assertTrue(any("no es correcto" in text for text in texts))
