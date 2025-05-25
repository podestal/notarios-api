from rest_framework.pagination import PageNumberPagination

"""
Pagination for the Notaria app.
This file defines the pagination for the Notaria app.
"""


class KardexPagination(PageNumberPagination):
    """
    Pagination class for the Kardex viewset.
    This class defines the pagination for the Kardex viewset.
    It uses page number pagination.
    """
    page_size = 10
    page_query_param = 'page'
    page_size_query_param = 'page_size'
    max_page_size = 100
