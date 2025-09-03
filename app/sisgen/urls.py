# sisgen_service/urls.py
from django.urls import path
from .views import DocumentSearchView, SendToSISGENView, search_books

app_name = 'sisgen_service'

urlpatterns = [
    path('search/', DocumentSearchView.as_view(), name='document_search'),
    path('send-sisgen/', SendToSISGENView.as_view(), name='send_sisgen'),
    path('books/search/', search_books, name='search_books'),
]