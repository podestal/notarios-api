import base64

from django.test import SimpleTestCase

from taxes.services.xml.enviar_resumen import _parse_status_response


def _status_soap(*, status_code: str, content: str = "") -> bytes:
    content_xml = f"<content>{content}</content>" if content else "<content/>"
    return f"""<?xml version="1.0"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <statusCode>{status_code}</statusCode>
    {content_xml}
  </soap:Body>
</soap:Envelope>
""".encode()


class ParseStatusResponseTests(SimpleTestCase):
    def test_status_98_is_pending(self):
        parsed = _parse_status_response(_status_soap(status_code="98"))
        self.assertTrue(parsed["en_proceso"])
        self.assertNotIn("cdr_zip_bytes", parsed)

    def test_valid_zip_content_is_returned(self):
        # Minimal ZIP local-file header ("PK\x03\x04...")
        zip_bytes = b"PK\x03\x04" + b"\x00" * 20
        content = base64.b64encode(zip_bytes).decode()
        parsed = _parse_status_response(
            _status_soap(status_code="0", content=content)
        )
        self.assertFalse(parsed["en_proceso"])
        self.assertEqual(parsed["cdr_zip_bytes"], zip_bytes)

    def test_non_zip_content_does_not_crash(self):
        content = base64.b64encode(b"not-a-zip-at-all").decode()
        parsed = _parse_status_response(
            _status_soap(status_code="0", content=content)
        )
        self.assertTrue(parsed["en_proceso"])
        self.assertNotIn("cdr_zip_bytes", parsed)
        self.assertIn("CDR ZIP", parsed["msj_sunat"])
