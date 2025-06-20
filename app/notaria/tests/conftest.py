import pytest
from model_bakery import baker
from rest_framework.test import APIClient

@pytest.fixture
def api_client():
    """Fixture to create an APIClient instance."""
    return APIClient()