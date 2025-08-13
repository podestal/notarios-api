from django.test import TestCase
from rest_framework.test import APIRequestFactory
from rest_framework.response import Response
from unittest.mock import MagicMock, patch

from notaria.views import CertDomiciliarioViewSet
from datetime import datetime as real_datetime


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

    @patch('notaria.views.CertDomiciliarioViewSet.serializer_class')
    @patch('notaria.views.models.CertDomiciliario.objects')
    @patch('notaria.views.datetime')
    def test_create_generates_first_when_no_last(self, mock_dt, mock_objects, mock_serializer):
        # Freeze year
        mock_dt.now.return_value = real_datetime(2025, 1, 15)
        # No last record
        mock_objects.filter.return_value.exclude.return_value.order_by.return_value.first.return_value = None
        # Serializer stub
        ser_inst = MagicMock()
        ser_inst.data = {'created': True}
        ser_inst.is_valid.return_value = True
        mock_serializer.return_value = ser_inst

        request = self.factory.post('/api/v1/cert_domiciliario/', {}, format='json')
        view = CertDomiciliarioViewSet.as_view({'post': 'create'})

        with patch.object(CertDomiciliarioViewSet, 'perform_create', return_value=None), \
             patch.object(CertDomiciliarioViewSet, 'get_success_headers', return_value={}):
            response = view(request)

        # Assert num_certificado composed as YYYY000001
        called_kwargs = mock_serializer.call_args.kwargs
        self.assertIn('data', called_kwargs)
        self.assertEqual(called_kwargs['data']['num_certificado'], '2025000001')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data, {'created': True})

    @patch('notaria.views.CertDomiciliarioViewSet.serializer_class')
    @patch('notaria.views.models.CertDomiciliario.objects')
    @patch('notaria.views.datetime')
    def test_create_increments_same_year(self, mock_dt, mock_objects, mock_serializer):
        mock_dt.now.return_value = real_datetime(2025, 3, 10)
        last = MagicMock()
        last.num_certificado = '2025000123'
        mock_objects.filter.return_value.exclude.return_value.order_by.return_value.first.return_value = last

        ser_inst = MagicMock()
        ser_inst.data = {'created': True}
        ser_inst.is_valid.return_value = True
        mock_serializer.return_value = ser_inst

        request = self.factory.post('/api/v1/cert_domiciliario/', {}, format='json')
        view = CertDomiciliarioViewSet.as_view({'post': 'create'})

        with patch.object(CertDomiciliarioViewSet, 'perform_create', return_value=None), \
             patch.object(CertDomiciliarioViewSet, 'get_success_headers', return_value={}):
            response = view(request)

        called_kwargs = mock_serializer.call_args.kwargs
        self.assertEqual(called_kwargs['data']['num_certificado'], '2025000124')
        self.assertEqual(response.status_code, 201)

    @patch('notaria.views.CertDomiciliarioViewSet.serializer_class')
    @patch('notaria.views.models.CertDomiciliario.objects')
    @patch('notaria.views.datetime')
    def test_create_resets_new_year(self, mock_dt, mock_objects, mock_serializer):
        mock_dt.now.return_value = real_datetime(2025, 1, 2)
        last = MagicMock()
        last.num_certificado = '2024000999'
        mock_objects.filter.return_value.exclude.return_value.order_by.return_value.first.return_value = last

        ser_inst = MagicMock()
        ser_inst.data = {'created': True}
        ser_inst.is_valid.return_value = True
        mock_serializer.return_value = ser_inst

        request = self.factory.post('/api/v1/cert_domiciliario/', {}, format='json')
        view = CertDomiciliarioViewSet.as_view({'post': 'create'})

        with patch.object(CertDomiciliarioViewSet, 'perform_create', return_value=None), \
             patch.object(CertDomiciliarioViewSet, 'get_success_headers', return_value={}):
            response = view(request)

        called_kwargs = mock_serializer.call_args.kwargs
        self.assertEqual(called_kwargs['data']['num_certificado'], '2025000001')
        self.assertEqual(response.status_code, 201) 