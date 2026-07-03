from django.test import SimpleTestCase

from sisgen.services.send_batch_summary import (
    BATCH_STATUS_COMPLETED,
    BATCH_STATUS_ERROR_SEND,
    BATCH_STATUS_SKIPPED_NO_XML,
    BATCH_STATUS_SOAP_REJECTED,
    build_batch_summary_entry,
    should_fan_out_batch,
)


class ShouldFanOutBatchTests(SimpleTestCase):
    def test_fan_out_on_soap_rejected_multi_doc_batch(self):
        batch = [{"kardex": "K1", "idkardex": "1"}, {"kardex": "K2", "idkardex": "2"}]
        result = {
            "batch_summary": build_batch_summary_entry(
                batch_index=1,
                batch=batch,
                status=BATCH_STATUS_SOAP_REJECTED,
                attempted=True,
            ),
        }
        self.assertTrue(should_fan_out_batch(result))

    def test_no_fan_out_on_completed_even_with_fallidos(self):
        batch = [{"kardex": "K1", "idkardex": "1"}, {"kardex": "K2", "idkardex": "2"}]
        result = {
            "batch_summary": build_batch_summary_entry(
                batch_index=1,
                batch=batch,
                status=BATCH_STATUS_COMPLETED,
                attempted=True,
                guardados=1,
                fallidos=1,
            ),
            "merge": {
                "data": [
                    {"kardex": "K1", "status": "GUARDADO"},
                    {"kardex": "K2", "status": "FALLIDO"},
                ],
            },
        }
        self.assertFalse(should_fan_out_batch(result))

    def test_no_fan_out_on_single_doc_batch_failure(self):
        batch = [{"kardex": "K1", "idkardex": "1"}]
        result = {
            "batch_summary": build_batch_summary_entry(
                batch_index=1,
                batch=batch,
                status=BATCH_STATUS_SOAP_REJECTED,
                attempted=True,
            ),
        }
        self.assertFalse(should_fan_out_batch(result))

    def test_fan_out_on_skipped_no_xml_multi_doc(self):
        batch = [{"kardex": "K1", "idkardex": "1"}, {"kardex": "K2", "idkardex": "2"}]
        result = {
            "batch_summary": build_batch_summary_entry(
                batch_index=1,
                batch=batch,
                status=BATCH_STATUS_SKIPPED_NO_XML,
                attempted=False,
            ),
        }
        self.assertTrue(should_fan_out_batch(result))

    def test_fan_out_on_error_send_multi_doc(self):
        batch = [{"kardex": "K1", "idkardex": "1"}, {"kardex": "K2", "idkardex": "2"}]
        result = {
            "batch_summary": build_batch_summary_entry(
                batch_index=1,
                batch=batch,
                status=BATCH_STATUS_ERROR_SEND,
                attempted=False,
                message="connection reset",
            ),
        }
        self.assertTrue(should_fan_out_batch(result))
