from rest_framework.response import Response

from taxes.services.document_lookup import document_lookup_context


class DocumentReadViewSetMixin:
    read_serializer_class = None

    def get_read_serializer_class(self):
        return self.read_serializer_class

    def _read_serializer(self, documents, *, many: bool):
        items = documents if many else [documents]
        context = {
            **self.get_serializer_context(),
            **document_lookup_context(items),
        }
        serializer_class = self.get_read_serializer_class()
        return serializer_class(documents, many=many, context=context)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self._read_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self._read_serializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self._read_serializer(instance, many=False)
        return Response(serializer.data)
