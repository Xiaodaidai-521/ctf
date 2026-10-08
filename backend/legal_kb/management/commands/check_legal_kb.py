"""Inspect legal KB database readiness and indexed content."""

from django.core.management.base import BaseCommand
from django.db import connection
from django.db.models import Count

from challenges.models import Challenge
from legal_kb.models import LegalDocument, LegalKnowledgeEmbedding
from legal_kb.services.embedding_service import EmbeddingService


class Command(BaseCommand):
    """Report whether legal documents and platform exercises are vectorized."""

    help = 'Check legal KB tables, database vendor, pgvector extension, and indexed content counts.'

    def handle(self, *args, **options):
        tables = set(connection.introspection.table_names())
        required_tables = {
            LegalDocument._meta.db_table,
            LegalKnowledgeEmbedding._meta.db_table,
            Challenge._meta.db_table,
        }
        missing = sorted(required_tables - tables)

        self.stdout.write(f'Database vendor: {connection.vendor}')
        self.stdout.write(f'Database engine: {connection.settings_dict.get("ENGINE")}')
        self.stdout.write(f'Database name: {connection.settings_dict.get("NAME")}')

        if connection.vendor == 'postgresql':
            self.stdout.write(f'pgvector extension: {self._pgvector_status()}')
        else:
            self.stdout.write(self.style.WARNING('pgvector extension: not applicable, current DB is not PostgreSQL'))

        embedding_service = EmbeddingService()
        self.stdout.write(f'Embedding provider: {embedding_service.provider or "local"}')
        self.stdout.write(f'Embedding model: {embedding_service.model}')
        self.stdout.write(f'Embedding dimension: {embedding_service.dimension}')
        self.stdout.write(f'Embedding remote enabled: {embedding_service.uses_remote_provider}')

        if missing:
            self.stdout.write(self.style.ERROR(f'Missing tables: {", ".join(missing)}'))
            self.stdout.write(self.style.WARNING('Run "python manage.py migrate" before preparing Legal KB data.'))
            return

        source_counts = {
            row['source_type']: row['count']
            for row in (
                LegalKnowledgeEmbedding.objects
                .values('source_type')
                .order_by('source_type')
                .annotate(count=Count('id'))
            )
        }
        legal_documents = LegalDocument.objects.count()
        legal_clause_vectors = source_counts.get('legal_clause', 0)
        challenge_vectors = source_counts.get('challenge', 0)
        pgvector_non_null = 0
        if connection.vendor == 'postgresql':
            pgvector_non_null = LegalKnowledgeEmbedding.objects.exclude(embedding_vector__isnull=True).count()
        sql_challenges = Challenge.objects.filter(
            is_active=True,
            title__icontains='SQL',
        ).count()

        self.stdout.write(f'Legal documents: {legal_documents}')
        self.stdout.write(f'Legal clause vectors: {legal_clause_vectors}')
        self.stdout.write(f'Active SQL challenges: {sql_challenges}')
        self.stdout.write(f'Challenge vectors: {challenge_vectors}')
        if connection.vendor == 'postgresql':
            self.stdout.write(f'PGVECTOR_NON_NULL: {pgvector_non_null}')
        self.stdout.write(f'All vector source counts: {source_counts}')

        if legal_documents and legal_clause_vectors:
            self.stdout.write(self.style.SUCCESS('Legal regulations appear to be imported and vectorized.'))
        else:
            self.stdout.write(self.style.WARNING(
                'Legal regulations are not imported/vectorized yet. '
                'Run fetch_official_laws to fetch official data from flk.npc.gov.cn, or run '
                'prepare_legal_kb --laws-dir <dir> with previously cached official JSON files.'
            ))

        if sql_challenges and challenge_vectors:
            self.stdout.write(self.style.SUCCESS('SQL exercises appear to be present and vectorized.'))
        else:
            self.stdout.write(self.style.WARNING(
                'SQL exercises are not fully present/vectorized yet. '
                'Run prepare_legal_kb --seed-sql-exercises --platform-only.'
            ))

        if connection.vendor == 'postgresql' and LegalKnowledgeEmbedding.objects.exists():
            if pgvector_non_null:
                self.stdout.write(self.style.SUCCESS('pgvector semantic embeddings are present.'))
            elif embedding_service.uses_remote_provider:
                self.stdout.write(self.style.WARNING(
                    'No rows have embedding_vector values yet. Verify the remote embedding endpoint '
                    'returns 1024-dimensional vectors, then rebuild the KB.'
                ))
            else:
                self.stdout.write(self.style.WARNING(
                    'No rows have embedding_vector values yet. Configure a remote 1024-dimensional '
                    'embedding provider, then rebuild the KB.'
                ))

    def _pgvector_status(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            row = cursor.fetchone()
        return row[0] if row else 'missing'