import pytest
from rest_framework import status

@pytest.mark.django_db
class TestKardex:
    pass
    # def test_kardex_list(self, api_client):
    #     """
    #     Test the list view of Kardex.
    #     """
    #     response = api_client.get('/notaria/kardex/')
    #     assert response.status_code == status.HTTP_200_OK
    #     assert isinstance(response.data, list)

    # def test_kardex_create(self, api_client):
    #     """
    #     Test the create view of Kardex.
    #     """
    #     data = {
    #         'field1': 'value1',
    #         'field2': 'value2',
    #         # Add other required fields here
    #     }
    #     response = api_client.post('/notaria/kardex/', data)
    #     assert response.status_code == status.HTTP_201_CREATED