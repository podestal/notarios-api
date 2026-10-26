from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from ducumentation.document_audit import kardex_from_proyecto_filename, log_digitacion_document


class ProyectoFilenameTests(SimpleTestCase):
    def test_extracts_kardex_from_proyecto_name(self):
        self.assertEqual(
            kardex_from_proyecto_filename("__PROY__K148-2026.docx"),
            "K148-2026",
        )
        self.assertEqual(
            kardex_from_proyecto_filename("documentos/__PROY__KAR2315-2025.docx"),
            "KAR2315-2025",
        )

    def test_unknown_filename_is_empty(self):
        self.assertEqual(kardex_from_proyecto_filename("not-a-project.docx"), "")


class DigitacionDocumentLogTests(SimpleTestCase):
    @patch("audit.services.enqueue_manual_event")
    @patch("ducumentation.models.DocumentosLogs.objects.create")
    def test_generate_writes_document_log_and_kardex_event(self, create_log, enqueue):
        user = SimpleNamespace(is_authenticated=True, idusuario=26, username="galaxia69")
        log_digitacion_document(
            kardex="K148-2026",
            user=user,
            action="G",
            source="/docs/documentos/open-template/",
            filename="__PROY__K148-2026.docx",
        )
        create_log.assert_called_once()
        enqueue.assert_called_once()
        kwargs = enqueue.call_args.kwargs
        self.assertEqual(kwargs["table_name"], "documento")
        self.assertEqual(kwargs["action"], "create")
        self.assertEqual(kwargs["user"], user)
        self.assertEqual(kwargs["changes"]["Acción"]["new"], "Generó el documento")

    @patch("audit.services.enqueue_manual_event")
    @patch("ducumentation.models.DocumentosLogs.objects.create")
    def test_save_is_logged_as_update(self, create_log, enqueue):
        user = SimpleNamespace(is_authenticated=True, idusuario=26, username="galaxia69")
        log_digitacion_document(
            kardex="K148-2026",
            user=user,
            action="S",
            source="/docs/save-doc/",
            filename="__PROY__K148-2026.docx",
        )
        kwargs = enqueue.call_args.kwargs
        self.assertEqual(kwargs["action"], "update")
        self.assertEqual(kwargs["changes"]["Acción"]["new"], "Guardó el documento")

    @patch("audit.services.enqueue_manual_event")
    @patch("ducumentation.models.DocumentosLogs.objects.create")
    def test_open_does_not_write_kardex_historial(self, create_log, enqueue):
        user = SimpleNamespace(is_authenticated=True, idusuario=26, username="galaxia69")
        log_digitacion_document(
            kardex="K148-2026",
            user=user,
            action="O",
            source="/docs/documentos/open-document/",
        )
        create_log.assert_called_once()
        enqueue.assert_not_called()
