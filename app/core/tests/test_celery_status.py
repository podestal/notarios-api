from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from core.services.celery_status import describe_schedule, list_beat_tasks, next_run_at

User = get_user_model()
LIMA = ZoneInfo("America/Lima")


class BeatScheduleHelperTests(SimpleTestCase):
    def test_interval_schedule_description(self):
        info = describe_schedule(300.0)
        self.assertEqual(info["type"], "interval")
        self.assertEqual(info["every_seconds"], 300.0)
        self.assertEqual(info["schedule"], "every 5 minute(s)")

    def test_next_run_from_last_run(self):
        last = datetime(2026, 8, 18, 8, 50, tzinfo=LIMA)
        now = datetime(2026, 8, 18, 8, 52, tzinfo=LIMA)
        nxt = next_run_at(300.0, last, now)
        self.assertEqual(nxt, datetime(2026, 8, 18, 8, 55, tzinfo=LIMA))

    def test_overdue_next_run_is_now(self):
        last = datetime(2026, 8, 18, 8, 0, tzinfo=LIMA)
        now = datetime(2026, 8, 18, 8, 52, tzinfo=LIMA)
        nxt = next_run_at(300.0, last, now)
        self.assertEqual(nxt, now)

    def test_unknown_next_run_without_last_run(self):
        self.assertIsNone(next_run_at(300.0, None))

    @override_settings(
        CELERY_BEAT_SCHEDULE={
            "taxes-sunat-process-due-outbox": {
                "task": "taxes.sunat.process_due_outbox",
                "schedule": 300.0,
            }
        }
    )
    @patch("core.services.celery_status.read_beat_runtime", return_value={})
    def test_list_beat_tasks_from_settings(self, _runtime):
        rows = list_beat_tasks(now=timezone.now())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "taxes-sunat-process-due-outbox")
        self.assertEqual(rows[0]["task"], "taxes.sunat.process_due_outbox")
        self.assertEqual(rows[0]["every_seconds"], 300.0)
        self.assertIsNone(rows[0]["next_run_at"])


class CeleryStatusViewTests(APITestCase):
    def setUp(self):
        self.url = reverse("celery-status")
        self.staff = User.objects.create_user(
            username="ops",
            password="secret123",
            email="ops@example.com",
            is_staff=True,
        )
        self.regular = User.objects.create_user(
            username="plain",
            password="secret123",
            email="plain@example.com",
        )

    def test_requires_staff(self):
        self.client.force_authenticate(user=self.regular)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("core.views.celery_status_payload")
    def test_staff_sees_beat_and_failures(self, mock_payload):
        mock_payload.return_value = {
            "beat_tasks": [{"name": "taxes-sunat-process-due-outbox"}],
            "sunat_retries": [],
            "sunat_failed": [{"id": 1, "status": "failed"}],
        }
        self.client.force_authenticate(user=self.staff)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("beat_tasks", response.data)
        self.assertIn("sunat_failed", response.data)
        self.assertIn("sunat_retries", response.data)
