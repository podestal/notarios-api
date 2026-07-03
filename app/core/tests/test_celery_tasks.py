from django.test import TestCase, override_settings

from core.tasks import ping


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
class TestPingTask(TestCase):
    def test_ping_returns_ok(self):
        result = ping.delay("hello")
        self.assertTrue(result.successful())
        self.assertEqual(result.get(), {"status": "ok", "message": "hello"})

    def test_ping_default_message(self):
        result = ping.delay()
        self.assertEqual(result.get()["message"], "pong")
