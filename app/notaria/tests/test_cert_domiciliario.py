from django.test import TestCase
from rest_framework.test import APIRequestFactory
from rest_framework.response import Response
from unittest.mock import MagicMock, patch

from notaria.views import CertDomiciliarioViewSet


class CertDomiciliarioListTests(TestCase):
    def setUp(self) -> None:
        self.factory = APIRequestFactory()

    @patch('notaria.views.serializers.CertDomiciliarioSerializer')
    def test_list_filters_by_date_range_and_name(self, mock_serializer):
        mock_serializer.return_value = MagicMock(data=[])

        request = self.factory.get(
            '/api/v1/cert_domiciliario/',
            {
                'dateFrom': '2025-01-01',
                'dateTo': '2025-02-01',
                'nombre_solic': 'RODRIGUEZ',
                'pag': '1',
            },
        )
        view = CertDomiciliarioViewSet.as_view({'get': 'list'})

        with patch.object(CertDomiciliarioViewSet, 'paginate_queryset', return_value=[]) as mock_paginate, \
             patch.object(CertDomiciliarioViewSet, 'get_paginated_response', side_effect=lambda data: Response({'results': data})):
            qs_mock = MagicMock()
            qs_mock.filter.return_value = qs_mock
            original_qs = CertDomiciliarioViewSet.queryset
            CertDomiciliarioViewSet.queryset = qs_mock
            try:
                response = view(request)
            finally:
                CertDomiciliarioViewSet.queryset = original_qs

        qs_mock.filter.assert_any_call(fec_ingreso__range=('2025-01-01', '2025-02-01'))
        qs_mock.filter.assert_any_call(nombre_solic__icontains='RODRIGUEZ')
        mock_paginate.assert_called_once()
        mock_serializer.assert_called_once()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {'results': []})

    @patch('notaria.views.serializers.CertDomiciliarioSerializer')
    def test_list_filters_by_num_certificado_exact(self, mock_serializer):
        mock_serializer.return_value = MagicMock(data=[])
        request = self.factory.get(
            '/api/v1/cert_domiciliario/',
            {
                'num_certificado': '2025000123',
            },
        )
        view = CertDomiciliarioViewSet.as_view({'get': 'list'})

        with patch.object(CertDomiciliarioViewSet, 'paginate_queryset', return_value=[]), \
             patch.object(CertDomiciliarioViewSet, 'get_paginated_response', side_effect=lambda data: Response({'results': data})):
            qs_mock = MagicMock()
            qs_mock.filter.return_value = qs_mock
            original_qs = CertDomiciliarioViewSet.queryset
            CertDomiciliarioViewSet.queryset = qs_mock
            try:
                response = view(request)
            finally:
                CertDomiciliarioViewSet.queryset = original_qs

        qs_mock.filter.assert_any_call(num_certificado='2025000123')
        mock_serializer.assert_called_once()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {'results': []}) 

    @patch('notaria.views.serializers.CertDomiciliarioSerializer')
    def test_list_filters_only_date_from(self, mock_serializer):
        mock_serializer.return_value = MagicMock(data=[])
        request = self.factory.get(
            '/api/v1/cert_domiciliario/',
            {
                'dateFrom': '2025-01-01',
            },
        )
        view = CertDomiciliarioViewSet.as_view({'get': 'list'})

        with patch.object(CertDomiciliarioViewSet, 'paginate_queryset', return_value=[]), \
             patch.object(CertDomiciliarioViewSet, 'get_paginated_response', side_effect=lambda data: Response({'results': data})):
            qs_mock = MagicMock()
            qs_mock.filter.return_value = qs_mock
            original_qs = CertDomiciliarioViewSet.queryset
            CertDomiciliarioViewSet.queryset = qs_mock
            try:
                response = view(request)
            finally:
                CertDomiciliarioViewSet.queryset = original_qs

        qs_mock.filter.assert_any_call(fec_ingreso__gte='2025-01-01')
        self.assertEqual(response.status_code, 200)

    @patch('notaria.views.serializers.CertDomiciliarioSerializer')
    def test_list_filters_only_date_to(self, mock_serializer):
        mock_serializer.return_value = MagicMock(data=[])
        request = self.factory.get(
            '/api/v1/cert_domiciliario/',
            {
                'dateTo': '2025-02-15',
            },
        )
        view = CertDomiciliarioViewSet.as_view({'get': 'list'})

        with patch.object(CertDomiciliarioViewSet, 'paginate_queryset', return_value=[]), \
             patch.object(CertDomiciliarioViewSet, 'get_paginated_response', side_effect=lambda data: Response({'results': data})):
            qs_mock = MagicMock()
            qs_mock.filter.return_value = qs_mock
            original_qs = CertDomiciliarioViewSet.queryset
            CertDomiciliarioViewSet.queryset = qs_mock
            try:
                response = view(request)
            finally:
                CertDomiciliarioViewSet.queryset = original_qs

        qs_mock.filter.assert_any_call(fec_ingreso__lte='2025-02-15')
        self.assertEqual(response.status_code, 200)

    @patch('notaria.views.serializers.CertDomiciliarioSerializer')
    def test_list_applies_all_filters_and_serializes_page(self, mock_serializer):
        # Make serializer return sentinel data
        mock_ser_instance = MagicMock()
        mock_ser_instance.data = [{'id': 1}]
        mock_serializer.return_value = mock_ser_instance

        page_items = ['objA', 'objB']
        request = self.factory.get(
            '/api/v1/cert_domiciliario/',
            {
                'dateFrom': '2025-01-01',
                'dateTo': '2025-01-31',
                'num_certificado': '2025000001',
                'nombre_solic': 'PEREZ',
            },
        )
        view = CertDomiciliarioViewSet.as_view({'get': 'list'})

        with patch.object(CertDomiciliarioViewSet, 'paginate_queryset', return_value=page_items) as mock_paginate, \
             patch.object(CertDomiciliarioViewSet, 'get_paginated_response', side_effect=lambda data: Response({'results': data})) as mock_get_resp:
            qs_mock = MagicMock()
            qs_mock.filter.return_value = qs_mock
            original_qs = CertDomiciliarioViewSet.queryset
            CertDomiciliarioViewSet.queryset = qs_mock
            try:
                response = view(request)
            finally:
                CertDomiciliarioViewSet.queryset = original_qs

        # Verify all filters applied
        qs_mock.filter.assert_any_call(fec_ingreso__range=('2025-01-01', '2025-01-31'))
        qs_mock.filter.assert_any_call(num_certificado='2025000001')
        qs_mock.filter.assert_any_call(nombre_solic__icontains='PEREZ')
        # Serializer called with page items and many=True
        mock_serializer.assert_called_once_with(page_items, many=True)
        # get_paginated_response got serializer.data
        # Since we passed Response({'results': data}), response.data should equal serializer.data
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {'results': [{'id': 1}]}) 