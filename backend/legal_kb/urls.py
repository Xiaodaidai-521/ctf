"""Legal knowledge-base API routes."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    KbIngestionJobViewSet,
    LegalCaseViewSet,
    LegalClauseViewSet,
    LegalDocumentViewSet,
    LegalKnowledgeEmbeddingViewSet,
    LegalRetrievalLogViewSet,
    LegalRetrieveView,
    LegalTemplateViewSet,
)

router = DefaultRouter()
router.register(r'documents', LegalDocumentViewSet, basename='legal-kb-document')
router.register(r'clauses', LegalClauseViewSet, basename='legal-kb-clause')
router.register(r'cases', LegalCaseViewSet, basename='legal-kb-case')
router.register(r'templates', LegalTemplateViewSet, basename='legal-kb-template')
router.register(r'embeddings', LegalKnowledgeEmbeddingViewSet, basename='legal-kb-embedding')
router.register(r'ingestion-jobs', KbIngestionJobViewSet, basename='legal-kb-ingestion-job')
router.register(r'retrieval-logs', LegalRetrievalLogViewSet, basename='legal-kb-retrieval-log')

urlpatterns = [
    path('', include(router.urls)),
    path('retrieve/', LegalRetrieveView.as_view(), name='legal-kb-retrieve'),
]
