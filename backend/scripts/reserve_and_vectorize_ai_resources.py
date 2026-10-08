"""Reserve AI resource-center items for tutoring and vectorize them.

Run from backend:
    python scripts/reserve_and_vectorize_ai_resources.py

Set TUTORING_AI_RESOURCE_IDS=26,27,28 to override the default resource IDs.
"""

from pathlib import Path
import os
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "ctf_backend.settings")

import django


django.setup()

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import transaction

from legal_kb.models import LegalKnowledgeEmbedding
from legal_kb.services.chunking_service import ChunkingService
from legal_kb.services.embedding_service import EmbeddingService, cosine_similarity
from legal_kb.services.hashing import sha256_text
from resources.models import Resource, ResourceCache


DEFAULT_RESOURCE_IDS = list(range(26, 41))
TEXT_SUFFIXES = {".md", ".txt"}


def configured_resource_ids() -> list[int]:
    raw_value = os.environ.get("TUTORING_AI_RESOURCE_IDS", "")
    if not raw_value.strip():
        return DEFAULT_RESOURCE_IDS

    ids = []
    for raw_item in raw_value.split(","):
        raw_item = raw_item.strip()
        if not raw_item:
            continue
        try:
            value = int(raw_item)
        except ValueError:
            continue
        if value > 0 and value not in ids:
            ids.append(value)
    return ids


def read_resource_body(resource: Resource) -> str:
    if not resource.file.name:
        return ""

    media_path = Path(settings.MEDIA_ROOT) / resource.file.name
    if media_path.suffix.lower() in TEXT_SUFFIXES and media_path.exists():
        return media_path.read_text(encoding="utf-8-sig")
    return ""


def build_retrieval_text(resource: Resource) -> str:
    return "\n".join(
        [
            f"Resource ID: {resource.id}",
            f"Title: {resource.title}",
            f"Type: {resource.resource_type or ''}",
            f"Category: {resource.category or ''}",
            f"Tags: {resource.tags or ''}",
            "Description:",
            resource.description or "",
            "File text:",
            read_resource_body(resource),
        ]
    ).strip()


def reserve_and_vectorize_resources() -> list[dict]:
    resource_ids = configured_resource_ids()
    resources = list(
        Resource.objects.filter(
            id__in=resource_ids,
            status="approved",
            resource_type="ai_resource",
        ).order_by("id")
    )
    selected_ids = [resource.id for resource in resources]
    missing_ids = sorted(set(resource_ids) - set(selected_ids))
    content_type = ContentType.objects.get_for_model(Resource)
    embedding_service = EmbeddingService(dimension=128, model="local-hash-v1")
    summary = []

    with transaction.atomic():
        updated_count = Resource.objects.filter(id__in=selected_ids).update(is_tutoring_reserved=True)
        deleted_count, _ = LegalKnowledgeEmbedding.objects.filter(
            content_type=content_type,
            object_id__in=selected_ids,
            source_type="resource",
        ).delete()
        cache_deleted_count, _ = ResourceCache.objects.all().delete()

        for resource in resources:
            resource.is_tutoring_reserved = True
            text = build_retrieval_text(resource)
            chunks = ChunkingService.split_plain_text(text, max_chars=1200)
            created = 0

            for chunk in chunks:
                embedding = embedding_service.embed_local_text(chunk.text)
                LegalKnowledgeEmbedding.objects.create(
                    source_type="resource",
                    content_type=content_type,
                    object_id=resource.id,
                    chunk_index=chunk.order - 1,
                    title=resource.title,
                    text=chunk.text,
                    text_hash=sha256_text(chunk.text),
                    embedding=embedding,
                    embedding_vector=None,
                    embedding_model="local-hash-v1",
                    embedding_dimension=len(embedding),
                    metadata={
                        "kind": "tutoring_reserved_ai_resource",
                        "resource_id": resource.id,
                        "file": resource.file.name or "",
                        "category": resource.category or "",
                        "tags": resource.get_tags_list(),
                        "resource_type": resource.resource_type or "",
                        "chunk_key": chunk.clause_key,
                        "chunk_chars": len(chunk.text),
                        "vector_model": "local-hash-v1",
                        "vectorized_for": "multi_agent_resource_retrieval",
                    },
                )
                created += 1

            summary.append(
                {
                    "id": resource.id,
                    "title": resource.title,
                    "reserved": resource.is_tutoring_reserved,
                    "chunks": created,
                    "source_chars": len(text),
                    "file": resource.file.name or "",
                }
            )

    return [
        {
            "selected_ids": selected_ids,
            "missing_ids": missing_ids,
            "updated_reserved_resources": updated_count,
            "deleted_existing_embeddings": deleted_count,
            "deleted_resource_cache_rows": cache_deleted_count,
        },
        *summary,
    ]


def smoke_test_queries() -> list[dict]:
    content_type = ContentType.objects.get_for_model(Resource)
    embedding_service = EmbeddingService(dimension=128, model="local-hash-v1")
    resource_ids = configured_resource_ids()
    queries = [
        "SQL注入 靶场 请求链 Python",
        "XSS 过滤绕过 JavaScript",
        "栈溢出 pwntools 偏移 payload",
        "RSA 弱参数 小指数 共模攻击",
        "流量分析 抓包 Python 可疑通信",
        "逆向 校验逻辑 伪代码 算法",
        "隐写 文件头 隐藏载荷 提取",
    ]
    queryset = LegalKnowledgeEmbedding.objects.filter(
        content_type=content_type,
        object_id__in=resource_ids,
        source_type="resource",
    )
    results = []

    for query in queries:
        query_embedding = embedding_service.embed_local_text(query)
        query_terms = [term for term in query.replace("/", " ").split() if term]
        scored = []
        for item in queryset:
            score = cosine_similarity(query_embedding, item.embedding)
            searchable = f"{item.title}\n{item.text}".lower()
            lexical_hits = sum(1 for term in query_terms if term.lower() in searchable)
            score = max(score, min(0.99, 0.35 + lexical_hits * 0.15))
            scored.append((score, item))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        results.append(
            {
                "query": query,
                "top": [
                    {
                        "resource_id": item.object_id,
                        "title": item.title,
                        "chunk_index": item.chunk_index,
                        "score": round(score, 6),
                    }
                    for score, item in scored[:3]
                ],
            }
        )
    return results


if __name__ == "__main__":
    print("RESERVE_AND_VECTORIZE_SUMMARY")
    for row in reserve_and_vectorize_resources():
        print(row)
    print("SMOKE_TEST")
    for row in smoke_test_queries():
        print(row)
