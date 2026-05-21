"""
UIF module API views (Phase 1).
"""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from notaria import pagination
from uif.services.dashboard_service import UifDashboardService


class UifErrorsDashboardView(APIView):
    """
    UIF error dashboard — RoClass loadData staging + validation.

    Query params: initialDate, finalDate, type (errors|ro|no_envian), page, page_size.
    """

    # permission_classes = [IsAuthenticated]
    pagination_class = pagination.KardexPagination

    def get(self, request):
        paginator = self.pagination_class()
        service = UifDashboardService()

        def paginate_fn(queryset):
            return paginator.paginate_queryset(queryset, request, view=self)

        def get_paginated_response_fn(data):
            return paginator.get_paginated_response(data)

        return service.build_response(request, paginate_fn, get_paginated_response_fn)
