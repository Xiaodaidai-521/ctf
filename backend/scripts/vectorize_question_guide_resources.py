"""Vectorize question-guide resources for multi-agent retrieval.

Run from backend:
    python scripts/vectorize_question_guide_resources.py

By default this indexes approved Resource rows whose file lives under:
    resources/question-guides/

Set QUESTION_GUIDE_RESOURCE_IDS=1,2,3 to include additional explicit IDs.
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
from django.db.models import Q

from legal_kb.models import LegalKnowledgeEmbedding
from legal_kb.services.chunking_service import ChunkingService
from legal_kb.services.embedding_service import EmbeddingService, cosine_similarity
from legal_kb.services.hashing import sha256_text
from resources.models import Resource, ResourceCache


QUESTION_GUIDE_PREFIX = "resources/question-guides/"

# Visible/searchable text for non-text question-guide assets. These are concise
# retrieval summaries, not transcripts.
VISIBLE_TEXT_BY_FILENAME = {
    "web-cache-basic-practice-flow.png": """#54 Web缓存基础练习
核心路径: 进入题目 -> 抓包观察 -> 定位缓存键 -> 构造实验 -> 利用或绕过 -> 提交复盘
观察重点: Cache-Control, ETag, Vary, Age, X-Cache, HIT/MISS
适用知识点: HTTP缓存头, 缓存键, 命中与未命中, 缓存规则验证, 缓存欺骗。""",
    "sql-injection-intro-solved-flow.png": """#26 SQL注入入门
解题流程: 确认范围 -> 寻找输入点 -> 观察回显 -> 判断类型 -> 构造查询 -> 提交复盘
观察重点: 输入点, 报错信息, 页面差异, 列数, 回显位
适用知识点: SQL注入判断, 报错注入, 布尔盲注, 联合查询, 登录绕过, 回显位识别, 修复建议。""",
    "1.1-1.2：SQL注入原理、SQL注入分类.mp4": """视频检索摘要: SQL注入原理与SQL注入分类。
关键词: SQL注入, SQL Injection, 注入原理, 注入分类, 输入点, 参数拼接, 数据库查询, 数字型注入, 字符型注入, 搜索型注入, 登录型注入, 报错注入, 联合查询, UNION查询, 布尔盲注, 时间盲注, 登录绕过, 注释符, 列数判断, 回显位, WHERE条件, 预编译, 参数化查询, Web安全, CTF。
适配题目: SQL注入入门, SQL注入基础认知, SQL注入检测实践, SQL注入绕过登录, SQL注入UNION查询, Blind SQL Injection Timing。
学习目标: 理解用户输入如何进入后端SQL语句, 识别常见注入类型, 根据页面内容、错误信息、响应时间和回显位置判断攻击面, 并了解授权练习环境中的验证与修复思路。""",
}


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
VIDEO_SUFFIXES = {".mp4", ".webm", ".mov", ".m4v"}
TEXT_SUFFIXES = {".md", ".txt"}


def configured_extra_ids() -> list[int]:
    ids = []
    raw_value = os.environ.get("QUESTION_GUIDE_RESOURCE_IDS", "")
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


def target_resources() -> list[Resource]:
    condition = Q(file__startswith=QUESTION_GUIDE_PREFIX)
    extra_ids = configured_extra_ids()
    if extra_ids:
        condition |= Q(id__in=extra_ids)
    return list(Resource.objects.filter(status="approved").filter(condition).order_by("id"))


def read_resource_body(resource: Resource) -> str:
    if not resource.file.name:
        return ""

    media_path = Path(settings.MEDIA_ROOT) / resource.file.name
    suffix = media_path.suffix.lower()
    if suffix in TEXT_SUFFIXES and media_path.exists():
        return media_path.read_text(encoding="utf-8-sig")

    return VISIBLE_TEXT_BY_FILENAME.get(media_path.name, "")


def is_image_resource(resource: Resource) -> bool:
    return Path(resource.file.name or "").suffix.lower() in IMAGE_SUFFIXES


def is_video_resource(resource: Resource) -> bool:
    return Path(resource.file.name or "").suffix.lower() in VIDEO_SUFFIXES


def build_retrieval_text(resource: Resource) -> str:
    return "\n".join(
        [
            f"资源ID: {resource.id}",
            f"标题: {resource.title}",
            f"资源类型: {resource.resource_type or ''}",
            f"分类: {resource.category or ''}",
            f"标签: {resource.tags or ''}",
            "描述:",
            resource.description or "",
            "文件内容/可见文本/检索摘要:",
            read_resource_body(resource),
        ]
    ).strip()


def vectorize_resources() -> list[dict]:
    content_type = ContentType.objects.get_for_model(Resource)
    embedding_service = EmbeddingService(dimension=128, model="local-hash-v1")
    resources = target_resources()
    resource_ids = [resource.id for resource in resources]
    summary = []

    with transaction.atomic():
        if resource_ids:
            deleted_count, _ = LegalKnowledgeEmbedding.objects.filter(
                content_type=content_type,
                object_id__in=resource_ids,
                source_type="resource",
            ).delete()
        else:
            deleted_count = 0

        cache_deleted_count, _ = ResourceCache.objects.all().delete()

        for resource in resources:
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
                        "kind": "question_guide_resource",
                        "resource_id": resource.id,
                        "file": resource.file.name or "",
                        "category": resource.category or "",
                        "tags": resource.get_tags_list(),
                        "resource_type": resource.resource_type or "",
                        "is_image": is_image_resource(resource),
                        "is_video": is_video_resource(resource),
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
                    "chunks": created,
                    "source_chars": len(text),
                    "file": resource.file.name or "",
                    "is_image": is_image_resource(resource),
                    "is_video": is_video_resource(resource),
                }
            )

    return [
        {
            "selected_ids": resource_ids,
            "deleted_existing_embeddings": deleted_count,
            "deleted_resource_cache_rows": cache_deleted_count,
            "question_guide_prefix": QUESTION_GUIDE_PREFIX,
        },
        *summary,
    ]


def smoke_test_queries() -> list[dict]:
    content_type = ContentType.objects.get_for_model(Resource)
    embedding_service = EmbeddingService(dimension=128, model="local-hash-v1")
    resources = target_resources()
    resource_ids = [resource.id for resource in resources]
    queries = [
        "SQL注入原理 SQL注入分类",
        "SQL injection basics 输入点 注入类型",
        "UNION查询 登录绕过 布尔盲注 时间盲注",
        "Web缓存 Cache-Control X-Cache",
        "SSRF 黑名单 本地服务",
        "文件上传 校验绕过",
        "CORS 反射 XSS 同源策略",
    ]
    results = []
    queryset = LegalKnowledgeEmbedding.objects.filter(
        content_type=content_type,
        object_id__in=resource_ids,
        source_type="resource",
    )

    for query in queries:
        query_embedding = embedding_service.embed_local_text(query)
        scored = []
        query_terms = [term for term in query.replace("/", " ").split() if term]
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
    print("VECTORIZE_SUMMARY")
    for row in vectorize_resources():
        print(row)
    print("SMOKE_TEST")
    for row in smoke_test_queries():
        print(row)