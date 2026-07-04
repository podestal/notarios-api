from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from sisgen.services.soap_client_service import SoapClientService


class SoapClientServiceTests(SimpleTestCase):
    def test_send_documents_uses_session_post(self):
        session = MagicMock()
        response = MagicMock()
        session.post.return_value = response
        client = SoapClientService(session=session)

        result = client.send_documents("<xml/>")

        self.assertIs(result, response)
        session.post.assert_called_once()
        client.close()

    def test_owned_session_is_closed(self):
        with patch("sisgen.services.soap_client_service.requests.Session") as mock_session_cls:
            session = MagicMock()
            mock_session_cls.return_value = session
            client = SoapClientService()

            client.close()

            session.close.assert_called_once()

    def test_injected_session_is_not_closed(self):
        session = MagicMock()
        client = SoapClientService(session=session)

        client.close()

        session.close.assert_not_called()
