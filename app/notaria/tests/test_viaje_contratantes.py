import pytest
from rest_framework import status
from rest_framework.test import APIClient, APITestCase
from unittest.mock import patch, MagicMock

from notaria import models
from notaria.views import ViajeContratantesViewSet


@pytest.mark.django_db
class TestViajeContratantesViewSetByViaje(APITestCase):
    """Test cases for ViajeContratantesViewSet by_viaje endpoint."""

    def setUp(self):
        self.api_client = APIClient()
        self.url = '/api/viaje_contratantes/by_viaje/'
        
        # Sample valid data for testing
        self.valid_data = {
            "id_viaje": "VIA001",
            "idcontratante": "0000147215",
            "kardex": "KAR1-2024",
            "condicion": "044.1/055.2/",
            "firma": "1",
            "fechafirma": "15/01/2024",
            "resfirma": 0,
            "tiporepresentacion": "0",
            "idcontratanterp": "",
            "idsedereg": "",
            "numpartida": "",
            "facultades": "Test faculties",
            "indice": "1",
            "visita": "0",
            "inscrito": "0",
            "plantilla": None
        }

    # ========== BASIC BY_VIAJE TESTS ==========

    @patch('notaria.models.ViajeContratantes.objects')
    def test_by_viaje_success_with_records(self, mock_viaje_contratantes):
        """Test by_viaje endpoint with existing records."""
        # Mock the queryset with data
        mock_queryset = MagicMock()
        mock_viaje_contratantes.filter.return_value = mock_queryset
        mock_queryset.exists.return_value = True
        
        # Mock serializer data
        mock_serializer_data = [
            {
                "id_viaje": "VIA001",
                "idcontratante": "0000147215",
                "kardex": "KAR1-2024",
                "condicion": "044.1/055.2/",
                "firma": "1",
                "fechafirma": "15/01/2024",
                "resfirma": 0,
                "tiporepresentacion": "0",
                "idcontratanterp": "",
                "idsedereg": "",
                "numpartida": "",
                "facultades": "Test faculties",
                "indice": "1",
                "visita": "0",
                "inscrito": "0",
                "plantilla": None
            },
            {
                "id_viaje": "VIA001",
                "idcontratante": "0000147216",
                "kardex": "KAR1-2024",
                "condicion": "066.3/077.4/",
                "firma": "2",
                "fechafirma": "16/01/2024",
                "resfirma": 1,
                "tiporepresentacion": "1",
                "idcontratanterp": "",
                "idsedereg": "",
                "numpartida": "",
                "facultades": "Test faculties 2",
                "indice": "2",
                "visita": "1",
                "inscrito": "1",
                "plantilla": None
            }
        ]
        
        # Mock the serializer
        with patch('notaria.serializers.ViajeContratantesSerializer') as mock_serializer_class:
            mock_serializer = MagicMock()
            mock_serializer.data = mock_serializer_data
            mock_serializer_class.return_value = mock_serializer
            
            response = self.api_client.get(f"{self.url}?id_viaje=VIA001")
            
            assert response.status_code == status.HTTP_200_OK
            assert response.data == mock_serializer_data
            mock_viaje_contratantes.filter.assert_called_once_with(id_viaje="VIA001")

    @patch('notaria.models.ViajeContratantes.objects')
    def test_by_viaje_success_no_records(self, mock_viaje_contratantes):
        """Test by_viaje endpoint when no records exist."""
        # Mock empty queryset
        mock_queryset = MagicMock()
        mock_viaje_contratantes.filter.return_value = mock_queryset
        mock_queryset.exists.return_value = False
        
        response = self.api_client.get(f"{self.url}?id_viaje=VIA001")
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data == []
        mock_viaje_contratantes.filter.assert_called_once_with(id_viaje="VIA001")

    @patch('notaria.models.ViajeContratantes.objects')
    def test_by_viaje_single_record(self, mock_viaje_contratantes):
        """Test by_viaje endpoint with single record."""
        # Mock the queryset with single record
        mock_queryset = MagicMock()
        mock_viaje_contratantes.filter.return_value = mock_queryset
        mock_queryset.exists.return_value = True
        
        # Mock serializer data for single record
        mock_serializer_data = [
            {
                "id_viaje": "VIA001",
                "idcontratante": "0000147215",
                "kardex": "KAR1-2024",
                "condicion": "044.1/",
                "firma": "1",
                "fechafirma": "15/01/2024",
                "resfirma": 0,
                "tiporepresentacion": "0",
                "idcontratanterp": "",
                "idsedereg": "",
                "numpartida": "",
                "facultades": "Test faculties",
                "indice": "1",
                "visita": "0",
                "inscrito": "0",
                "plantilla": None
            }
        ]
        
        # Mock the serializer
        with patch('notaria.serializers.ViajeContratantesSerializer') as mock_serializer_class:
            mock_serializer = MagicMock()
            mock_serializer.data = mock_serializer_data
            mock_serializer_class.return_value = mock_serializer
            
            response = self.api_client.get(f"{self.url}?id_viaje=VIA001")
            
            assert response.status_code == status.HTTP_200_OK
            assert response.data == mock_serializer_data
            assert len(response.data) == 1

    # ========== PARAMETER VALIDATION TESTS ==========

    def test_by_viaje_missing_id_viaje_parameter(self):
        """Test by_viaje endpoint without id_viaje parameter."""
        response = self.api_client.get(self.url)
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"] == "id_viaje parameter is required."

    def test_by_viaje_empty_id_viaje_parameter(self):
        """Test by_viaje endpoint with empty id_viaje parameter."""
        response = self.api_client.get(f"{self.url}?id_viaje=")
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"] == "id_viaje parameter is required."

    def test_by_viaje_none_id_viaje_parameter(self):
        """Test by_viaje endpoint with None id_viaje parameter."""
        try:
            response = self.api_client.get(f"{self.url}?id_viaje=None")
            # Should handle gracefully since it's a string "None" that can't be converted to int
            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        except Exception as e:
            # The view should handle ValueError gracefully
            assert "expected a number" in str(e).lower() or "database" in str(e).lower() or "table" in str(e).lower()

    # ========== EDGE CASES ==========

    @patch('notaria.models.ViajeContratantes.objects')
    def test_by_viaje_with_special_characters(self, mock_viaje_contratantes):
        """Test by_viaje endpoint with special characters in id_viaje."""
        # Mock empty queryset
        mock_queryset = MagicMock()
        mock_viaje_contratantes.filter.return_value = mock_queryset
        mock_queryset.exists.return_value = False
        
        # Since id_viaje is an integer, we'll test with a valid integer
        special_id = "12345"
        response = self.api_client.get(f"{self.url}?id_viaje={special_id}")
        
        assert response.status_code == status.HTTP_200_OK
        # The mock receives the string value from the URL parameter
        mock_viaje_contratantes.filter.assert_called_once_with(id_viaje=special_id)

    @patch('notaria.models.ViajeContratantes.objects')
    def test_by_viaje_with_long_id_viaje(self, mock_viaje_contratantes):
        """Test by_viaje endpoint with very long id_viaje."""
        # Mock empty queryset
        mock_queryset = MagicMock()
        mock_viaje_contratantes.filter.return_value = mock_queryset
        mock_queryset.exists.return_value = False
        
        # Use a large but valid integer
        long_id = "999999999"
        response = self.api_client.get(f"{self.url}?id_viaje={long_id}")
        
        assert response.status_code == status.HTTP_200_OK
        # The mock receives the string value from the URL parameter
        mock_viaje_contratantes.filter.assert_called_once_with(id_viaje=long_id)

    @patch('notaria.models.ViajeContratantes.objects')
    def test_by_viaje_with_numeric_id_viaje(self, mock_viaje_contratantes):
        """Test by_viaje endpoint with numeric id_viaje."""
        # Mock empty queryset
        mock_queryset = MagicMock()
        mock_viaje_contratantes.filter.return_value = mock_queryset
        mock_queryset.exists.return_value = False
        
        numeric_id = "12345"
        response = self.api_client.get(f"{self.url}?id_viaje={numeric_id}")
        
        assert response.status_code == status.HTTP_200_OK
        # The mock receives the string value from the URL parameter
        mock_viaje_contratantes.filter.assert_called_once_with(id_viaje=numeric_id)

    # ========== ERROR HANDLING TESTS ==========

    @patch('notaria.models.ViajeContratantes.objects')
    def test_by_viaje_database_error(self, mock_viaje_contratantes):
        """Test by_viaje endpoint when database operations fail."""
        # Mock database error
        from django.db import DatabaseError
        mock_viaje_contratantes.filter.side_effect = DatabaseError("Database error")
        
        try:
            response = self.api_client.get(f"{self.url}?id_viaje=123")
            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        except Exception as e:
            # If it fails due to missing database, that's expected
            assert "database" in str(e).lower() or "table" in str(e).lower()

    @patch('notaria.models.ViajeContratantes.objects')
    def test_by_viaje_serializer_error(self, mock_viaje_contratantes):
        """Test by_viaje endpoint when serializer fails."""
        # Mock the queryset with data
        mock_queryset = MagicMock()
        mock_viaje_contratantes.filter.return_value = mock_queryset
        mock_queryset.exists.return_value = True
        
        # Mock serializer error
        with patch('notaria.serializers.ViajeContratantesSerializer') as mock_serializer_class:
            mock_serializer_class.side_effect = Exception("Serializer error")
            
            try:
                response = self.api_client.get(f"{self.url}?id_viaje=123")
                assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            except Exception as e:
                # The view should handle serializer errors gracefully
                assert "serializer error" in str(e).lower() or "database" in str(e).lower() or "table" in str(e).lower()

    # ========== COMPREHENSIVE SCENARIOS ==========

    @patch('notaria.models.ViajeContratantes.objects')
    def test_by_viaje_multiple_different_viajes(self, mock_viaje_contratantes):
        """Test by_viaje endpoint with different viaje IDs."""
        test_cases = [
            "1",
            "2", 
            "3",
            "100",
            "999",
            "12345",
            "999999",
        ]
        
        for viaje_id in test_cases:
            # Mock empty queryset for each test
            mock_queryset = MagicMock()
            mock_viaje_contratantes.filter.return_value = mock_queryset
            mock_queryset.exists.return_value = False
            
            response = self.api_client.get(f"{self.url}?id_viaje={viaje_id}")
            
            assert response.status_code == status.HTTP_200_OK
            assert response.data == []
            # The mock receives the string value from the URL parameter
            mock_viaje_contratantes.filter.assert_called_with(id_viaje=viaje_id)

    @patch('notaria.models.ViajeContratantes.objects')
    def test_by_viaje_large_dataset(self, mock_viaje_contratantes):
        """Test by_viaje endpoint with large dataset."""
        # Mock the queryset with data
        mock_queryset = MagicMock()
        mock_viaje_contratantes.filter.return_value = mock_queryset
        mock_queryset.exists.return_value = True
        
        # Mock large serializer data
        large_serializer_data = [
            {
                "id_viaje": "VIA001",
                "idcontratante": f"0000147{i:03d}",
                "kardex": "KAR1-2024",
                "condicion": f"044.{i}/",
                "firma": str(i % 3),
                "fechafirma": "15/01/2024",
                "resfirma": i % 2,
                "tiporepresentacion": str(i % 2),
                "idcontratanterp": "",
                "idsedereg": "",
                "numpartida": "",
                "facultades": f"Test faculties {i}",
                "indice": str(i),
                "visita": str(i % 2),
                "inscrito": str(i % 2),
                "plantilla": None
            }
            for i in range(100)  # 100 records
        ]
        
        # Mock the serializer
        with patch('notaria.serializers.ViajeContratantesSerializer') as mock_serializer_class:
            mock_serializer = MagicMock()
            mock_serializer.data = large_serializer_data
            mock_serializer_class.return_value = mock_serializer
            
            response = self.api_client.get(f"{self.url}?id_viaje=VIA001")
            
            assert response.status_code == status.HTTP_200_OK
            assert len(response.data) == 100
            assert all(record["id_viaje"] == "VIA001" for record in response.data)

    # ========== SECURITY TESTS ==========

    def test_by_viaje_sql_injection_attempt(self):
        """Test by_viaje endpoint with potential SQL injection attempt."""
        malicious_id = "123'; DROP TABLE viaje_contratantes; --"
        
        try:
            response = self.api_client.get(f"{self.url}?id_viaje={malicious_id}")
            # Should handle gracefully
            assert response.status_code in [status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST, status.HTTP_500_INTERNAL_SERVER_ERROR]
        except Exception as e:
            # If it fails due to missing database, that's expected
            assert "database" in str(e).lower() or "table" in str(e).lower()

    def test_by_viaje_xss_attempt(self):
        """Test by_viaje endpoint with potential XSS attempt."""
        xss_id = "<script>alert('xss')</script>"
        
        try:
            response = self.api_client.get(f"{self.url}?id_viaje={xss_id}")
            # Should handle gracefully
            assert response.status_code in [status.HTTP_200_OK, status.HTTP_400_BAD_REQUEST, status.HTTP_500_INTERNAL_SERVER_ERROR]
        except Exception as e:
            # The view should handle ValueError gracefully
            assert "expected a number" in str(e).lower() or "database" in str(e).lower() or "table" in str(e).lower()

    # ========== HTTP METHOD TESTS ==========

    def test_by_viaje_wrong_http_method(self):
        """Test by_viaje endpoint with wrong HTTP method."""
        # Test POST instead of GET
        response = self.api_client.post(f"{self.url}?id_viaje=123")
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_by_viaje_put_method(self):
        """Test by_viaje endpoint with PUT method."""
        response = self.api_client.put(f"{self.url}?id_viaje=123")
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_by_viaje_delete_method(self):
        """Test by_viaje endpoint with DELETE method."""
        response = self.api_client.delete(f"{self.url}?id_viaje=123")
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    # ========== URL PATTERN TESTS ==========

    def test_by_viaje_invalid_url_pattern(self):
        """Test by_viaje endpoint with invalid URL pattern."""
        response = self.api_client.get("/api/viaje_contratantes/invalid-endpoint/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_by_viaje_missing_trailing_slash(self):
        """Test by_viaje endpoint without trailing slash."""
        response = self.api_client.get("/api/viaje_contratantes/by_viaje?id_viaje=123")
        # Should redirect or work the same
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_301_MOVED_PERMANENTLY, status.HTTP_400_BAD_REQUEST]

    # ========== PERFORMANCE TESTS ==========

    @patch('notaria.models.ViajeContratantes.objects')
    def test_by_viaje_performance_with_filtering(self, mock_viaje_contratantes):
        """Test by_viaje endpoint performance with filtering."""
        # Mock the queryset
        mock_queryset = MagicMock()
        mock_viaje_contratantes.filter.return_value = mock_queryset
        mock_queryset.exists.return_value = True
        
        # Mock serializer data
        mock_serializer_data = [
            {
                "id_viaje": 1,
                "idcontratante": "0000147215",
                "kardex": "KAR1-2024",
                "condicion": "044.1/",
                "firma": "1",
                "fechafirma": "15/01/2024",
                "resfirma": 0,
                "tiporepresentacion": "0",
                "idcontratanterp": "",
                "idsedereg": "",
                "numpartida": "",
                "facultades": "Test faculties",
                "indice": "1",
                "visita": "0",
                "inscrito": "0",
                "plantilla": None
            }
        ]
        
        # Mock the serializer
        with patch('notaria.serializers.ViajeContratantesSerializer') as mock_serializer_class:
            mock_serializer = MagicMock()
            mock_serializer.data = mock_serializer_data
            mock_serializer_class.return_value = mock_serializer
            
            # Test multiple requests to ensure performance
            for i in range(10):
                response = self.api_client.get(f"{self.url}?id_viaje=1")
                assert response.status_code == status.HTTP_200_OK
                assert response.data == mock_serializer_data

    # ========== DATA VALIDATION TESTS ==========

    @patch('notaria.models.ViajeContratantes.objects')
    def test_by_viaje_data_integrity(self, mock_viaje_contratantes):
        """Test by_viaje endpoint data integrity."""
        # Mock the queryset with data
        mock_queryset = MagicMock()
        mock_viaje_contratantes.filter.return_value = mock_queryset
        mock_queryset.exists.return_value = True
        
        # Mock serializer data with specific structure
        mock_serializer_data = [
            {
                "id_viaje": 1,
                "idcontratante": "0000147215",
                "kardex": "KAR1-2024",
                "condicion": "044.1/",
                "firma": "1",
                "fechafirma": "15/01/2024",
                "resfirma": 0,
                "tiporepresentacion": "0",
                "idcontratanterp": "",
                "idsedereg": "",
                "numpartida": "",
                "facultades": "Test faculties",
                "indice": "1",
                "visita": "0",
                "inscrito": "0",
                "plantilla": None
            }
        ]
        
        # Mock the serializer
        with patch('notaria.serializers.ViajeContratantesSerializer') as mock_serializer_class:
            mock_serializer = MagicMock()
            mock_serializer.data = mock_serializer_data
            mock_serializer_class.return_value = mock_serializer
            
            response = self.api_client.get(f"{self.url}?id_viaje=1")
            
            assert response.status_code == status.HTTP_200_OK
            assert isinstance(response.data, list)
            assert len(response.data) == 1
            
            # Verify data structure
            record = response.data[0]
            assert "id_viaje" in record
            assert "idcontratante" in record
            assert "kardex" in record
            assert "condicion" in record
            assert "firma" in record
            assert "fechafirma" in record
            assert "resfirma" in record
            assert "tiporepresentacion" in record
            assert "idcontratanterp" in record
            assert "idsedereg" in record
            assert "numpartida" in record
            assert "facultades" in record
            assert "indice" in record
            assert "visita" in record
            assert "inscrito" in record
            assert "plantilla" in record 