from django.test import SimpleTestCase
from django.utils import timezone

from taxes.models import SunatOutbox
from taxes.services.sunat_errors import (
    build_sunat_user_payload,
    is_transient_sunat_message,
    recibo_needs_sunat_retry,
)
from taxes.services.sunat_retry_schedule import compute_next_retry_at


class SunatErrorClassificationTests(SimpleTestCase):
    def test_connection_error_is_transient(self):
        self.assertTrue(
            is_transient_sunat_message("Error de conexión con SUNAT: timeout")
        )

    def test_business_rejection_is_not_transient(self):
        self.assertFalse(
            recibo_needs_sunat_retry(
                {
                    "cod_sunat": "2335",
                    "msj_sunat": "SUNAT rechazó el comprobante",
                    "enviada_sunat": True,
                    "aceptada_sunat": False,
                }
            )
        )

    def test_build_sunat_down_payload_with_outbox(self):
        outbox = SunatOutbox(
            kind=SunatOutbox.Kind.RECIBO,
            target_id=1,
            status=SunatOutbox.Status.PENDING,
            next_retry_at=timezone.now(),
            attempt_count=2,
        )
        payload = build_sunat_user_payload(
            sunat={"enviada_sunat": False, "aceptada_sunat": False},
            outbox=outbox,
        )
        self.assertEqual(payload["status"], "sunat_down")
        self.assertTrue(payload["recoverable"])
        self.assertEqual(payload["retry_count"], 2)


class SunatRetryScheduleTests(SimpleTestCase):
    def test_recibo_backoff_grows(self):
        first = compute_next_retry_at(
            kind=SunatOutbox.Kind.RECIBO,
            phase=SunatOutbox.Phase.SEND,
            attempt_count=1,
        )
        later = compute_next_retry_at(
            kind=SunatOutbox.Kind.RECIBO,
            phase=SunatOutbox.Phase.SEND,
            attempt_count=4,
        )
        self.assertLess(first, later)

    def test_resumen_poll_is_short(self):
        poll = compute_next_retry_at(
            kind=SunatOutbox.Kind.RESUMEN,
            phase=SunatOutbox.Phase.POLL,
            attempt_count=2,
        )
        send = compute_next_retry_at(
            kind=SunatOutbox.Kind.RESUMEN,
            phase=SunatOutbox.Phase.SEND,
            attempt_count=2,
        )
        self.assertLess(poll, send)
