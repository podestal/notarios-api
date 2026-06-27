from django.test import SimpleTestCase

from sisgen.services.sync_status import (
    build_sisgen_sync_status,
    status_ui_from_document_status,
)


class SisgenSyncStatusTests(SimpleTestCase):
    def test_guardado_remote_but_estado_zero_means_resend(self):
        last = {
            "exists": True,
            "document_status": "GUARDADO",
            "created_at": "2026-05-01T10:00:00",
        }
        sync = build_sisgen_sync_status(0, last)
        self.assertTrue(sync["needs_resubmit"])
        self.assertTrue(sync["submission_stale"])
        self.assertEqual(sync["status_ui"], "pendiente_reenvio")
        self.assertTrue(sync["can_send"])
        self.assertEqual(sync["last_submission"]["remote_status_ui"], "guardado")

    def test_never_sent_estado_zero(self):
        sync = build_sisgen_sync_status(0, {"exists": False})
        self.assertFalse(sync["needs_resubmit"])
        self.assertEqual(sync["status_ui"], "pendiente")

    def test_estado_guardado_matches_remote(self):
        last = {"exists": True, "document_status": "GUARDADO"}
        sync = build_sisgen_sync_status(1, last)
        self.assertFalse(sync["needs_resubmit"])
        self.assertEqual(sync["status_ui"], "guardado")

    def test_internal_server_error_maps_to_fallido(self):
        self.assertEqual(
            status_ui_from_document_status("INTERNAL_SERVER_ERROR"),
            "fallido",
        )
