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

    def test_build_soap_failure_entries_include_it_note(self):
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
        self.assertIn("A41-2026", row["mensaje_usuario"])
        self.assertIn("Cargo", row["mensaje_tecnico"])
        self.assertEqual(row["nota_contacto_it"], SISGEN_IT_CONTACT_NOTE)

    def test_extract_submission_errors_reads_soap_failure_payload(self):
        payload = {
            "soap_failure": True,
            "user_facing": {
                "mensaje_usuario": "A41-2026: SISGEN rechazó el envío (INTERNAL_SERVER_ERROR). AnoFabricacion",
                "nota_contacto_it": SISGEN_IT_CONTACT_NOTE,
            },
            "nota_contacto_it": SISGEN_IT_CONTACT_NOTE,
        }
        errors = extract_submission_errors(
            payload,
            soap_return_message="AnoFabricacion '-' is not valid",
            document_status="INTERNAL_SERVER_ERROR",
            soap_return_status="INTERNAL_SERVER_ERROR",
        )
        self.assertGreaterEqual(len(errors), 1)
        self.assertIn("A41-2026", errors[0])
        self.assertIn(SISGEN_IT_CONTACT_NOTE, errors[-1])
