from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from sisgen.models import SisgenSendJob
from sisgen.services.send_batch_summary import (
    BATCH_STATUS_COMPLETED,
    BATCH_STATUS_DRY_RUN,
    BATCH_STATUS_SKIPPED_NO_XML,
    BATCH_STATUS_SOAP_REJECTED,
)
from sisgen.services.send_job_executor import execute_send_job
from sisgen.services.send_job_store import create_send_job
from sisgen.services.sisgen_send_service import (
    merge_batch_result,
    new_combined_result,
    send_batch,
    send_documents,
    send_single,
)

User = get_user_model()


class SisgenSendServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="sisgen_sender",
            password="secret123",
            email="sender@example.com",
        )
        self.batch = [{"kardex": "K1-2026", "idkardex": "1"}]

    @patch("sisgen.services.sisgen_send_service.SoapClientService")
    @patch("sisgen.services.sisgen_send_service.SISGENXmlGenerator")
    @patch("sisgen.services.sisgen_send_service.DataProcessorService")
    def test_send_batch_dry_run(self, mock_dp_cls, mock_xml_cls, mock_soap_cls):
        mock_dp = mock_dp_cls.return_value
        mock_dp.process_documents_batch.return_value = {
            "documents": [{"kardex": "K1-2026"}],
            "errores": [],
            "observaciones": [],
            "personas": [],
        }
        mock_xml = mock_xml_cls.return_value
        mock_xml.generate_document_xml.return_value = ("<xml/>", [])
        mock_soap_cls.return_value.build_request.return_value = {
            "url": "http://sisgen",
            "headers": {},
            "soap_body": "<soap/>",
        }

        result = send_batch(
            batch=self.batch,
            batch_index=1,
            user=self.user,
            dry_run=True,
            write_debug=lambda *_args, **_kwargs: None,
        )

        self.assertEqual(result["batch_summary"]["status"], BATCH_STATUS_DRY_RUN)
        self.assertEqual(result["merge"]["processed_kardex"], ["K1-2026"])
        self.assertEqual(len(result["merge"]["sisgen_requests"]), 1)

    @patch("sisgen.services.sisgen_send_service.SISGENXmlGenerator")
    @patch("sisgen.services.sisgen_send_service.DataProcessorService")
    def test_send_batch_skipped_when_no_xml(self, mock_dp_cls, mock_xml_cls):
        mock_dp_cls.return_value.process_documents_batch.return_value = {
            "documents": [],
            "errores": [],
            "observaciones": [],
            "personas": [],
        }
        mock_xml_cls.return_value.generate_document_xml.return_value = (
            None,
            ["XML validation failed"],
        )

        result = send_batch(
            batch=self.batch,
            batch_index=2,
            user=self.user,
            write_debug=lambda *_args, **_kwargs: None,
        )

        self.assertEqual(result["batch_summary"]["status"], BATCH_STATUS_SKIPPED_NO_XML)
        self.assertIn("XML validation failed", result["batch_summary"]["xml_issues"])

    @patch("sisgen.services.sisgen_send_service.save_response_logs_for_batch")
    @patch("sisgen.services.sisgen_send_service.parse_set_documentos_response")
    @patch("sisgen.services.sisgen_send_service.SoapClientService")
    @patch("sisgen.services.sisgen_send_service.SISGENXmlGenerator")
    @patch("sisgen.services.sisgen_send_service.DataProcessorService")
    def test_send_batch_soap_rejected(
        self,
        mock_dp_cls,
        mock_xml_cls,
        mock_soap_cls,
        mock_parse,
        mock_save_logs,
    ):
        mock_dp = mock_dp_cls.return_value
        mock_dp.process_documents_batch.return_value = {
            "documents": [{"kardex": "K1-2026"}],
            "errores": [],
            "observaciones": [],
            "personas": [],
        }
        mock_xml_cls.return_value.generate_document_xml.return_value = ("<xml/>", [])

        response = MagicMock()
        response.status_code = 500
        response.text = "<soap/>"
        response.reason = "Internal Server Error"
        mock_soap_cls.return_value.send_documents.return_value = response

        mock_parse.return_value = {
            "return_status": "INTERNAL_SERVER_ERROR",
            "return_message": "boom",
            "summary": {"soap_level_ok": False},
        }
        mock_save_logs.return_value = [99]

        result = send_batch(
            batch=self.batch,
            batch_index=1,
            user=self.user,
            write_debug=lambda *_args, **_kwargs: None,
        )

        self.assertEqual(result["batch_summary"]["status"], BATCH_STATUS_SOAP_REJECTED)
        self.assertEqual(result["merge"]["error"], 1)
        self.assertTrue(result["merge"]["soap_errors"])

    @patch("sisgen.services.sisgen_send_service.send_batch")
    def test_send_single_delegates_to_batch(self, mock_send_batch):
        mock_send_batch.return_value = {"batch_summary": {}, "merge": {}}
        doc = {"kardex": "K9-2026", "idkardex": "9"}

        send_single(doc, batch_index=3, user=self.user, dry_run=True)

        mock_send_batch.assert_called_once()
        kwargs = mock_send_batch.call_args.kwargs
        self.assertEqual(kwargs["batch"], [doc])
        self.assertEqual(kwargs["batch_index"], 3)
        self.assertTrue(kwargs["dry_run"])

    @patch("sisgen.services.sisgen_send_service.send_batch")
    def test_send_documents_splits_into_batches(self, mock_send_batch):
        mock_send_batch.side_effect = [
            {
                "batch_summary": {"batch_index": 1, "status": BATCH_STATUS_COMPLETED},
                "merge": {
                    "error": 0,
                    "messageDescription": "",
                    "data": [],
                    "errores": [],
                    "errores_sisgen_usuario": [],
                    "soap_errors": [],
                    "observaciones": [],
                    "personas": [],
                    "guardados": 1,
                    "fallidos": 0,
                    "observados": 0,
                    "processed_kardex": ["K1"],
                    "sisgen_requests": [],
                    "submission_response_ids": [],
                },
            },
            {
                "batch_summary": {"batch_index": 2, "status": BATCH_STATUS_COMPLETED},
                "merge": {
                    "error": 0,
                    "messageDescription": "",
                    "data": [],
                    "errores": [],
                    "errores_sisgen_usuario": [],
                    "soap_errors": [],
                    "observaciones": [],
                    "personas": [],
                    "guardados": 1,
                    "fallidos": 0,
                    "observados": 0,
                    "processed_kardex": ["K11"],
                    "sisgen_requests": [],
                    "submission_response_ids": [],
                },
            },
        ]

        docs = [{"kardex": f"K{i}", "idkardex": str(i)} for i in range(1, 12)]
        combined = send_documents(docs, user=self.user, batch_size=10)

        self.assertEqual(mock_send_batch.call_count, 2)
        self.assertEqual(combined["guardados"], 2)
        self.assertEqual(len(combined["batches"]), 2)
        self.assertEqual(combined["batch_summary"]["expected_batches"], 2)

    def test_merge_batch_result_accumulates_counters(self):
        combined = new_combined_result()
        merge_batch_result(
            combined,
            {
                "batch_summary": {"status": BATCH_STATUS_COMPLETED},
                "merge": {
                    "error": 1,
                    "messageDescription": "failed batch",
                    "guardados": 2,
                    "fallidos": 1,
                    "processed_kardex": ["A", "B"],
                },
            },
        )
        self.assertEqual(combined["error"], 1)
        self.assertEqual(combined["guardados"], 2)
        self.assertEqual(combined["fallidos"], 1)
        self.assertEqual(combined["processed_kardex"], ["A", "B"])


class SendJobExecutorTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="job_runner",
            password="secret123",
            email="runner@example.com",
        )

    @patch("sisgen.services.send_job_executor.send_documents")
    def test_execute_send_job_marks_completed(self, mock_send_documents):
        mock_send_documents.return_value = {"error": 0, "guardados": 1}
        job = create_send_job(
            user=self.user,
            documents=[{"kardex": "K1-2026", "idkardex": "1"}],
        )

        execute_send_job(job.pk, celery_task_id="celery-abc")
        job.refresh_from_db()

        self.assertEqual(job.status, SisgenSendJob.Status.COMPLETED)
        self.assertEqual(job.celery_task_id, "celery-abc")
        self.assertEqual(job.result["guardados"], 1)
        self.assertEqual(job.progress_label, "1/1")
        self.assertIsNotNone(job.finished_at)

    @patch("sisgen.services.send_job_executor.send_documents")
    def test_execute_send_job_marks_failed_on_exception(self, mock_send_documents):
        mock_send_documents.side_effect = RuntimeError("worker died")
        job = create_send_job(
            user=self.user,
            documents=[{"kardex": "K2-2026", "idkardex": "2"}],
        )

        with self.assertRaises(RuntimeError):
            execute_send_job(job.pk)

        job.refresh_from_db()
        self.assertEqual(job.status, SisgenSendJob.Status.FAILED)
        self.assertIn("worker died", job.error)


class SendToSISGENViewTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="sisgen_admin",
            password="secret123",
            email="admin@example.com",
        )
        self.url = reverse("sisgen_service:send_sisgen")

    @patch("sisgen.tasks.run_send_job")
    def test_post_returns_202_and_creates_job(self, mock_run_send_job):
        mock_run_send_job.delay.return_value = MagicMock(id="task-uuid-1")
        self.client.force_authenticate(user=self.user)

        response = self.client.post(
            self.url,
            {
                "documents": [
                    {"kardex": "K10-2026", "idkardex": "10"},
                    {"kardex": "K11-2026", "idkardex": "11"},
                ]
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data["error"], 0)
        self.assertEqual(response.data["status"], SisgenSendJob.Status.PENDING)
        self.assertEqual(response.data["progress"], "0/2")
        self.assertIn("job_id", response.data)
        self.assertIn("status_url", response.data)

        job = SisgenSendJob.objects.get(pk=response.data["job_id"])
        self.assertEqual(job.documents.count(), 2)
        mock_run_send_job.delay.assert_called_once_with(job.pk)

    def test_post_requires_documents(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(self.url, {"documents": []}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class SisgenSendJobDetailViewTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="sisgen_admin2",
            password="secret123",
            email="admin2@example.com",
        )
        self.job = create_send_job(
            user=self.user,
            documents=[{"kardex": "K20-2026", "idkardex": "20"}],
        )
        self.url = reverse(
            "sisgen_service:send_job_detail",
            kwargs={"job_id": self.job.pk},
        )

    def test_get_job_detail(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["job_id"], self.job.pk)
        self.assertEqual(len(response.data["documents"]), 1)

    def test_get_job_not_found(self):
        self.client.force_authenticate(user=self.user)
        url = reverse("sisgen_service:send_job_detail", kwargs={"job_id": 99999})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
class RunSendJobTaskTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="celery_user",
            password="secret123",
            email="celery@example.com",
        )

    @patch("sisgen.services.send_job_executor.send_documents")
    def test_run_send_job_task_eager(self, mock_send_documents):
        from sisgen.tasks import run_send_job

        mock_send_documents.return_value = {"error": 0, "guardados": 3}
        job = create_send_job(
            user=self.user,
            documents=[
                {"kardex": "K1-2026", "idkardex": "1"},
                {"kardex": "K2-2026", "idkardex": "2"},
                {"kardex": "K3-2026", "idkardex": "3"},
            ],
        )

        run_send_job.delay(job.pk)
        job.refresh_from_db()

        self.assertEqual(job.status, SisgenSendJob.Status.COMPLETED)
        self.assertEqual(job.result["guardados"], 3)
