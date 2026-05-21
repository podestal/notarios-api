from unittest.mock import MagicMock

from django.test import SimpleTestCase
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from uif.services.dashboard_service import UifDashboardService


class DashboardFilterTests(SimpleTestCase):
    def test_no_envian_returns_only_that_list(self):
        factory = APIRequestFactory()
        drf_request = Request(
            factory.get(
                "/uif/errors/",
                {
                    "initialDate": "01/04/2026",
                    "finalDate": "30/04/2026",
                    "type": "no_envian",
                },
            )
        )

        service = UifDashboardService()
        payload = {
            "lista_errores": [{"kardex": "err"}],
            "lista_kardex_ro": [{"kardex": "ro"}],
            "lista_kardex_no_envian": [{"kardex": "ne1"}, {"kardex": "ne2"}],
            "summary": {"total_no_envian": 2},
            "metadata": {"engine": "uif"},
        }
        service.run = MagicMock(return_value=payload)

        paginated = [{"kardex": "ne1"}, {"kardex": "ne2"}]
        response = service.build_response(
            drf_request,
            paginate_fn=lambda qs: paginated,
            get_paginated_response_fn=lambda data: MagicMock(data={"results": data}),
        )

        body = response.data["results"]
        self.assertEqual(body["lista_kardex_no_envian"], paginated)
        self.assertEqual(body["lista_errores"], [])
        self.assertEqual(body["lista_kardex_ro"], [])
        self.assertEqual(body["metadata"]["current_filter"], "no_envian")
