from django.test import SimpleTestCase

from sisgen.services.send_batch_summary import (
    BATCH_STATUS_COMPLETED,
    BATCH_STATUS_SKIPPED_NO_XML,
    BATCH_STATUS_SOAP_REJECTED,
    aggregate_batch_summary,
    build_batch_summary_entry,
)


class SendBatchSummaryTests(SimpleTestCase):
    def test_build_batch_summary_entry(self):
        row = build_batch_summary_entry(
            batch_index=2,
            batch=[{"kardex": "K11-2026", "idkardex": "11"}],
            status=BATCH_STATUS_COMPLETED,
            attempted=True,
            guardados=1,
            http_status=200,
            soap_return_status="OK",
        )
        self.assertEqual(row["batch_index"], 2)
        self.assertEqual(row["kardex"], ["K11-2026"])
        self.assertTrue(row["attempted"])
        self.assertEqual(row["guardados"], 1)

    def test_aggregate_batch_summary(self):
        batches = [
            build_batch_summary_entry(
                batch_index=1,
                batch=[{"kardex": "K1", "idkardex": "1"}],
                status=BATCH_STATUS_COMPLETED,
                attempted=True,
                guardados=1,
            ),
            build_batch_summary_entry(
                batch_index=2,
                batch=[{"kardex": "K2", "idkardex": "2"}],
                status=BATCH_STATUS_SOAP_REJECTED,
                attempted=True,
                message="INTERNAL_SERVER_ERROR",
            ),
            build_batch_summary_entry(
                batch_index=3,
                batch=[{"kardex": "K3", "idkardex": "3"}],
                status=BATCH_STATUS_SKIPPED_NO_XML,
                attempted=False,
            ),
        ]
        summary = aggregate_batch_summary(
            batches, total_documents=25, expected_batches=3
        )
        self.assertEqual(summary["expected_batches"], 3)
        self.assertEqual(summary["reported_batches"], 3)
        self.assertEqual(summary["completed"], 1)
        self.assertEqual(summary["soap_rejected"], 1)
        self.assertEqual(summary["skipped_no_xml"], 1)
        self.assertEqual(summary["documents_soap_attempted"], 2)
        self.assertFalse(summary["all_batches_completed"])
