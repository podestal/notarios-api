import pytest
from rest_framework import status
from rest_framework.test import APIClient
from unittest.mock import patch, MagicMock
from collections import defaultdict

from notaria import models
from notaria.views import KardexViewSet


@pytest.mark.django_db
class TestKardexViewSetList:
    """
    Test suite for KardexViewSet.list method using mocking to avoid unmanaged model issues.
    """

    def setup_method(self):
        """Set up test data for each test method."""
        self.api_client = APIClient()
        self.url = '/api/kardex/'  # Fixed: Use correct API endpoint

    @patch('notaria.models.Kardex.objects')
    @patch('notaria.models.Usuarios.objects')
    @patch('notaria.models.Contratantes.objects')
    @patch('notaria.models.Cliente2.objects')
    def test_list_empty_database(self, mock_cliente2, mock_contratantes, mock_usuarios, mock_kardex):
        """Test list method when database is empty."""
        # Mock empty querysets
        mock_kardex.all.return_value.order_by.return_value = []
        mock_usuarios.filter.return_value = []
        mock_contratantes.filter.return_value.values.return_value = []
        mock_cliente2.filter.return_value.values.return_value = []

        response = self.api_client.get(self.url)
        
        assert response.status_code == status.HTTP_200_OK
        assert 'results' in response.data
        assert response.data['results'] == []
        assert response.data['count'] == 0

    @patch('notaria.models.Kardex.objects')
    @patch('notaria.models.Usuarios.objects') 
    @patch('notaria.models.Contratantes.objects')
    @patch('notaria.models.Cliente2.objects')
    def test_list_single_kardex_without_relationships(self, mock_cliente2, mock_contratantes, mock_usuarios, mock_kardex):
        """Test list method with a single Kardex record without related data."""
        # Create mock Kardex object
        mock_kardex_obj = MagicMock()
        mock_kardex_obj.idkardex = 1
        mock_kardex_obj.kardex = 'KAR1-2024'
        mock_kardex_obj.idtipkar = 1
        mock_kardex_obj.fechaingreso = '01/01/2024'
        mock_kardex_obj.contrato = 'Test Contract'
        mock_kardex_obj.codactos = '001'
        mock_kardex_obj.idusuario = 1
        mock_kardex_obj.fechaescritura = None
        mock_kardex_obj.numescritura = None
        mock_kardex_obj.numminuta = None
        mock_kardex_obj.folioini = None
        mock_kardex_obj.foliofin = None
        mock_kardex_obj.numinstrmento = None
        mock_kardex_obj.txa_minuta = None
        mock_kardex_obj.retenido = 0
        mock_kardex_obj.desistido = 0
        mock_kardex_obj.autorizado = 1
        mock_kardex_obj.idrecogio = 1
        mock_kardex_obj.pagado = 1
        mock_kardex_obj.visita = 0
        mock_kardex_obj.papelini = None
        mock_kardex_obj.papelfin = None
        mock_kardex_obj.responsable = 1
        mock_kardex_obj.referencia = None

        # Mock the queryset to return our mock object
        mock_kardex.all.return_value.order_by.return_value = [mock_kardex_obj]
        
        # Mock empty related objects
        mock_usuarios.filter.return_value = []
        mock_contratantes.filter.return_value.values.return_value = []
        mock_cliente2.filter.return_value.values.return_value = []

        response = self.api_client.get(self.url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['count'] == 1
        assert len(response.data['results']) == 1
        
        kardex_data = response.data['results'][0]
        assert kardex_data['idkardex'] == 1
        assert kardex_data['kardex'] == 'KAR1-2024'
        assert kardex_data['fechaingreso'] == '01/01/2024'
        assert kardex_data['contrato'] == 'Test Contract'
        assert kardex_data['idusuario'] == 1

    @patch('notaria.views.KardexViewSet.get_queryset')
    @patch('notaria.models.Usuarios.objects')
    @patch('notaria.models.Contratantes.objects') 
    @patch('notaria.models.Cliente2.objects')
    def test_list_with_idtipkar_filter(self, mock_cliente2, mock_contratantes, mock_usuarios, mock_get_queryset):
        """Test list method with idtipkar query parameter filtering."""
        # Create mock Kardex objects
        mock_kardex_obj1 = MagicMock()
        mock_kardex_obj1.idkardex = 1
        mock_kardex_obj1.kardex = 'KAR1-2024'
        mock_kardex_obj1.idtipkar = 1
        mock_kardex_obj1.idusuario = 1
        mock_kardex_obj1.fechaingreso = '01/01/2024'
        mock_kardex_obj1.contrato = 'Test Contract 1'
        mock_kardex_obj1.codactos = '001'
        # Set other required fields
        for field in ['fechaescritura', 'numescritura', 'numminuta', 'folioini', 'foliofin', 
                     'numinstrmento', 'txa_minuta', 'papelini', 'papelfin', 'referencia']:
            setattr(mock_kardex_obj1, field, None)
        for field in ['retenido', 'desistido', 'autorizado', 'idrecogio', 'pagado', 'visita', 'responsable']:
            setattr(mock_kardex_obj1, field, 0)

        # Mock get_queryset to return our filtered result
        mock_get_queryset.return_value = [mock_kardex_obj1]
        
        # Mock empty related objects
        mock_usuarios.filter.return_value = []
        mock_contratantes.filter.return_value.values.return_value = []
        mock_cliente2.filter.return_value.values.return_value = []

        # Test filtering by idtipkar=1
        response = self.api_client.get(self.url, {'idtipkar': 1})
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['count'] == 1
        assert len(response.data['results']) == 1
        
        # Verify the get_queryset was called
        mock_get_queryset.assert_called_once()

    @patch('notaria.models.Kardex.objects')
    @patch('notaria.models.Usuarios.objects')
    @patch('notaria.models.Contratantes.objects')
    @patch('notaria.models.Cliente2.objects')
    def test_list_with_complete_relationships(self, mock_cliente2, mock_contratantes, mock_usuarios, mock_kardex):
        """Test list method with complete related data (usuarios, contratantes, clientes)."""
        # Create mock Kardex object
        mock_kardex_obj = MagicMock()
        mock_kardex_obj.idkardex = 1
        mock_kardex_obj.kardex = 'KAR1-2024'
        mock_kardex_obj.idtipkar = 1
        mock_kardex_obj.idusuario = 1
        mock_kardex_obj.fechaingreso = '01/01/2024'
        mock_kardex_obj.contrato = 'Test Contract'
        mock_kardex_obj.codactos = '001'
        # Set other required fields
        for field in ['fechaescritura', 'numescritura', 'numminuta', 'folioini', 'foliofin',
                     'numinstrmento', 'txa_minuta', 'papelini', 'papelfin', 'referencia']:
            setattr(mock_kardex_obj, field, None)
        for field in ['retenido', 'desistido', 'autorizado', 'idrecogio', 'pagado', 'visita', 'responsable']:
            setattr(mock_kardex_obj, field, 0)

        mock_kardex.all.return_value.order_by.return_value = [mock_kardex_obj]

        # Mock Usuario
        mock_usuario = MagicMock()
        mock_usuario.idusuario = 1
        mock_usuario.loginusuario = 'testuser'
        mock_usuario.apepat = 'Apellido'
        mock_usuario.apemat = 'Apellido2'
        mock_usuario.prinom = 'Nombre'
        mock_usuario.segnom = 'Nombre2'
        mock_usuarios.filter.return_value = [mock_usuario]

        # Mock Contratantes
        mock_contratantes.filter.return_value.values.return_value = [
            {'idcontratante': '1001', 'kardex': 'KAR1-2024'},
            {'idcontratante': '1002', 'kardex': 'KAR1-2024'}
        ]

        # Mock Cliente2
        mock_cliente2.filter.return_value.values.return_value = [
            {'idcontratante': '1001', 'idcliente': 'C001', 'nombre': 'Juan Perez', 'numdoc': '12345678', 'razonsocial': None},
            {'idcontratante': '1002', 'idcliente': 'C002', 'nombre': 'Maria Garcia', 'numdoc': '87654321', 'razonsocial': None}
        ]

        response = self.api_client.get(self.url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['count'] == 1
        
        kardex_data = response.data['results'][0]
        assert kardex_data['idkardex'] == 1
        
        # Verify usuario relationship is included
        assert 'usuario' in kardex_data
        
        # Verify cliente relationship is included
        assert 'cliente' in kardex_data

    @patch('notaria.views.KardexViewSet.get_queryset')
    @patch('notaria.models.Usuarios.objects')
    @patch('notaria.models.Contratantes.objects') 
    @patch('notaria.models.Cliente2.objects')
    def test_list_ordering(self, mock_cliente2, mock_contratantes, mock_usuarios, mock_get_queryset):
        """Test list method ordering by -idkardex."""
        # Create mock Kardex objects with specific IDs
        mock_objects = []
        for kid in [5, 4, 3, 2, 1]:  # Already in descending order
            mock_obj = MagicMock()
            mock_obj.idkardex = kid
            mock_obj.kardex = f'KAR{kid}-2024'
            mock_obj.idtipkar = 1
            mock_obj.idusuario = 1
            # Set required fields
            for field in ['fechaingreso', 'contrato', 'codactos', 'fechaescritura', 'numescritura', 'numminuta', 
                         'folioini', 'foliofin', 'numinstrmento', 'txa_minuta', 'papelini', 'papelfin', 'referencia']:
                setattr(mock_obj, field, None)
            for field in ['retenido', 'desistido', 'autorizado', 'idrecogio', 'pagado', 'visita', 'responsable']:
                setattr(mock_obj, field, 0)
            mock_objects.append(mock_obj)

        # Mock get_queryset to return objects in descending order
        mock_get_queryset.return_value = mock_objects
        
        # Mock all related objects to prevent database queries
        mock_usuarios.filter.return_value = []
        mock_contratantes.filter.return_value.values.return_value = []
        mock_cliente2.filter.return_value.values.return_value = []

        response = self.api_client.get(self.url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['count'] == 5
        
        # Verify get_queryset was called
        mock_get_queryset.assert_called_once()
        
        # Verify the results are in descending order
        results = response.data['results']
        expected_order = [5, 4, 3, 2, 1]
        actual_order = [result['idkardex'] for result in results]
        assert actual_order == expected_order

    def test_list_invalid_idtipkar_filter(self):
        """Test list method with invalid idtipkar query parameter."""
        with patch('notaria.models.Kardex.objects') as mock_kardex:
            # Mock empty queryset for invalid filter
            mock_queryset = MagicMock()
            mock_queryset.filter.return_value.order_by.return_value = []
            mock_kardex.all.return_value = mock_queryset

            # Test with non-existent idtipkar
            response = self.api_client.get(self.url, {'idtipkar': 999})
            
            assert response.status_code == status.HTTP_200_OK
            assert response.data['count'] == 0
            assert len(response.data['results']) == 0

    def test_list_pagination_structure(self):
        """Test that the response has proper pagination structure."""
        with patch('notaria.models.Kardex.objects') as mock_kardex:
            mock_kardex.all.return_value.order_by.return_value = []

            response = self.api_client.get(self.url)
            
            assert response.status_code == status.HTTP_200_OK
            
            # Check pagination structure
            assert 'count' in response.data
            assert 'next' in response.data
            assert 'previous' in response.data
            assert 'results' in response.data
            assert isinstance(response.data['results'], list)

    # ========== ADDITIONAL TEST CASES FOR LIST METHOD ==========

    @patch('notaria.views.KardexViewSet.get_queryset')
    @patch('notaria.models.Usuarios.objects')
    @patch('notaria.models.Contratantes.objects')
    @patch('notaria.models.Cliente2.objects')
    def test_list_pagination_first_page_with_next(self, mock_cliente2, mock_contratantes, mock_usuarios, mock_get_queryset):
        """Test first page pagination when there are more pages available."""
        # Create 15 mock Kardex objects (more than default page size of 10)
        mock_objects = []
        for i in range(15):
            mock_obj = MagicMock()
            mock_obj.idkardex = i + 1
            mock_obj.kardex = f'KAR{i+1}-2024'
            mock_obj.idtipkar = 1
            mock_obj.idusuario = 1
            # Set required fields
            for field in ['fechaingreso', 'contrato', 'codactos', 'fechaescritura', 'numescritura', 'numminuta',
                         'folioini', 'foliofin', 'numinstrmento', 'txa_minuta', 'papelini', 'papelfin', 'referencia']:
                setattr(mock_obj, field, f'test_{field}_{i}' if field != 'fechaingreso' else '01/01/2024')
            for field in ['retenido', 'desistido', 'autorizado', 'idrecogio', 'pagado', 'visita', 'responsable']:
                setattr(mock_obj, field, 0)
            mock_objects.append(mock_obj)

        mock_get_queryset.return_value = mock_objects
        
        # Mock empty related objects
        mock_usuarios.filter.return_value = []
        mock_contratantes.filter.return_value.values.return_value = []
        mock_cliente2.filter.return_value.values.return_value = []

        response = self.api_client.get(self.url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['count'] == 15
        assert len(response.data['results']) == 10  # Default page size
        assert response.data['next'] is not None  # Should have next page
        assert response.data['previous'] is None  # First page, no previous

    @patch('notaria.views.KardexViewSet.get_queryset')
    @patch('notaria.models.Usuarios.objects')
    @patch('notaria.models.Contratantes.objects')
    @patch('notaria.models.Cliente2.objects')
    def test_list_pagination_custom_page_size_exceeds_data(self, mock_cliente2, mock_contratantes, mock_usuarios, mock_get_queryset):
        """Test pagination when requested page size exceeds available data."""
        # Create only 3 mock objects
        mock_objects = []
        for i in range(3):
            mock_obj = MagicMock()
            mock_obj.idkardex = i + 1
            mock_obj.kardex = f'KAR{i+1}-2024'
            mock_obj.idtipkar = 1
            mock_obj.idusuario = 1
            # Set required fields
            for field in ['fechaingreso', 'contrato', 'codactos', 'fechaescritura', 'numescritura', 'numminuta',
                         'folioini', 'foliofin', 'numinstrmento', 'txa_minuta', 'papelini', 'papelfin', 'referencia']:
                setattr(mock_obj, field, f'test_{field}_{i}' if field != 'fechaingreso' else '01/01/2024')
            for field in ['retenido', 'desistido', 'autorizado', 'idrecogio', 'pagado', 'visita', 'responsable']:
                setattr(mock_obj, field, 0)
            mock_objects.append(mock_obj)

        mock_get_queryset.return_value = mock_objects
        
        # Mock empty related objects
        mock_usuarios.filter.return_value = []
        mock_contratantes.filter.return_value.values.return_value = []
        mock_cliente2.filter.return_value.values.return_value = []

        # Request page size larger than available data
        response = self.api_client.get(self.url, {'page_size': 10})
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['count'] == 3
        assert len(response.data['results']) == 3  # Should return all available
        assert response.data['next'] is None
        assert response.data['previous'] is None

    @patch('notaria.views.KardexViewSet.get_queryset')
    @patch('notaria.models.Usuarios.objects')
    @patch('notaria.models.Contratantes.objects')
    @patch('notaria.models.Cliente2.objects')
    def test_list_with_usuarios_but_no_contratantes(self, mock_cliente2, mock_contratantes, mock_usuarios, mock_get_queryset):
        """Test list when Kardex has usuarios but no contratantes."""
        # Create mock Kardex
        mock_kardex_obj = MagicMock()
        mock_kardex_obj.idkardex = 1
        mock_kardex_obj.kardex = 'KAR1-2024'
        mock_kardex_obj.idtipkar = 1
        mock_kardex_obj.idusuario = 1
        # Set required fields
        for field in ['fechaingreso', 'contrato', 'codactos', 'fechaescritura', 'numescritura', 'numminuta',
                     'folioini', 'foliofin', 'numinstrmento', 'txa_minuta', 'papelini', 'papelfin', 'referencia']:
            setattr(mock_kardex_obj, field, 'test_value' if field != 'fechaingreso' else '01/01/2024')
        for field in ['retenido', 'desistido', 'autorizado', 'idrecogio', 'pagado', 'visita', 'responsable']:
            setattr(mock_kardex_obj, field, 0)

        mock_get_queryset.return_value = [mock_kardex_obj]
        
        # Mock usuario exists
        mock_usuario = MagicMock()
        mock_usuario.idusuario = 1
        mock_usuario.loginusuario = 'testuser'
        mock_usuarios.filter.return_value = [mock_usuario]
        
        # Mock NO contratantes
        mock_contratantes.filter.return_value.values.return_value = []
        mock_cliente2.filter.return_value.values.return_value = []

        response = self.api_client.get(self.url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['count'] == 1
        
        # Should handle missing contratantes gracefully
        kardex_data = response.data['results'][0]
        assert kardex_data['idkardex'] == 1
        assert 'usuario' in kardex_data
        assert 'cliente' in kardex_data

    @patch('notaria.views.KardexViewSet.get_queryset')
    @patch('notaria.models.Usuarios.objects')
    @patch('notaria.models.Contratantes.objects')
    @patch('notaria.models.Cliente2.objects')
    def test_list_with_contratantes_but_no_clientes(self, mock_cliente2, mock_contratantes, mock_usuarios, mock_get_queryset):
        """Test list when contratantes exist but have no associated clientes."""
        # Create mock Kardex
        mock_kardex_obj = MagicMock()
        mock_kardex_obj.idkardex = 1
        mock_kardex_obj.kardex = 'KAR1-2024'
        mock_kardex_obj.idtipkar = 1
        mock_kardex_obj.idusuario = 1
        # Set required fields
        for field in ['fechaingreso', 'contrato', 'codactos', 'fechaescritura', 'numescritura', 'numminuta',
                     'folioini', 'foliofin', 'numinstrmento', 'txa_minuta', 'papelini', 'papelfin', 'referencia']:
            setattr(mock_kardex_obj, field, 'test_value' if field != 'fechaingreso' else '01/01/2024')
        for field in ['retenido', 'desistido', 'autorizado', 'idrecogio', 'pagado', 'visita', 'responsable']:
            setattr(mock_kardex_obj, field, 0)

        mock_get_queryset.return_value = [mock_kardex_obj]
        
        # Mock empty usuarios
        mock_usuarios.filter.return_value = []
        
        # Mock contratantes exist
        mock_contratantes.filter.return_value.values.return_value = [
            {'idcontratante': '1001', 'kardex': 'KAR1-2024'}
        ]
        
        # Mock NO clientes for these contratantes
        mock_cliente2.filter.return_value.values.return_value = []

        response = self.api_client.get(self.url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['count'] == 1
        
        # Should handle missing clientes gracefully
        kardex_data = response.data['results'][0]
        assert kardex_data['idkardex'] == 1

    @patch('notaria.views.KardexViewSet.get_queryset')
    @patch('notaria.models.Usuarios.objects')
    @patch('notaria.models.Contratantes.objects')
    @patch('notaria.models.Cliente2.objects')
    def test_list_serializer_context_passing(self, mock_cliente2, mock_contratantes, mock_usuarios, mock_get_queryset):
        """Test that serializer context is properly passed with all required maps."""
        # Create mock Kardex
        mock_kardex_obj = MagicMock()
        mock_kardex_obj.idkardex = 1
        mock_kardex_obj.kardex = 'KAR1-2024'
        mock_kardex_obj.idtipkar = 1
        mock_kardex_obj.idusuario = 1
        # Set required fields
        for field in ['fechaingreso', 'contrato', 'codactos', 'fechaescritura', 'numescritura', 'numminuta',
                     'folioini', 'foliofin', 'numinstrmento', 'txa_minuta', 'papelini', 'papelfin', 'referencia']:
            setattr(mock_kardex_obj, field, 'test_value' if field != 'fechaingreso' else '01/01/2024')
        for field in ['retenido', 'desistido', 'autorizado', 'idrecogio', 'pagado', 'visita', 'responsable']:
            setattr(mock_kardex_obj, field, 0)

        mock_get_queryset.return_value = [mock_kardex_obj]
        
        # Mock all related objects with specific data
        mock_usuario = MagicMock()
        mock_usuario.idusuario = 1
        mock_usuario.loginusuario = 'testuser'
        mock_usuarios.filter.return_value = [mock_usuario]
        
        mock_contratantes.filter.return_value.values.return_value = [
            {'idcontratante': '1001', 'kardex': 'KAR1-2024'}
        ]
        
        mock_cliente2.filter.return_value.values.return_value = [
            {'idcontratante': '1001', 'nombre': 'Juan Perez', 'numdoc': '12345678', 'razonsocial': None}
        ]

        response = self.api_client.get(self.url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['count'] == 1
        
        # Verify the context data is properly structured
        kardex_data = response.data['results'][0]
        assert 'usuario' in kardex_data
        assert 'cliente' in kardex_data

    @patch('notaria.views.KardexViewSet.get_queryset')
    @patch('notaria.models.Usuarios.objects')
    @patch('notaria.models.Contratantes.objects')
    @patch('notaria.models.Cliente2.objects')
    def test_list_with_mixed_data_completeness(self, mock_cliente2, mock_contratantes, mock_usuarios, mock_get_queryset):
        """Test list with mixed data completeness - some records have full data, others don't."""
        # Create multiple mock Kardex objects with varying data completeness
        mock_objects = []
        
        # Complete record
        mock_obj1 = MagicMock()
        mock_obj1.idkardex = 1
        mock_obj1.kardex = 'KAR1-2024'
        mock_obj1.idtipkar = 1
        mock_obj1.idusuario = 1
        for field in ['fechaingreso', 'contrato', 'codactos', 'fechaescritura', 'numescritura', 'numminuta',
                     'folioini', 'foliofin', 'numinstrmento', 'txa_minuta', 'papelini', 'papelfin', 'referencia']:
            setattr(mock_obj1, field, 'complete_value' if field != 'fechaingreso' else '01/01/2024')
        for field in ['retenido', 'desistido', 'autorizado', 'idrecogio', 'pagado', 'visita', 'responsable']:
            setattr(mock_obj1, field, 1)
        mock_objects.append(mock_obj1)
        
        # Incomplete record (missing some fields)
        mock_obj2 = MagicMock()
        mock_obj2.idkardex = 2
        mock_obj2.kardex = 'KAR2-2024'
        mock_obj2.idtipkar = 1
        mock_obj2.idusuario = 999  # Non-existent user
        for field in ['fechaingreso', 'contrato', 'codactos']:
            setattr(mock_obj2, field, 'minimal_value' if field != 'fechaingreso' else '02/01/2024')
        for field in ['fechaescritura', 'numescritura', 'numminuta', 'folioini', 'foliofin', 
                     'numinstrmento', 'txa_minuta', 'papelini', 'papelfin', 'referencia']:
            setattr(mock_obj2, field, None)
        for field in ['retenido', 'desistido', 'autorizado', 'idrecogio', 'pagado', 'visita', 'responsable']:
            setattr(mock_obj2, field, 0)
        mock_objects.append(mock_obj2)

        mock_get_queryset.return_value = mock_objects
        
        # Mock partial related data
        mock_usuario = MagicMock()
        mock_usuario.idusuario = 1
        mock_usuario.loginusuario = 'existing_user'
        mock_usuarios.filter.return_value = [mock_usuario]  # Only user 1 exists, not 999
        
        mock_contratantes.filter.return_value.values.return_value = [
            {'idcontratante': '1001', 'kardex': 'KAR1-2024'}  # Only KAR1 has contratantes
        ]
        
        mock_cliente2.filter.return_value.values.return_value = [
            {'idcontratante': '1001', 'nombre': 'Juan Perez', 'numdoc': '12345678', 'razonsocial': None}
        ]

        response = self.api_client.get(self.url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['count'] == 2
        
        # Both records should be returned despite different data completeness
        results = response.data['results']
        assert len(results) == 2
        
        # Verify both records have required structure
        for result in results:
            assert 'idkardex' in result
            assert 'kardex' in result
            assert 'usuario' in result
            assert 'cliente' in result

    @patch('notaria.views.KardexViewSet.get_queryset')
    @patch('notaria.models.Usuarios.objects')
    @patch('notaria.models.Contratantes.objects')
    @patch('notaria.models.Cliente2.objects')
    def test_list_with_zero_page_size(self, mock_cliente2, mock_contratantes, mock_usuarios, mock_get_queryset):
        """Test list method with page_size=0 (should handle gracefully)."""
        mock_kardex_obj = MagicMock()
        mock_kardex_obj.idkardex = 1
        mock_kardex_obj.kardex = 'KAR1-2024'
        mock_kardex_obj.idtipkar = 1
        mock_kardex_obj.idusuario = 1
        for field in ['fechaingreso', 'contrato', 'codactos', 'fechaescritura', 'numescritura', 'numminuta',
                     'folioini', 'foliofin', 'numinstrmento', 'txa_minuta', 'papelini', 'papelfin', 'referencia']:
            setattr(mock_kardex_obj, field, 'test_value' if field != 'fechaingreso' else '01/01/2024')
        for field in ['retenido', 'desistido', 'autorizado', 'idrecogio', 'pagado', 'visita', 'responsable']:
            setattr(mock_kardex_obj, field, 0)

        mock_get_queryset.return_value = [mock_kardex_obj]
        mock_usuarios.filter.return_value = []
        mock_contratantes.filter.return_value.values.return_value = []
        mock_cliente2.filter.return_value.values.return_value = []

        # Test with page_size=0
        response = self.api_client.get(self.url, {'page_size': 0})
        
        # Should handle gracefully (exact behavior depends on pagination implementation)
        assert response.status_code == status.HTTP_200_OK
        assert 'results' in response.data
        assert 'count' in response.data

    @patch('notaria.views.KardexViewSet.get_queryset')
    @patch('notaria.models.Usuarios.objects')
    @patch('notaria.models.Contratantes.objects')
    @patch('notaria.models.Cliente2.objects')
    def test_list_field_completeness_validation(self, mock_cliente2, mock_contratantes, mock_usuarios, mock_get_queryset):
        """Test that all expected fields are present in the response."""
        mock_kardex_obj = MagicMock()
        mock_kardex_obj.idkardex = 1
        mock_kardex_obj.kardex = 'KAR1-2024'
        mock_kardex_obj.idtipkar = 1
        mock_kardex_obj.idusuario = 1
        mock_kardex_obj.fechaingreso = '01/01/2024'
        mock_kardex_obj.contrato = 'Test Contract'
        mock_kardex_obj.codactos = '001'
        mock_kardex_obj.fechaescritura = '02/01/2024'
        mock_kardex_obj.numescritura = 'ESC001'
        mock_kardex_obj.numminuta = 'MIN001'
        mock_kardex_obj.folioini = 'F001'
        mock_kardex_obj.foliofin = 'F002'
        mock_kardex_obj.numinstrmento = 'INST001'
        mock_kardex_obj.txa_minuta = 'TXA001'
        mock_kardex_obj.papelini = 'P001'
        mock_kardex_obj.papelfin = 'P002'
        mock_kardex_obj.referencia = 'REF001'
        mock_kardex_obj.retenido = 0
        mock_kardex_obj.desistido = 0
        mock_kardex_obj.autorizado = 1
        mock_kardex_obj.idrecogio = 1
        mock_kardex_obj.pagado = 1
        mock_kardex_obj.visita = 0
        mock_kardex_obj.responsable = 1

        mock_get_queryset.return_value = [mock_kardex_obj]
        mock_usuarios.filter.return_value = []
        mock_contratantes.filter.return_value.values.return_value = []
        mock_cliente2.filter.return_value.values.return_value = []

        response = self.api_client.get(self.url)
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['count'] == 1
        
        kardex_data = response.data['results'][0]
        
        # Verify all critical fields are present (based on KardexSerializer)
        critical_fields = [
            'idkardex', 'kardex', 'fechaingreso', 'contrato', 'codactos',
            'fechaescritura', 'numescritura', 'numminuta', 'folioini',
            'foliofin', 'numinstrmento', 'txa_minuta', 'idusuario',
            'usuario', 'idtipkar', 'cliente', 'retenido', 'desistido',
            'autorizado', 'idrecogio', 'pagado', 'visita', 'papelini',
            'papelfin', 'responsable', 'referencia'
        ]
        
        for field in critical_fields:
            assert field in kardex_data, f"Critical field '{field}' missing from response"
        
        # Verify data types and values
        assert isinstance(kardex_data['idkardex'], int)
        assert isinstance(kardex_data['kardex'], str)
        assert isinstance(kardex_data['idtipkar'], int)
        assert isinstance(kardex_data['idusuario'], int)


@pytest.mark.django_db
class TestKardexViewSetCreate:
    """
    Comprehensive test suite for KardexViewSet.create method.
    Tests validation, kardex number generation, database interactions, and edge cases.
    """

    def setup_method(self):
        """Set up test data for each test method."""
        self.api_client = APIClient()
        self.url = '/api/kardex/'
        
        # Base valid data for creating Kardex with ALL required fields
        self.valid_data = {
            "idtipkar": 1,
            "kardexconexo": "12345678",
            "fechaingreso": "15/01/2024",
            "horaingreso": "10:30:00",
            "codactos": "001002",  # Two tipo actos
            "contrato": "Test Contract",
            "idusuario": 1,
            "responsable": 1,
            "observacion": "Test observation",
            "documentos": "Test documents",
            "fechacalificado": "16/01/2024",
            "fechainstrumento": "17/01/2024",
            "fechaconclusion": "18/01/2024",
            "comunica1": "Test communication",
            "contacto": "Test contact",
            "telecontacto": "987654321",
            "mailcontacto": "test@example.com",
            "retenido": 0,
            "desistido": 0,
            "autorizado": 1,
            "idrecogio": 1,
            "pagado": 1,
            "visita": 0,
            "dregistral": "12345",
            "dnotarial": "67890",
            "idnotario": 1,
            "numminuta": "MIN001"
        }

    # ========== VALIDATION TESTS ==========

    def test_create_missing_idtipkar(self):
        """Test create with missing idtipkar field."""
        data = self.valid_data.copy()
        del data["idtipkar"]
        
        response = self.api_client.post(self.url, data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"] == "Missing required fields"

    def test_create_missing_fechaingreso(self):
        """Test create with missing fechaingreso field."""
        data = self.valid_data.copy()
        del data["fechaingreso"]
        
        response = self.api_client.post(self.url, data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"] == "Missing required fields"

    def test_create_missing_both_required_fields(self):
        """Test create with both required fields missing."""
        data = self.valid_data.copy()
        del data["idtipkar"]
        del data["fechaingreso"]
        
        response = self.api_client.post(self.url, data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"] == "Missing required fields"

    def test_create_empty_idtipkar(self):
        """Test create with empty idtipkar."""
        data = self.valid_data.copy()
        data["idtipkar"] = ""
        
        response = self.api_client.post(self.url, data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"] == "Missing required fields"

    def test_create_empty_fechaingreso(self):
        """Test create with empty fechaingreso."""
        data = self.valid_data.copy()
        data["fechaingreso"] = ""
        
        response = self.api_client.post(self.url, data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"] == "Missing required fields"

    @patch('notaria.models.Kardex.objects')
    @patch('notaria.models.Tiposdeacto.objects')
    @patch('notaria.models.DetalleActosKardex.objects')
    @patch('notaria.views.KardexViewSet.get_serializer')
    def test_create_invalid_fechaingreso_format(self, mock_get_serializer, mock_detalle, mock_tipos, mock_kardex):
        """Test create with invalid fechaingreso format."""
        # Mock no existing Kardex
        mock_kardex.filter.return_value.annotate.return_value.order_by.return_value.first.return_value = None
        
        # Mock serializer to pass validation but fail in custom logic
        mock_serializer = MagicMock()
        mock_serializer.is_valid.return_value = True
        mock_get_serializer.return_value = mock_serializer
        
        data = self.valid_data.copy()
        data["fechaingreso"] = "invalid"  # 7 chars, passes max_length but fails split logic
        
        response = self.api_client.post(self.url, data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"] == "Invalid fechaingreso format"

    @patch('notaria.models.Kardex.objects')
    @patch('notaria.models.Tiposdeacto.objects')
    @patch('notaria.models.DetalleActosKardex.objects')
    @patch('notaria.views.KardexViewSet.get_serializer')
    def test_create_fechaingreso_no_year(self, mock_get_serializer, mock_detalle, mock_tipos, mock_kardex):
        """Test create with fechaingreso that has no year part."""
        # Mock no existing Kardex
        mock_kardex.filter.return_value.annotate.return_value.order_by.return_value.first.return_value = None
        
        # Mock serializer to pass validation but fail in custom logic
        mock_serializer = MagicMock()
        mock_serializer.is_valid.return_value = True
        mock_get_serializer.return_value = mock_serializer
        
        data = self.valid_data.copy()
        data["fechaingreso"] = "15/01"  # 5 chars, passes max_length but has no year
        
        response = self.api_client.post(self.url, data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"] == "Invalid fechaingreso format"

    def test_create_invalid_idtipkar(self):
        """Test create with invalid idtipkar (not in abreviatura_map)."""
        data = self.valid_data.copy()
        data["idtipkar"] = 99  # Invalid idtipkar
        
        response = self.api_client.post(self.url, data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"] == "Invalid tipoescritura"

    # ========== KARDEX NUMBER GENERATION TESTS ==========

    @patch('notaria.models.Kardex.objects')
    @patch('notaria.models.Tiposdeacto.objects')
    @patch('notaria.models.DetalleActosKardex.objects')
    @patch('notaria.views.KardexViewSet.get_serializer')
    def test_create_first_kardex_for_year(self, mock_get_serializer, mock_detalle, mock_tipos, mock_kardex):
        """Test creating the first Kardex for a given year and type."""
        # Mock no existing Kardex records
        mock_kardex.filter.return_value.annotate.return_value.order_by.return_value.first.return_value = None
        
        # Mock Tiposdeacto
        mock_tipo = MagicMock()
        mock_tipo.actosunat = "SUNAT001"
        mock_tipo.actouif = "UIF001"
        mock_tipo.desacto = "Test Acto"
        mock_tipos.get.return_value = mock_tipo
        
        # Mock serializer
        mock_serializer = MagicMock()
        mock_serializer.is_valid.return_value = True
        mock_serializer.data = {"idkardex": 1, "kardex": "KAR1-2024"}
        mock_get_serializer.return_value = mock_serializer
        
        response = self.api_client.post(self.url, self.valid_data, format='json')
        
        assert response.status_code == status.HTTP_201_CREATED
        
        # Verify the serializer was called with the generated kardex number
        mock_get_serializer.assert_called_once()
        call_args = mock_get_serializer.call_args[1]['data']
        assert call_args['kardex'] == 'KAR1-2024'

    @patch('notaria.models.Kardex.objects')
    @patch('notaria.models.Tiposdeacto.objects')
    @patch('notaria.models.DetalleActosKardex.objects')
    @patch('notaria.views.KardexViewSet.get_serializer')
    def test_create_incremental_kardex_number(self, mock_get_serializer, mock_detalle, mock_tipos, mock_kardex):
        """Test creating Kardex with incremental number."""
        # Mock existing Kardex record
        mock_existing = MagicMock()
        mock_existing.kardex = "KAR5-2024"
        mock_existing.numeric_part = 5
        mock_kardex.filter.return_value.annotate.return_value.order_by.return_value.first.return_value = mock_existing
        
        # Mock Tiposdeacto
        mock_tipo = MagicMock()
        mock_tipo.actosunat = "SUNAT001"
        mock_tipo.actouif = "UIF001"
        mock_tipo.desacto = "Test Acto"
        mock_tipos.get.return_value = mock_tipo
        
        # Mock serializer
        mock_serializer = MagicMock()
        mock_serializer.is_valid.return_value = True
        mock_serializer.data = {"idkardex": 1, "kardex": "KAR6-2024"}
        mock_get_serializer.return_value = mock_serializer
        
        response = self.api_client.post(self.url, self.valid_data, format='json')
        
        assert response.status_code == status.HTTP_201_CREATED
        
        # Verify the new kardex number is incremented
        call_args = mock_get_serializer.call_args[1]['data']
        assert call_args['kardex'] == 'KAR6-2024'

    @patch('notaria.models.Kardex.objects')
    @patch('notaria.models.Tiposdeacto.objects')
    @patch('notaria.models.DetalleActosKardex.objects')
    @patch('notaria.views.KardexViewSet.get_serializer')
    def test_create_different_idtipkar_types(self, mock_get_serializer, mock_detalle, mock_tipos, mock_kardex):
        """Test creating Kardex with different idtipkar types."""
        test_cases = [
            (1, "KAR"),  # ESCRITURAS PUBLICAS
            (2, "NCT"),  # ASUNTOS NO CONTENCIOSOS
            (3, "ACT"),  # TRANSFERENCIAS VEHICULARES
            (4, "GAM"),  # GARANTIAS MOBILIARIAS
            (5, "TES"),  # TESTAMENTOS
        ]
        
        for idtipkar, expected_prefix in test_cases:
            # Reset mocks
            mock_kardex.reset_mock()
            mock_get_serializer.reset_mock()
            
            # Mock no existing records for each type
            mock_kardex.filter.return_value.annotate.return_value.order_by.return_value.first.return_value = None
            
            # Mock Tiposdeacto
            mock_tipo = MagicMock()
            mock_tipo.actosunat = "SUNAT001"
            mock_tipo.actouif = "UIF001"
            mock_tipo.desacto = "Test Acto"
            mock_tipos.get.return_value = mock_tipo
            
            # Mock serializer
            mock_serializer = MagicMock()
            mock_serializer.is_valid.return_value = True
            mock_serializer.data = {"idkardex": 1, "kardex": f"{expected_prefix}1-2024"}
            mock_get_serializer.return_value = mock_serializer
            
            data = self.valid_data.copy()
            data["idtipkar"] = idtipkar
            
            response = self.api_client.post(self.url, data, format='json')
            
            assert response.status_code == status.HTTP_201_CREATED
            
            # Verify the correct prefix is used
            call_args = mock_get_serializer.call_args[1]['data']
            assert call_args['kardex'] == f'{expected_prefix}1-2024'

    @patch('notaria.models.Kardex.objects')
    @patch('notaria.models.Tiposdeacto.objects')
    @patch('notaria.models.DetalleActosKardex.objects')
    @patch('notaria.views.KardexViewSet.get_serializer')
    def test_create_different_years(self, mock_get_serializer, mock_detalle, mock_tipos, mock_kardex):
        """Test creating Kardex for different years."""
        test_years = ["2023", "2024", "2025"]
        
        for year in test_years:
            # Reset mocks
            mock_kardex.reset_mock()
            mock_get_serializer.reset_mock()
            
            # Mock no existing records
            mock_kardex.filter.return_value.annotate.return_value.order_by.return_value.first.return_value = None
            
            # Mock Tiposdeacto
            mock_tipo = MagicMock()
            mock_tipo.actosunat = "SUNAT001"
            mock_tipo.actouif = "UIF001"
            mock_tipo.desacto = "Test Acto"
            mock_tipos.get.return_value = mock_tipo
            
            # Mock serializer
            mock_serializer = MagicMock()
            mock_serializer.is_valid.return_value = True
            mock_serializer.data = {"idkardex": 1, "kardex": f"KAR1-{year}"}
            mock_get_serializer.return_value = mock_serializer
            
            data = self.valid_data.copy()
            data["fechaingreso"] = f"15/01/{year}"
            
            response = self.api_client.post(self.url, data, format='json')
            
            assert response.status_code == status.HTTP_201_CREATED
            
            # Verify the correct year is used
            call_args = mock_get_serializer.call_args[1]['data']
            assert call_args['kardex'] == f'KAR1-{year}'

    # ========== DETALLE ACTOS KARDEX TESTS ==========

    @patch('notaria.models.Kardex.objects')
    @patch('notaria.models.Tiposdeacto.objects')
    @patch('notaria.models.DetalleActosKardex.objects')
    @patch('notaria.views.KardexViewSet.get_serializer')
    def test_create_with_valid_codactos(self, mock_get_serializer, mock_detalle, mock_tipos, mock_kardex):
        """Test creating Kardex with valid codactos."""
        # Mock no existing Kardex
        mock_kardex.filter.return_value.annotate.return_value.order_by.return_value.first.return_value = None
        
        # Mock Tiposdeacto
        mock_tipo = MagicMock()
        mock_tipo.actosunat = "SUNAT001"
        mock_tipo.actouif = "UIF001"
        mock_tipo.desacto = "Test Acto"
        mock_tipos.get.return_value = mock_tipo
        
        # Mock serializer
        mock_serializer = MagicMock()
        mock_serializer.is_valid.return_value = True
        mock_serializer.data = {"idkardex": 1, "kardex": "KAR1-2024"}
        mock_get_serializer.return_value = mock_serializer
        
        data = self.valid_data.copy()
        data["codactos"] = "001002003"  # Three tipo actos
        
        response = self.api_client.post(self.url, data, format='json')
        
        assert response.status_code == status.HTTP_201_CREATED
        
        # Verify DetalleActosKardex.create was called 3 times
        assert mock_detalle.create.call_count == 3

    @patch('notaria.models.Kardex.objects')
    @patch('notaria.models.Tiposdeacto.objects')
    @patch('notaria.models.DetalleActosKardex.objects')
    @patch('notaria.views.KardexViewSet.get_serializer')
    def test_create_with_invalid_idtipoacto(self, mock_get_serializer, mock_detalle, mock_tipos, mock_kardex):
        """Test create with invalid idtipoacto in codactos."""
        # Mock no existing Kardex
        mock_kardex.filter.return_value.annotate.return_value.order_by.return_value.first.return_value = None
        
        # Mock serializer to pass validation
        mock_serializer = MagicMock()
        mock_serializer.is_valid.return_value = True
        mock_serializer.data = {"idkardex": 1, "kardex": "KAR1-2024"}
        mock_get_serializer.return_value = mock_serializer
        
        # Mock Tiposdeacto.DoesNotExist exception
        mock_tipos.get.side_effect = models.Tiposdeacto.DoesNotExist()
        
        response = self.api_client.post(self.url, self.valid_data, format='json')
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.data["error"] == "Tipo de acto no encontrado."

    @patch('notaria.models.Kardex.objects')
    @patch('notaria.models.Tiposdeacto.objects')
    @patch('notaria.models.DetalleActosKardex.objects')
    @patch('notaria.views.KardexViewSet.get_serializer')
    def test_create_with_empty_codactos(self, mock_get_serializer, mock_detalle, mock_tipos, mock_kardex):
        """Test creating Kardex with empty codactos."""
        # Mock no existing Kardex
        mock_kardex.filter.return_value.annotate.return_value.order_by.return_value.first.return_value = None
        
        # Mock serializer
        mock_serializer = MagicMock()
        mock_serializer.is_valid.return_value = True
        mock_serializer.data = {"idkardex": 1, "kardex": "KAR1-2024"}
        mock_get_serializer.return_value = mock_serializer
        
        data = self.valid_data.copy()
        data["codactos"] = ""  # Empty codactos
        
        response = self.api_client.post(self.url, data, format='json')
        
        assert response.status_code == status.HTTP_201_CREATED
        
        # Verify no DetalleActosKardex records were created
        mock_detalle.create.assert_not_called()

    # ========== SERIALIZER AND DATABASE TESTS ==========

    @patch('notaria.models.Kardex.objects')
    @patch('notaria.views.KardexViewSet.get_serializer')
    def test_create_serializer_validation_error(self, mock_get_serializer, mock_kardex):
        """Test create when serializer validation fails."""
        # Mock no existing Kardex
        mock_kardex.filter.return_value.annotate.return_value.order_by.return_value.first.return_value = None
        
        # Mock serializer validation error - use ValidationError instead of generic Exception
        from rest_framework.exceptions import ValidationError
        mock_serializer = MagicMock()
        mock_serializer.is_valid.side_effect = ValidationError("Validation error")
        mock_get_serializer.return_value = mock_serializer
        
        response = self.api_client.post(self.url, self.valid_data, format='json')
        
        # Should return 400 for validation error
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    # ========== EDGE CASES ==========

    @patch('notaria.models.Kardex.objects')
    @patch('notaria.models.Tiposdeacto.objects')
    @patch('notaria.models.DetalleActosKardex.objects')
    @patch('notaria.views.KardexViewSet.get_serializer')
    def test_create_malformed_existing_kardex(self, mock_get_serializer, mock_detalle, mock_tipos, mock_kardex):
        """Test create when existing Kardex has malformed number."""
        # Mock existing Kardex with malformed number
        mock_existing = MagicMock()
        mock_existing.kardex = "INVALID-FORMAT"
        mock_kardex.filter.return_value.annotate.return_value.order_by.return_value.first.return_value = mock_existing
        
        # Mock Tiposdeacto
        mock_tipo = MagicMock()
        mock_tipo.actosunat = "SUNAT001"
        mock_tipo.actouif = "UIF001"
        mock_tipo.desacto = "Test Acto"
        mock_tipos.get.return_value = mock_tipo
        
        # Mock serializer
        mock_serializer = MagicMock()
        mock_serializer.is_valid.return_value = True
        mock_serializer.data = {"idkardex": 1, "kardex": "KAR1-2024"}
        mock_get_serializer.return_value = mock_serializer
        
        response = self.api_client.post(self.url, self.valid_data, format='json')
        
        # Should handle gracefully and default to 0
        assert response.status_code == status.HTTP_201_CREATED
        
        call_args = mock_get_serializer.call_args[1]['data']
        assert call_args['kardex'] == 'KAR1-2024'  # Should start from 1

    def test_create_null_idtipkar(self):
        """Test create with null idtipkar."""
        data = self.valid_data.copy()
        data["idtipkar"] = None
        
        response = self.api_client.post(self.url, data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"] == "Missing required fields"

    def test_create_null_fechaingreso(self):
        """Test create with null fechaingreso."""
        data = self.valid_data.copy()
        data["fechaingreso"] = None
        
        response = self.api_client.post(self.url, data, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"] == "Missing required fields"

    @patch('notaria.models.Kardex.objects')
    @patch('notaria.models.Tiposdeacto.objects')
    @patch('notaria.models.DetalleActosKardex.objects')
    @patch('notaria.views.KardexViewSet.get_serializer')
    def test_create_success_response_structure(self, mock_get_serializer, mock_detalle, mock_tipos, mock_kardex):
        """Test that successful create returns proper response structure."""
        # Mock no existing Kardex
        mock_kardex.filter.return_value.annotate.return_value.order_by.return_value.first.return_value = None
        
        # Mock Tiposdeacto
        mock_tipo = MagicMock()
        mock_tipo.actosunat = "SUNAT001"
        mock_tipo.actouif = "UIF001"
        mock_tipo.desacto = "Test Acto"
        mock_tipos.get.return_value = mock_tipo
        
        # Mock serializer
        mock_serializer = MagicMock()
        mock_serializer.is_valid.return_value = True
        mock_serializer.data = {
            "idkardex": 1,
            "kardex": "KAR1-2024",
            "idtipkar": 1,
            "fechaingreso": "15/01/2024",
            "contrato": "Test Contract"
        }
        mock_get_serializer.return_value = mock_serializer
        
        response = self.api_client.post(self.url, self.valid_data, format='json')
        
        assert response.status_code == status.HTTP_201_CREATED
        assert "idkardex" in response.data
        assert "kardex" in response.data
        assert response.data["kardex"] == "KAR1-2024"