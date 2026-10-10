from django.urls import path

from .views import DocumentIngestionView

urlpatterns = [
    path('documents/', DocumentIngestionView.as_view(), name='rag-ingestion-documents'),
]
