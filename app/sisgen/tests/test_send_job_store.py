from django.contrib.auth import get_user_model
from django.test import TestCase

from sisgen.models import SisgenSendJob, SisgenSendJobDocument, SisgenSoapResponse
from sisgen.services.send_job_store import (
    complete_job,
    create_send_job,
    fail_job,
    set_job_running,
    update_job_document,
    update_job_progress,
)

User = get_user_model()


class SisgenSendJobModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="sisgen_job_tester",
            password="secret123",
            email="sisgen@example.com",
        )

    def test_create_send_job_creates_document_rows(self):
        job = create_send_job(
            user=self.user,
            documents=[
                {"kardex": "K1-2026", "idkardex": "101"},
                {"kardex": "K2-2026", "idkardex": "102"},
            ],
            filters={"estado": "0"},
        )

        self.assertEqual(job.status, SisgenSendJob.Status.PENDING)
        self.assertEqual(job.progress_total, 2)
        self.assertEqual(job.progress_processed, 0)
        self.assertEqual(job.progress_label, "0/2")
        self.assertEqual(job.payload["filters"], {"estado": "0"})
        self.assertEqual(len(job.payload["documents"]), 2)

        docs = list(job.documents.order_by("kardex"))
        self.assertEqual(len(docs), 2)
        self.assertEqual(docs[0].kardex, "K1-2026")
        self.assertEqual(docs[0].status, SisgenSendJobDocument.Status.PENDING)
        self.assertEqual(docs[1].idkardex, "102")

    def test_create_send_job_dedupes_kardex(self):
        job = create_send_job(
            user=self.user,
            documents=[
                {"kardex": "K1-2026", "idkardex": "1"},
                {"kardex": "K1-2026", "idkardex": "9"},
                {"kardex": "", "idkardex": "x"},
            ],
        )

        self.assertEqual(job.progress_total, 1)
        self.assertEqual(job.documents.count(), 1)
        self.assertEqual(job.documents.get().idkardex, "1")

    def test_job_lifecycle_running_completed(self):
        job = create_send_job(
            user=self.user,
            documents=[{"kardex": "K9-2026", "idkardex": "9"}],
        )

        set_job_running(job, "celery-task-uuid-1")
        job.refresh_from_db()
        self.assertEqual(job.status, SisgenSendJob.Status.RUNNING)
        self.assertEqual(job.celery_task_id, "celery-task-uuid-1")
        self.assertIsNone(job.finished_at)

        update_job_progress(job, processed=1)
        job.refresh_from_db()
        self.assertEqual(job.progress_label, "1/1")

        result = {"error": 0, "guardados": 1, "batch_summary": {}}
        complete_job(job, result)
        job.refresh_from_db()
        self.assertEqual(job.status, SisgenSendJob.Status.COMPLETED)
        self.assertEqual(job.result, result)
        self.assertEqual(job.error, "")
        self.assertIsNotNone(job.finished_at)

    def test_job_lifecycle_failed(self):
        job = create_send_job(
            user=self.user,
            documents=[{"kardex": "K3-2026", "idkardex": "3"}],
        )

        fail_job(job, "orchestrator crashed")
        job.refresh_from_db()
        self.assertEqual(job.status, SisgenSendJob.Status.FAILED)
        self.assertEqual(job.error, "orchestrator crashed")
        self.assertIsNotNone(job.finished_at)

    def test_update_job_document_links_soap_response(self):
        job = create_send_job(
            user=self.user,
            documents=[{"kardex": "K4-2026", "idkardex": "4"}],
        )
        job_doc = job.documents.get()
        soap_row = SisgenSoapResponse.objects.create(
            kardex="K4-2026",
            idkardex="4",
            batch_index=1,
            http_status=200,
            document_status="GUARDADO",
            created_by=self.user,
        )

        update_job_document(
            job_doc,
            status=SisgenSendJobDocument.Status.COMPLETED,
            message="GUARDADO",
            batch_index=1,
            attempt=SisgenSendJobDocument.Attempt.BATCH,
            submission_response=soap_row,
        )
        job_doc.refresh_from_db()

        self.assertEqual(job_doc.status, SisgenSendJobDocument.Status.COMPLETED)
        self.assertEqual(job_doc.attempt, SisgenSendJobDocument.Attempt.BATCH)
        self.assertEqual(job_doc.batch_index, 1)
        self.assertEqual(job_doc.submission_response_id, soap_row.pk)

    def test_unique_kardex_per_job(self):
        job = create_send_job(
            user=self.user,
            documents=[{"kardex": "K5-2026", "idkardex": "5"}],
        )
        with self.assertRaises(Exception):
            SisgenSendJobDocument.objects.create(
                job=job,
                kardex="K5-2026",
                idkardex="5",
            )
