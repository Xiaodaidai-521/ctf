"""Index platform learning content into the legal knowledge embedding table."""

from dataclasses import dataclass
from typing import Iterable, List

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db import connection

from audit.models import AuditEvent
from audit.services import AuditLedgerService
from ai_assistant.models import ChallengeKnowledgePack
from articles.models import Article
from challenges.models import Challenge
from resources.models import Resource

from ..models import LegalKnowledgeEmbedding
from .chunking_service import ChunkingService
from .embedding_service import EmbeddingService
from .hashing import sha256_text


@dataclass(frozen=True)
class PlatformIndexingResult:
    """Summary of platform content indexing."""

    source_type: str
    indexed_objects: int
    embedded_chunks: int


class PlatformContentIndexingService:
    """Vectorize challenges, articles, and resources for compliance retrieval."""

    def __init__(self, embedding_service: EmbeddingService = None):
        self.embedding_service = embedding_service or EmbeddingService()

    def index_all(self, *, actor=None) -> List[PlatformIndexingResult]:
        """Index all supported platform content types."""
        return [
            self.index_challenges(actor=actor),
            self.index_challenge_knowledge_packs(actor=actor),
            self.index_articles(actor=actor),
            self.index_resources(actor=actor),
        ]

    @transaction.atomic
    def index_challenges(self, *, actor=None) -> PlatformIndexingResult:
        """Index active CTF challenge metadata and text."""
        queryset = Challenge.objects.filter(is_active=True).select_related('category')
        return self._index_queryset(
            source_type='challenge',
            queryset=queryset,
            actor=actor,
            title_getter=lambda item: item.title,
            text_getter=self._build_challenge_text,
        )

    def _build_challenge_text(self, challenge: Challenge) -> str:
        """Build retrieval text for CTF solving documents and challenge context."""
        solution = getattr(challenge, 'solution', None)
        solution_text = ''
        hint_map_text = ''
        if solution and solution.is_enabled:
            solution_text = solution.content or ''
            hint_map_text = solution.hint_map or ''

        return '\n'.join([
            f'题目：{challenge.title}',
            f'分类：{getattr(challenge.category, "name", "")}',
            f'难度：{challenge.difficulty or ""}',
            f'分值：{challenge.score}',
            '题面：',
            challenge.description or '',
            '提示：',
            challenge.hint or '',
            '解题文档：',
            solution_text,
            '分步提示：',
            hint_map_text,
        ])

    @transaction.atomic
    def index_challenge_knowledge_packs(self, *, actor=None) -> PlatformIndexingResult:
        """Index generated CTF challenge knowledge packs for legal-review retrieval."""
        queryset = ChallengeKnowledgePack.objects.select_related('challenge', 'challenge__category')
        return self._index_queryset(
            source_type='challenge',
            queryset=queryset,
            actor=actor,
            title_getter=lambda item: item.challenge.title,
            text_getter=self._build_challenge_pack_text,
            metadata_getter=lambda item, chunk: {
                'source_type': 'challenge',
                'kind': 'knowledge_pack',
                'challenge_id': item.challenge_id,
                'category_name': item.category_name,
                'difficulty': item.difficulty,
                'pack_version': item.pack_version,
                'chunk_key': chunk.clause_key,
            },
        )

    def _build_challenge_pack_text(self, pack: ChallengeKnowledgePack) -> str:
        """Build retrieval text from a precomputed challenge knowledge pack."""
        snapshot = pack.challenge_snapshot or {}
        related_titles = []
        for collection in [pack.related_challenges, pack.related_articles, pack.related_resources]:
            for item in collection or []:
                title = item.get('title') or item.get('name')
                if title:
                    related_titles.append(str(title))
        return '\n'.join([
            f'题目：{pack.challenge.title}',
            f'分类：{pack.category_name}',
            f'难度：{pack.difficulty}',
            f'关键词：{"、".join(pack.keywords or [])}',
            f'摘要：{pack.summary}',
            f'题面：{snapshot.get("description", "")}',
            f'提示：{snapshot.get("hint", "")}',
            f'关联资料：{"、".join(related_titles[:20])}',
            '知识包内容：',
            pack.context_text or '',
        ])

    @transaction.atomic
    def index_articles(self, *, actor=None) -> PlatformIndexingResult:
        """Index approved community articles."""
        queryset = Article.objects.filter(status='approved').select_related('category')
        return self._index_queryset(
            source_type='article',
            queryset=queryset,
            actor=actor,
            title_getter=lambda item: item.title,
            text_getter=lambda item: '\n'.join([
                item.title,
                item.summary or '',
                item.content or '',
                getattr(item.category, 'name', ''),
                item.tags or '',
            ]),
        )

    @transaction.atomic
    def index_resources(self, *, actor=None) -> PlatformIndexingResult:
        """Index approved learning resources."""
        queryset = Resource.objects.filter(status='approved')
        return self._index_queryset(
            source_type='resource',
            queryset=queryset,
            actor=actor,
            title_getter=lambda item: item.title,
            text_getter=lambda item: '\n'.join([
                item.title,
                item.description or '',
                item.category or '',
                item.tags or '',
                item.resource_type or '',
            ]),
        )

    def _index_queryset(
        self,
        *,
        source_type: str,
        queryset: Iterable,
        actor,
        title_getter,
        text_getter,
        metadata_getter=None,
    ) -> PlatformIndexingResult:
        content_type = ContentType.objects.get_for_model(queryset.model)
        indexed_objects = 0
        embedded_chunks = 0

        for item in queryset.iterator():
            text = (text_getter(item) or '').strip()
            if not text:
                continue
            LegalKnowledgeEmbedding.objects.filter(
                content_type=content_type,
                object_id=item.id,
                source_type=source_type,
            ).delete()
            chunks = ChunkingService.split_plain_text(text)
            if not chunks:
                continue
            indexed_objects += 1
            for chunk in chunks:
                semantic_embedding = self.embedding_service.embed_text(chunk.text)
                # Keep a stable local vector for SQLite/offline fallback even when
                # a production semantic vector is also written to pgvector.
                embedding = self.embedding_service.embed_local_text(chunk.text)
                metadata = metadata_getter(item, chunk) if metadata_getter else {
                    'source_type': source_type,
                    'chunk_key': chunk.clause_key,
                }
                LegalKnowledgeEmbedding.objects.create(
                    source_type=source_type,
                    content_type=content_type,
                    object_id=item.id,
                    chunk_index=chunk.order - 1,
                    title=title_getter(item),
                    text=chunk.text,
                    text_hash=sha256_text(chunk.text),
                    embedding=embedding,
                    embedding_vector=(
                        semantic_embedding
                        if connection.vendor == 'postgresql' and len(semantic_embedding) == 1024
                        else None
                    ),
                    embedding_model='local-hash-v1',
                    embedding_dimension=len(embedding),
                    metadata={
                        **metadata,
                        'vector_model': (
                            self.embedding_service.model
                            if len(semantic_embedding) == 1024
                            else 'local-hash-v1'
                        ),
                    },
                )
                embedded_chunks += 1

        AuditEvent.log(
            category='kb_ingestion',
            summary=f'Platform content indexed: {source_type}',
            user=actor,
            detail={
                'source_type': source_type,
                'indexed_objects': indexed_objects,
                'embedded_chunks': embedded_chunks,
            },
        )
        AuditLedgerService.append_entry(
            event_category='kb_ingestion',
            object_type=f'platform.{source_type}',
            object_id='bulk',
            actor=actor,
            payload={
                'action': 'index_platform_content',
                'source_type': source_type,
                'indexed_objects': indexed_objects,
                'embedded_chunks': embedded_chunks,
                'embedding_model': self.embedding_service.model,
            },
        )
        return PlatformIndexingResult(
            source_type=source_type,
            indexed_objects=indexed_objects,
            embedded_chunks=embedded_chunks,
        )
