"""API views for legal knowledge-base workflows."""

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    KbIngestionJob,
    LegalCase,
    LegalClause,
    LegalDocument,
    LegalKnowledgeEmbedding,
    LegalRetrievalLog,
    LegalTemplate,
)
from .permissions import IsLegalKbAdmin, IsLegalKbReader
from .serializers import (
    KbIngestionJobSerializer,
    LegalCaseSerializer,
    LegalClauseSerializer,
    LegalDocumentSerializer,
    LegalKnowledgeEmbeddingSerializer,
    LegalRetrievalLogSerializer,
    LegalRetrieveSerializer,
    LegalTemplateSerializer,
)
from .services.ingestion_service import LegalKbIngestionService
from .services.rag_answer_service import RagAnswerService
from .services.retrieval_service import LegalRetrievalService


class LegalKbPermissionMixin:
    """Use admin permissions for writes and reader permissions for reads."""

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy', 'ingest']:
            return [IsLegalKbAdmin()]
        return [IsLegalKbReader()]


class LegalDocumentViewSet(LegalKbPermissionMixin, viewsets.ModelViewSet):
    """Manage legal documents."""

    queryset = LegalDocument.objects.select_related('created_by').prefetch_related('clauses')
    serializer_class = LegalDocumentSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'])
    def ingest(self, request, pk=None):
        document = self.get_object()
        job = LegalKbIngestionService().ingest_document(document, actor=request.user)
        return Response(KbIngestionJobSerializer(job).data, status=status.HTTP_201_CREATED)


class LegalClauseViewSet(LegalKbPermissionMixin, viewsets.ModelViewSet):
    """Browse and manage legal clauses."""

    queryset = LegalClause.objects.select_related('document')
    serializer_class = LegalClauseSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        document_id = self.request.query_params.get('document')
        search = self.request.query_params.get('search')
        if document_id:
            queryset = queryset.filter(document_id=document_id)
        if search:
            queryset = queryset.filter(text__icontains=search)
        return queryset


class LegalCaseViewSet(LegalKbPermissionMixin, viewsets.ModelViewSet):
    """Browse and manage legal cases."""

    queryset = LegalCase.objects.select_related('related_document')
    serializer_class = LegalCaseSerializer


class LegalTemplateViewSet(LegalKbPermissionMixin, viewsets.ModelViewSet):
    """Browse and manage legal templates."""

    queryset = LegalTemplate.objects.all()
    serializer_class = LegalTemplateSerializer


class LegalKnowledgeEmbeddingViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only embedding chunk API."""

    queryset = LegalKnowledgeEmbedding.objects.all()
    serializer_class = LegalKnowledgeEmbeddingSerializer
    permission_classes = [IsLegalKbReader]


class KbIngestionJobViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only ingestion job API."""

    queryset = KbIngestionJob.objects.select_related('document', 'created_by')
    serializer_class = KbIngestionJobSerializer
    permission_classes = [IsLegalKbReader]


class LegalRetrievalLogViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only retrieval log API."""

    queryset = LegalRetrievalLog.objects.select_related('user')
    serializer_class = LegalRetrievalLogSerializer
    permission_classes = [IsLegalKbAdmin]


class LegalRetrieveView(APIView):
    """RAG endpoint that synthesizes retrieved knowledge before returning it."""

    permission_classes = [IsLegalKbReader]

    def post(self, request):
        serializer = LegalRetrieveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = RagAnswerService().answer(
            query=serializer.validated_data['query'],
            top_k=serializer.validated_data.get('top_k', 8),
            filters=serializer.validated_data.get('filters') or {},
            user=request.user,
            include_raw=(
                serializer.validated_data.get('include_raw', False)
                and (request.user.is_staff or getattr(request.user, 'role', '') == 'admin')
            ),
        )
        return Response(payload)
