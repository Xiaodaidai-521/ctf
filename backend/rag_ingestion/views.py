"""Admin-only ingestion API. Uploads require staff privileges by design."""

import logging

from django.conf import settings
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import DocumentSource
from .serializers import DocumentSourceSerializer
from .services import IngestionService

logger = logging.getLogger(__name__)


class DocumentIngestionView(APIView):
    """POST a document file for ingestion; GET lists ingested documents.

    Restricted to staff/admin users: ingestion writes into the shared knowledge
    base, so it must never be an unauthenticated endpoint.
    """

    permission_classes = [IsAdminUser]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request):
        documents = DocumentSource.objects.all()[:200]
        return Response(DocumentSourceSerializer(documents, many=True).data)

    def post(self, request):
        upload = request.FILES.get('file')
        if upload is None:
            return Response({'detail': 'A file is required.'}, status=status.HTTP_400_BAD_REQUEST)

        max_mb = int(getattr(settings, 'RAG_INGESTION_MAX_UPLOAD_MB', 20))
        if upload.size > max_mb * 1024 * 1024:
            return Response(
                {'detail': f'File exceeds the {max_mb}MB upload limit.'},
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        allowed = getattr(settings, 'RAG_INGESTION_ALLOWED_EXTENSIONS', None)
        name_lower = (upload.name or '').lower()
        if allowed and not any(name_lower.endswith(ext) for ext in allowed):
            return Response(
                {'detail': f'Unsupported file type. Allowed: {", ".join(allowed)}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        visibility = request.data.get('visibility', 'internal')
        if visibility not in dict(DocumentSource.VISIBILITY_CHOICES):
            visibility = 'internal'

        document = IngestionService().ingest_bytes(
            data=upload.read(),
            filename=upload.name,
            mime=upload.content_type or '',
            title=request.data.get('title', '') or (upload.name or ''),
            visibility=visibility,
            uploaded_by=request.user,
            reingest=str(request.data.get('reingest', '')).lower() in ('1', 'true', 'yes'),
        )
        http_status = (
            status.HTTP_201_CREATED if document.status == 'completed'
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        return Response(DocumentSourceSerializer(document).data, status=http_status)
