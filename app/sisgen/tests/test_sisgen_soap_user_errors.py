import os
from unittest import mock

from django.test import SimpleTestCase

from sisgen.services.sisgen_soap_response import (
    SISGEN_IT_CONTACT_NOTE,
    build_soap_failure_entries,
    extract_submission_errors,
    format_soap_return_message,
    parse_set_documentos_response,
    soap_response_is_ok,
)

INTERNAL_ERROR_XML = """<?xml version="1.0"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <ns2:setDocumentosNotarialesResponse xmlns:ns2="http://cnlws.notarios.org.pe/">
      <return>
        <message>cvc-complex-type.2.4.a: Invalid content was found starting with element 'Cargo'.
org.xml.sax.SAXParseException; lineNumber: 123</message>
        <status>INTERNAL_SERVER_ERROR</status>
      </return>
    </ns2:setDocumentosNotarialesResponse>
  </soap:Body>
</soap:Envelope>"""


class SisgenSoapUserErrorsTests(SimpleTestCase):
    def test_parse_internal_server_error_not_ok(self):
        parsed = parse_set_documentos_response(INTERNAL_ERROR_XML)
        self.assertFalse(soap_response_is_ok(parsed))
        self.assertEqual(parsed["return_status"], "INTERNAL_SERVER_ERROR")
        self.assertIn("Cargo", parsed["return_message"])

    def test_format_soap_return_message_first_line_only(self):
        raw = "line one error\norg.xml.sax.SAXParseException; line 123"
        self.assertEqual(format_soap_return_message(raw), "line one error")

    def test_build_soap_failure_entries_structural_error_is_system_with_it_note(self):
        parsed = parse_set_documentos_response(INTERNAL_ERROR_XML)
        entries = build_soap_failure_entries(
            parsed=parsed,
            batch_documents=[{"kardex": "A41-2026", "idkardex": "99"}],
            batch_index=1,
            http_status=200,
        )
        self.assertEqual(len(entries), 1)
        row = entries[0]
        self.assertEqual(row["kardex"], "A41-2026")
        self.assertEqual(row["estado"], "INTERNAL_SERVER_ERROR")
        self.assertEqual(row["origen"], "sistema")
        self.assertIn("Cargo", row["mensaje_usuario"])
        self.assertIn("Cargo", row["mensaje_tecnico"])
        self.assertEqual(row["nota_contacto_it"], SISGEN_IT_CONTACT_NOTE)

    def test_build_soap_failure_entries_pins_culprit_from_location(self):
        parsed = {
            "return_status": "INTERNAL_SERVER_ERROR",
            "return_message": (
                "cvc-enumeration-valid: Value '01' is not facet-valid with respect to enumeration "
                "'[08, 09, 10, 12, 13]'. It must be a value from the enumeration. En la Fila: 55 Columna: 45"
            ),
        }
        location = {
            "elemento": "TipoDocIdentidad",
            "valor": "01",
            "persona": "AMI & RAI NETWORK SOLUTIONS E.I.R.L.",
            "persona_tipo": "J",
            "kardex": "K119-2026",
        }
        entries = build_soap_failure_entries(
            parsed=parsed,
            batch_documents=[{"kardex": "K118-2026"}, {"kardex": "K119-2026"}],
            batch_index=1,
            location=location,
        )
        by_kardex = {e["kardex"]: e for e in entries}
        culprit = by_kardex["K119-2026"]
        self.assertEqual(culprit["titulo"], "Valor no permitido en Tipo de documento")
        self.assertIn("persona jurídica", culprit["mensaje_usuario"])
        self.assertEqual(culprit["campos"][0]["campo"], "Tipo de documento")
        self.assertEqual(culprit["campos"][0]["referencia"], "AMI & RAI NETWORK SOLUTIONS E.I.R.L.")
        self.assertNotIn("nota_contacto_it", culprit)
        other = by_kardex["K118-2026"]
        self.assertEqual(other["codigo"], "LOTE")
        self.assertIn("K119-2026", other["que_hacer"])

    def test_extract_submission_errors_explains_legacy_soap_failure_payload(self):
        payload = {
            "soap_failure": True,
            "user_facing": {
                "mensaje_usuario": "A90-2026: SISGEN rechazó el envío (INTERNAL_SERVER_ERROR).",
                "nota_contacto_it": SISGEN_IT_CONTACT_NOTE,
            },
        }
        errors = extract_submission_errors(
            payload,
            soap_return_message='For input string: "-" En la Fila: 146 Columna: 39',
            document_status="INTERNAL_SERVER_ERROR",
            soap_return_status="INTERNAL_SERVER_ERROR",
            kardex="A90-2026",
        )
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["titulo"], "Valor numérico inválido")
        self.assertIn("«-»", errors[0]["mensaje_usuario"])
        self.assertEqual(errors[0]["origen"], "dato")

    def test_extract_submission_errors_backfills_kardex_link_on_stored_campos(self):
        payload = {
            "soap_failure": True,
            "user_facing": {
                "titulo": "Valor no permitido en Tipo de documento",
                "campos": [{"seccion": "Contratantes", "campo": "Tipo de documento"}],
            },
        }
        errors = extract_submission_errors(
            payload,
            document_status="INTERNAL_SERVER_ERROR",
            soap_return_status="INTERNAL_SERVER_ERROR",
            kardex="K119-2026",
        )
        self.assertEqual(errors[0]["campos"][0]["accion"], {"tipo": "ir_kardex", "seccion": "contratantes"})


class SisgenXmlPersistPolicyTests(SimpleTestCase):
    def test_development_always_persists_xml(self):
        from sisgen.services import sisgen_soap_response as mod

        with mock.patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=False):
            self.assertTrue(
                mod.should_persist_sisgen_xml(
                    {"return_status": "OK", "summary": {"soap_level_ok": True}, "documents": []},
                    http_status=200,
                )
            )

    def test_local_skips_xml_on_success(self):
        from sisgen.services import sisgen_soap_response as mod

        with mock.patch.dict(os.environ, {"ENVIRONMENT": "local", "DJANGO_SETTINGS_MODULE": "notarios.settings.dev"}, clear=False):
            self.assertFalse(
                mod.should_persist_sisgen_xml(
                    {"return_status": "OK", "summary": {"soap_level_ok": True}, "documents": [
                        {"doc_status": "GUARDADO", "errors": [], "has_errors": False}
                    ]},
                    http_status=200,
                )
            )

    def test_local_persists_xml_on_soap_error(self):
        from sisgen.services import sisgen_soap_response as mod

        with mock.patch.dict(os.environ, {"ENVIRONMENT": "localf"}, clear=False):
            self.assertTrue(
                mod.should_persist_sisgen_xml(
                    {"return_status": "INTERNAL_SERVER_ERROR", "summary": {"soap_level_ok": False}},
                    http_status=200,
                )
            )

    def test_test_env_persists_xml_on_document_errors(self):
        from sisgen.services import sisgen_soap_response as mod

        with mock.patch.dict(os.environ, {"ENVIRONMENT": "testing"}, clear=False):
            self.assertTrue(
                mod.should_persist_sisgen_xml(
                    {
                        "return_status": "OK",
                        "summary": {"soap_level_ok": True},
                        "documents": [{"doc_status": "FALLIDO", "errors": ["RO04"], "has_errors": True}],
                    },
                    http_status=200,
                )
            )
