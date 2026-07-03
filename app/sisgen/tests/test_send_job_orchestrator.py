from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from sisgen.models import SisgenSendJob, SisgenSendJobDocument
from sisgen.services.send_batch_summary import (
    BATCH_STATUS_COMPLETED,
    BATCH_STATUS_SOAP_REJECTED,
    build_batch_summary_entry,
)
from sisgen.services.send_job_executor import execute_send_job, run_send_job_orchestrator
from sisgen.services.send_job_store import create_send_job

User = get_user_model()


def _completed_batch_result(*, batch_index: int, batch: list) -> dict:
    return {
        "batch_summary": build_batch_summary_entry(
            batch_index=batch_index,
            batch=batch,
            status=BATCH_STATUS_COMPLETED,
            attempted=True,
            guardados=len(batch),
        ),
        "merge": {
            "error": 0,
            "messageDescription": "",
            "data": [],
            "errores": [],
            "errores_sisgen_usuario": [],
            "soap_errors": [],
            "observaciones": [],
            "personas": [],
            "guardados": len(batch),
            "fallidos": 0,
            "observados": 0,
            "processed_kardex": [d["kardex"] for d in batch],
            "sisgen_requests": [],
            "submission_response_ids": [],
        },
    }


class RunSendJobOrchestratorTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="orch_user",
            password="secret123",
            email="orch@example.com",
        )
        self._enrich_patcher = patch(
            "sisgen.services.sisgen_send_service.enrich_send_result"
        )
        self._enrich_patcher.start()

    def tearDown(self):
        self._enrich_patcher.stop()

    @patch("sisgen.services.send_job_executor.send_batch")
    def test_orchestrator_sends_in_batches_of_10(self, mock_send_batch):
        docs = [{"kardex": f"K{i}-2026", "idkardex": str(i)} for i in range(1, 12)]
        job = create_send_job(user=self.user, documents=docs)
        mock_send_batch.side_effect = [
            _completed_batch_result(batch_index=1, batch=docs[:10]),
            _completed_batch_result(batch_index=2, batch=docs[10:]),
        ]

        result = run_send_job_orchestrator(job, documents=docs, batch_size=10)

        self.assertEqual(mock_send_batch.call_count, 2)
        self.assertEqual(result["guardados"], 11)
        self.assertEqual(result["batch_summary"]["expected_batches"], 2)

        job.refresh_from_db()
        self.assertEqual(job.progress_label, "11/11")

    @patch("sisgen.services.send_job_executor.send_batch")
    def test_orchestrator_marks_documents_completed(self, mock_send_batch):
        batch = [{"kardex": "K1-2026", "idkardex": "1"}]
        job = create_send_job(user=self.user, documents=batch)
        mock_send_batch.return_value = _completed_batch_result(batch_index=1, batch=batch)

        run_send_job_orchestrator(job, documents=batch)

        job_doc = job.documents.get()
        self.assertEqual(job_doc.status, SisgenSendJobDocument.Status.COMPLETED)
        self.assertEqual(job_doc.batch_index, 1)
        self.assertEqual(job_doc.attempt, SisgenSendJobDocument.Attempt.BATCH)

    @patch("sisgen.services.send_job_executor.send_batch")
    def test_orchestrator_marks_documents_failed_on_soap_reject(self, mock_send_batch):
        batch = [{"kardex": "K2-2026", "idkardex": "2"}]
        job = create_send_job(user=self.user, documents=batch)
        mock_send_batch.return_value = {
            "batch_summary": build_batch_summary_entry(
                batch_index=1,
                batch=batch,
                status=BATCH_STATUS_SOAP_REJECTED,
                attempted=True,
                message="INTERNAL_SERVER_ERROR",
            ),
            "merge": {
                "error": 1,
                "messageDescription": "rejected",
                "data": [],
                "errores": [],
                "errores_sisgen_usuario": [{"kardex": "K2-2026"}],
                "soap_errors": [],
                "observaciones": [],
                "personas": [],
                "guardados": 0,
                "fallidos": 0,
                "observados": 0,
                "processed_kardex": ["K2-2026"],
                "sisgen_requests": [],
                "submission_response_ids": [],
            },
        }

        run_send_job_orchestrator(job, documents=batch)

        job_doc = job.documents.get()
        self.assertEqual(job_doc.status, SisgenSendJobDocument.Status.FAILED)
        self.assertIn("INTERNAL_SERVER_ERROR", job_doc.message)

    @patch("sisgen.services.send_job_executor.send_batch")
    def test_execute_send_job_completes_job(self, mock_send_batch):
        batch = [{"kardex": "K3-2026", "idkardex": "3"}]
        job = create_send_job(user=self.user, documents=batch)
        mock_send_batch.return_value = _completed_batch_result(batch_index=1, batch=batch)

        execute_send_job(job.pk, celery_task_id="task-orch-1")
        job.refresh_from_db()

        self.assertEqual(job.status, SisgenSendJob.Status.COMPLETED)
        self.assertEqual(job.celery_task_id, "task-orch-1")
        self.assertEqual(job.result["guardados"], 1)

    def test_execute_send_job_skips_already_completed(self):
        job = create_send_job(
            user=self.user,
            documents=[{"kardex": "K4-2026", "idkardex": "4"}],
        )
        job.status = SisgenSendJob.Status.COMPLETED
        job.save(update_fields=["status"])

        with patch("sisgen.services.send_job_executor.send_batch") as mock_send_batch:
            execute_send_job(job.pk, celery_task_id="task-skip")
            mock_send_batch.assert_not_called()


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
class SendJobCeleryTaskTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="celery_orch",
            password="secret123",
            email="celery@example.com",
        )
        self._enrich_patcher = patch(
            "sisgen.services.sisgen_send_service.enrich_send_result"
        )
        self._enrich_patcher.start()

    def tearDown(self):
        self._enrich_patcher.stop()

    @patch("sisgen.services.send_job_executor.send_batch")
    def test_send_job_task_registered_name(self, mock_send_batch):
        from sisgen.tasks import send_job

        self.assertEqual(send_job.name, "sisgen.send_job")

    @patch("sisgen.services.send_job_executor.send_batch")
    def test_send_job_task_runs_orchestrator(self, mock_send_batch):
        from sisgen.tasks import send_job

        docs = [{"kardex": "K5-2026", "idkardex": "5"}]
        job = create_send_job(user=self.user, documents=docs)
        mock_send_batch.return_value = _completed_batch_result(batch_index=1, batch=docs)

        send_job.delay(job.pk)
        job.refresh_from_db()

        self.assertEqual(job.status, SisgenSendJob.Status.COMPLETED)
        mock_send_batch.assert_called_once()
