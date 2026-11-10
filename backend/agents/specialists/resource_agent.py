"""Structured resource preparation agent."""

from __future__ import annotations

import logging

import re
from typing import Any, Dict, List, Mapping, Optional

from django.conf import settings
from django.db.models import Q



logger = logging.getLogger(__name__)

class ResourceAgent:
    """Prepare ranked learning resources without generating teaching prose."""

    PROMPT_POLICY = "\n".join([
        "ResourceAgent \u53ea\u8fd4\u56de\u7ed3\u6784\u5316 resourceList\uff0c\u4e0d\u751f\u6210\u6559\u5b66\u6b63\u6587\u3002",
        "\u4e0d\u5f97\u7f16\u9020\u8d44\u6e90\uff1b\u4e0d\u5f97\u66ff\u6362\u73b0\u6709 RAG\uff1b\u4e0d\u5f97\u66b4\u9732\u670d\u52a1\u5668\u5185\u90e8\u8def\u5f84\u3002",
        "\u7f13\u5b58\u547d\u4e2d\u65f6\u76f4\u63a5\u4f7f\u7528\u7f13\u5b58\u8d44\u6e90\uff1b\u7f13\u5b58\u672a\u547d\u4e2d\u65f6\u590d\u7528\u73b0\u6709 RAG \u68c0\u7d22\u3002",
        "\u6839\u636e studentLevel \u8c03\u6574\u8d44\u6e90\u6392\u5e8f\uff1b\u65e0\u5339\u914d\u8d44\u6e90\u65f6\u8fd4\u56de\u7a7a resourceList\u3002",
    ])

    DEFAULT_RESULT = {
        "studentId": "",
        "knowledgePoint": "",
        "cacheHit": False,
        "studentLevel": "",
        "resourceList": [],
        # Backward-compatible alias consumed by the existing teaching context.
        "resources": [],
        "noMatchedResource": True,
    }

    BASIC_LEVEL_ALIASES = (
        "basic", "beginner", "foundation", "intro", "low", "weak",
        "\u57fa\u7840", "\u5165\u95e8", "\u521d\u7ea7", "\u65b0\u624b", "\u8584\u5f31",
    )
    ADVANCED_LEVEL_ALIASES = (
        "advanced", "excellent", "expert", "strong", "pro", "high",
        "\u4f18\u79c0", "\u9ad8\u9636", "\u9ad8\u7ea7", "\u8fdb\u9636", "\u63d0\u5347", "\u5f3a",
    )

    KNOWLEDGE_PATTERNS = (
        (re.compile(r"sql\s*\u6ce8\u5165|sql\s*injection", re.I), "SQL\u6ce8\u5165"),
        (re.compile(r"xss|\u8de8\u7ad9\u811a\u672c", re.I), "XSS"),
        (re.compile(r"csrf|\u8de8\u7ad9\u8bf7\u6c42\u4f2a\u9020", re.I), "CSRF"),
        (re.compile(r"ssrf|\u670d\u52a1\u7aef\u8bf7\u6c42\u4f2a\u9020", re.I), "SSRF"),
        (re.compile(r"base64", re.I), "Base64\u7f16\u7801"),
        (re.compile(r"rsa", re.I), "RSA"),
        (re.compile(r"aes", re.I), "AES"),
        (re.compile(r"http", re.I), "HTTP\u534f\u8bae"),
        (re.compile(r"tcp|\u4e09\u6b21\u63e1\u624b", re.I), "TCP\u4e09\u6b21\u63e1\u624b"),
        (re.compile(r"\u53cd\u5e8f\u5217\u5316|deserialization", re.I), "\u53cd\u5e8f\u5217\u5316"),
        (re.compile(r"\u6587\u4ef6\u4e0a\u4f20|file\s*upload", re.I), "\u6587\u4ef6\u4e0a\u4f20"),
        (re.compile(r"\u547d\u4ee4\u6267\u884c|command\s*execution|rce", re.I), "\u547d\u4ee4\u6267\u884c"),
        (re.compile(r"\u6808\u6ea2\u51fa|\u7f13\u51b2\u533a\u6ea2\u51fa|buffer\s*overflow", re.I), "\u7f13\u51b2\u533a\u6ea2\u51fa"),
        (re.compile(r"\u9006\u5411|reverse", re.I), "\u9006\u5411\u5de5\u7a0b"),
        (re.compile(r"\u53d6\u8bc1|forensics", re.I), "\u6570\u5b57\u53d6\u8bc1"),
        (re.compile(r"\u9690\u5199|steg", re.I), "\u9690\u5199\u5206\u6790"),
    )

    BASIC_TERMS = (
        "\u57fa\u7840", "\u5165\u95e8", "\u521d\u7ea7", "\u65b0\u624b", "\u524d\u7f6e", "\u793a\u4f8b", "\u7b80\u4ecb", "\u539f\u7406", "\u6982\u5ff5",
        "basic", "beginner", "intro", "foundation", "easy", "example", "prerequisite",
    )
    ADVANCED_TERMS = (
        "\u63d0\u5347", "\u6df1\u5165", "\u8fdb\u9636", "\u9ad8\u7ea7", "\u5b9e\u6218", "\u5b9e\u8df5", "\u6311\u6218", "\u4e13\u9898", "\u7814\u7a76", "\u7ed5\u8fc7",
        "advanced", "deep", "hard", "expert", "challenge", "practice", "lab",
    )

    def prepare(
        self,
        *,
        query: str = "",
        question: Optional[str] = None,
        student_id: Optional[int] = None,
        task_type: Optional[str] = None,
        knowledge_point: Optional[str] = None,
        student_level: Optional[str] = None,
        resource_cache: Optional[Mapping[str, Any]] = None,
        existing_rag_context: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Return cached or freshly retrieved resources for a student concept."""
        del task_type  # ResourceAgent prepares data only; task prose belongs elsewhere.

        question_text = str(question if question is not None else query or "").strip()
        normalized_knowledge_point = self._normalize_knowledge_point(knowledge_point or question_text)
        normalized_student_level = self._normalize_student_level(student_level)
        student_key = self._coerce_student_id(student_id)
        cache_enabled = bool(getattr(settings, "TUTOR_RESOURCE_CACHE_ENABLED", True))

        if not question_text and not normalized_knowledge_point:
            return self._result(
                student_id=student_key,
                knowledge_point=normalized_knowledge_point,
                student_level=normalized_student_level,
                cache_hit=False,
                resources=[],
            )

        try:
            if cache_enabled:
                provided_cache = self._resources_from_provided_cache(resource_cache)
                if provided_cache is not None:
                    resources = self._rank_for_student_level(provided_cache, normalized_student_level)
                    return self._result(
                        student_id=student_key,
                        knowledge_point=normalized_knowledge_point,
                        student_level=normalized_student_level,
                        cache_hit=True,
                        resources=resources,
                    )

                cache = self._get_cache(student_key, normalized_knowledge_point)
                if cache is not None:
                    resources = self._rank_for_student_level(
                        self._sanitize_resource_list(cache.resourceList),
                        normalized_student_level,
                    )
                    self._mark_cache_hit(cache, resources, normalized_student_level)
                    return self._result(
                        student_id=student_key,
                        knowledge_point=normalized_knowledge_point,
                        student_level=normalized_student_level,
                        cache_hit=True,
                        resources=resources,
                    )

            search_query = self._build_search_query(question_text, normalized_knowledge_point)
            resources = self._resources_from_existing_context(existing_rag_context)
            if not resources:
                resources.extend(self._retrieve_vector_resources(search_query))
            resources.extend(self._retrieve_database_resources(search_query))
            resources = self._dedupe(resources)
            resources = self._rank_for_student_level(resources, normalized_student_level)[:8]
            if cache_enabled:
                self._write_cache(student_key, normalized_knowledge_point, resources, normalized_student_level)
            return self._result(
                student_id=student_key,
                knowledge_point=normalized_knowledge_point,
                student_level=normalized_student_level,
                cache_hit=False,
                resources=resources,
            )
        except Exception as exc:
            logger.warning("resource_agent_fallback", extra={"event": "resource_agent_fallback", "error_type": type(exc).__name__})
            return self._result(
                student_id=student_key,
                knowledge_point=normalized_knowledge_point,
                student_level=normalized_student_level,
                cache_hit=False,
                resources=[],
            )

    def _retrieve_vector_resources(self, query: str) -> List[Dict[str, Any]]:
        """Reuse the existing RAG/vector retrieval service; do not create a new vector path."""
        try:
            from legal_kb.services.retrieval_service import LegalRetrievalService

            matches = LegalRetrievalService().retrieve(
                query=query,
                top_k=12,
                filters={"source_type": ["article", "resource"]},
            )
            resources = []
            for item in matches:
                hydrated = self._hydrate_vector_item(item)
                if hydrated:
                    resources.append(hydrated)
            return resources
        except Exception as exc:
            logger.warning("resource_agent_fallback", extra={"event": "resource_agent_fallback", "error_type": type(exc).__name__})
            return []

    def _hydrate_vector_item(self, item: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
        source_type = str(item.get("source_type") or "").lower()
        object_id = item.get("object_id")
        score = self._safe_float(item.get("score"), 0.0)
        summary = self._safe_excerpt(item.get("text") or "", 260)

        try:
            if source_type == "article":
                from articles.models import Article

                article = Article.objects.filter(id=object_id, status="approved").first()
                if not article:
                    return None
                return self._resource_item(
                    id=article.id,
                    title=article.title,
                    type="article",
                    entry=f"/community/article/{article.id}",
                    summary=summary or getattr(article, "summary", ""),
                    score=score,
                    source="rag",
                    tags=getattr(article, "tags", ""),
                    category=getattr(getattr(article, "category", None), "name", ""),
                )
            if source_type == "resource":
                from resources.models import Resource

                resource = Resource.objects.filter(id=object_id, status="approved").first()
                if not resource:
                    return None
                return self._resource_item(
                    id=resource.id,
                    title=resource.title,
                    type=self._map_type(resource.resource_type),
                    entry=f"/resources?highlight_resource={resource.id}&resource={resource.id}",
                    summary=summary or resource.description,
                    score=score,
                    source="rag",
                    tags=resource.tags,
                    category=resource.category,
                    reserved=bool(getattr(resource, "is_tutoring_reserved", False)),
                )
        except Exception as exc:
            logger.warning("resource_agent_fallback", extra={"event": "resource_agent_fallback", "error_type": type(exc).__name__})
            return None
        return None

    def _retrieve_database_resources(self, query: str) -> List[Dict[str, Any]]:
        keywords = self._keywords(query)
        if not keywords:
            return []

        results = []
        results.extend(self._article_results(keywords))
        results.extend(self._resource_results(keywords))
        results.extend(self._challenge_results(keywords))
        return results

    def _article_results(self, keywords) -> List[Dict[str, Any]]:
        try:
            from articles.models import Article

            condition = self._condition(["title", "summary", "content", "tags"], keywords)
            queryset = Article.objects.filter(status="approved").filter(condition).order_by("-view_count")[:5]
            return [
                self._resource_item(
                    id=article.id,
                    title=article.title,
                    type="article",
                    entry=f"/community/article/{article.id}",
                    summary=getattr(article, "summary", ""),
                    score=self._keyword_score(" ".join([article.title, getattr(article, "summary", "")]), keywords, base=0.45),
                    source="keyword",
                    tags=getattr(article, "tags", ""),
                    category=getattr(getattr(article, "category", None), "name", ""),
                )
                for article in queryset
            ]
        except Exception as exc:
            logger.warning("resource_agent_fallback", extra={"event": "resource_agent_fallback", "error_type": type(exc).__name__})
            return []

    def _resource_results(self, keywords) -> List[Dict[str, Any]]:
        try:
            from resources.models import Resource

            condition = self._condition(["title", "description", "category", "tags"], keywords)
            queryset = Resource.objects.filter(status="approved").filter(condition).order_by("-view_count")[:5]
            return [
                self._resource_item(
                    id=resource.id,
                    title=resource.title,
                    type=self._map_type(resource.resource_type),
                    entry=f"/resources?highlight_resource={resource.id}&resource={resource.id}",
                    summary=resource.description,
                    score=self._keyword_score(" ".join([resource.title, resource.description, resource.tags]), keywords, base=0.5),
                    source="keyword",
                    tags=resource.tags,
                    category=resource.category,
                    reserved=bool(getattr(resource, "is_tutoring_reserved", False)),
                )
                for resource in queryset
            ]
        except Exception as exc:
            logger.warning("resource_agent_fallback", extra={"event": "resource_agent_fallback", "error_type": type(exc).__name__})
            return []

    def _challenge_results(self, keywords) -> List[Dict[str, Any]]:
        try:
            from challenges.models import Challenge

            condition = self._condition(["title", "description", "category__name"], keywords)
            queryset = Challenge.objects.filter(is_active=True).filter(condition).order_by("difficulty", "-solve_count")[:5]
            return [
                self._resource_item(
                    id=challenge.id,
                    title=challenge.title,
                    type="challenge",
                    entry=f"/challenge/{challenge.id}",
                    summary=getattr(challenge, "description", ""),
                    score=self._keyword_score(" ".join([challenge.title, getattr(challenge, "description", "")]), keywords, base=0.4),
                    source="keyword",
                    category=getattr(getattr(challenge, "category", None), "name", ""),
                    difficulty=getattr(challenge, "difficulty", ""),
                )
                for challenge in queryset
            ]
        except Exception as exc:
            logger.warning("resource_agent_fallback", extra={"event": "resource_agent_fallback", "error_type": type(exc).__name__})
            return []

    def _get_cache(self, student_id: Optional[int], knowledge_point: str):
        if student_id is None or not knowledge_point:
            return None
        try:
            from resources.models import ResourceCache

            return ResourceCache.objects.filter(
                studentId=student_id,
                knowledgePoint=knowledge_point,
            ).first()
        except Exception as exc:
            logger.warning("resource_agent_fallback", extra={"event": "resource_agent_fallback", "error_type": type(exc).__name__})
            return None

    def _mark_cache_hit(self, cache, resources: List[Dict[str, Any]], student_level: str) -> None:
        try:
            cache.cacheHitCount = int(cache.cacheHitCount or 0) + 1
            update_fields = ["cacheHitCount", "updatedTime"]
            if student_level and cache.studentLevel != student_level:
                cache.studentLevel = student_level
                cache.resourceList = resources
                update_fields.extend(["studentLevel", "resourceList"])
            cache.save(update_fields=update_fields)
        except Exception as exc:
            logger.warning("resource_agent_fallback", extra={"event": "resource_agent_fallback", "error_type": type(exc).__name__})
            pass

    def _write_cache(
        self,
        student_id: Optional[int],
        knowledge_point: str,
        resources: List[Dict[str, Any]],
        student_level: str,
    ) -> None:
        if student_id is None or not knowledge_point:
            return
        try:
            from resources.models import ResourceCache

            ResourceCache.objects.update_or_create(
                studentId=student_id,
                knowledgePoint=knowledge_point,
                defaults={
                    "resourceList": resources,
                    "studentLevel": student_level,
                },
            )
        except Exception as exc:
            logger.warning("resource_agent_fallback", extra={"event": "resource_agent_fallback", "error_type": type(exc).__name__})
            pass

    def _resources_from_provided_cache(self, resource_cache: Optional[Mapping[str, Any]]) -> Optional[List[Dict[str, Any]]]:
        if not isinstance(resource_cache, Mapping):
            return None
        if "resourceList" in resource_cache:
            return self._sanitize_resource_list(resource_cache.get("resourceList"))
        if "resources" in resource_cache:
            return self._sanitize_resource_list(resource_cache.get("resources"))
        return None

    def _resources_from_existing_context(self, existing_rag_context: Optional[Mapping[str, Any]]) -> List[Dict[str, Any]]:
        if not isinstance(existing_rag_context, Mapping):
            return []
        candidates = []
        for key in ("resourceList", "resources", "items", "rag_sources"):
            value = existing_rag_context.get(key)
            if isinstance(value, list):
                candidates.extend(value)
        retrieval_context = existing_rag_context.get("retrieval_context")
        if isinstance(retrieval_context, Mapping) and isinstance(retrieval_context.get("items"), list):
            candidates.extend(retrieval_context.get("items"))
        return self._sanitize_resource_list(candidates)

    def _sanitize_resource_list(self, resources: Any) -> List[Dict[str, Any]]:
        if not isinstance(resources, list):
            return []
        sanitized = []
        for item in resources:
            if not isinstance(item, Mapping):
                continue
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            resource_type = self._map_type(item.get("type") or item.get("source_type") or item.get("resource_type"))
            raw_id = item.get("id") or item.get("object_id") or item.get("resource_id") or title
            sanitized.append(self._resource_item(
                id=raw_id,
                title=title,
                type=resource_type,
                entry=item.get("entry") or self._entry_for(resource_type, raw_id),
                summary=item.get("summary") or item.get("text") or item.get("reason") or "",
                score=self._safe_float(item.get("matchScore", item.get("score")), 0.5),
                source=item.get("source") or item.get("mode") or "existing_rag",
                tags=item.get("tags", ""),
                category=item.get("category", ""),
                difficulty=item.get("difficulty", ""),
                reserved=bool(item.get("reserved", item.get("is_tutoring_reserved", False))),
            ))
        return sanitized

    def _resource_item(
        self,
        *,
        id: Any,
        title: Any,
        type: Any,
        entry: Any,
        summary: Any = "",
        score: Any = 0,
        source: Any = "",
        tags: Any = "",
        category: Any = "",
        difficulty: Any = "",
        reserved: bool = False,
    ) -> Dict[str, Any]:
        mapped_type = self._map_type(type)
        title_text = str(title or "")[:120]
        is_resource_center_item = mapped_type in {
            "resource", "video", "document", "zip", "report", "course", "textbook", "ai_resource",
        }
        label = "AI多模态生成" if is_resource_center_item else ""
        location = (
            f"资源中心 / {label} / {title_text}" if label
            else f"社区 / 文章 / {title_text}" if mapped_type == "article"
            else f"题库 / 题目 / {title_text}" if mapped_type == "challenge"
            else title_text
        )
        match_score = round(self._safe_float(score, 0.0), 4)
        return {
            "id": str(id or ""),
            "title": title_text,
            "type": mapped_type,
            "entry": self._safe_entry(entry),
            "summary": self._safe_excerpt(summary, 260),
            "ai_generated_label": label,
            "location": location,
            "score": match_score,
            "matchScore": match_score,
            "source": str(source or "")[:40],
            "tags": str(tags or "")[:200],
            "category": str(category or "")[:100],
            "difficulty": str(difficulty or "")[:40],
            "reserved": bool(reserved),
        }

    def _rank_for_student_level(self, resources: List[Dict[str, Any]], student_level: str) -> List[Dict[str, Any]]:
        level_group = self._student_level_group(student_level)
        ranked = []
        for resource in resources:
            item = dict(resource)
            base_score = self._safe_float(item.get("matchScore", item.get("score")), 0.0)
            item["matchScore"] = round(base_score, 4)
            item["score"] = round(base_score + self._level_bonus(item, level_group), 4)
            ranked.append(item)
        ranked.sort(key=lambda item: (self._safe_float(item.get("score"), 0), item.get("title", "")), reverse=True)
        return ranked

    def _level_bonus(self, item: Mapping[str, Any], level_group: str) -> float:
        blob = " ".join([
            str(item.get("title", "")),
            str(item.get("summary", "")),
            str(item.get("tags", "")),
            str(item.get("category", "")),
            str(item.get("difficulty", "")),
            str(item.get("type", "")),
        ]).lower()
        if level_group == "advanced":
            bonus = 0.0
            if any(term.lower() in blob for term in self.ADVANCED_TERMS):
                bonus += 0.22
            if str(item.get("type")) == "challenge":
                bonus += 0.12
            if str(item.get("difficulty", "")).lower() in {"medium", "hard", "expert"}:
                bonus += 0.14
            if any(term.lower() in blob for term in self.BASIC_TERMS):
                bonus -= 0.08
            return bonus

        if level_group == "basic":
            bonus = 0.0
            if any(term.lower() in blob for term in self.BASIC_TERMS):
                bonus += 0.24
            if str(item.get("difficulty", "")).lower() in {"easy", "beginner", "basic"}:
                bonus += 0.14
            if str(item.get("type")) in {"article", "resource", "video"}:
                bonus += 0.05
            if any(term.lower() in blob for term in self.ADVANCED_TERMS):
                bonus -= 0.08
            return bonus
        return 0.0

    def _student_level_group(self, student_level: str) -> str:
        value = str(student_level or "").strip().lower()
        if any(alias.lower() in value for alias in self.ADVANCED_LEVEL_ALIASES):
            return "advanced"
        if any(alias.lower() in value for alias in self.BASIC_LEVEL_ALIASES):
            return "basic"
        return "basic"

    def _normalize_student_level(self, student_level: Optional[str]) -> str:
        value = str(student_level or "beginner").strip()
        return value[:40] or "beginner"

    def _normalize_knowledge_point(self, value: Any) -> str:
        text = re.sub(r"\s+", " ", str(value or "").strip())
        text = text.strip(" \u3000\uff0c\u3002\uff01\uff1f?!.;\uff1b:\uff1a\u3001\"'`()[]{}<>\u300a\u300b")
        if not text:
            return ""
        for pattern, canonical in self.KNOWLEDGE_PATTERNS:
            if pattern.search(text):
                return canonical
        tokens = self._keywords(text)
        if tokens:
            return " ".join(tokens[:4])[:80]
        return text[:80]

    def _build_search_query(self, question: str, knowledge_point: str) -> str:
        parts = []
        if knowledge_point:
            parts.append(knowledge_point)
        if question and question not in parts:
            parts.append(question)
        return " ".join(parts).strip()

    def _keywords(self, query: str) -> List[str]:
        value = str(query or "").lower()
        tokens = re.findall(r"[a-z0-9_+#.-]{2,}|[\u4e00-\u9fff]{2,}", value)
        stopwords = {"how", "what", "why", "the", "and", "for", "\u8bf7\u95ee", "\u600e\u4e48", "\u4e3a\u4ec0\u4e48", "\u5982\u4f55", "\u8fd9\u4e2a", "\u77e5\u8bc6\u70b9"}
        cleaned = []
        for token in tokens:
            token = token.strip("-_ ")
            if not token or token in stopwords:
                continue
            if len(token) > 18 and re.fullmatch(r"[\u4e00-\u9fff]+", token):
                token = token[:18]
            if token not in cleaned:
                cleaned.append(token)
            if len(cleaned) >= 8:
                break
        return cleaned

    def _condition(self, fields, keywords):
        condition = Q()
        for field in fields:
            for keyword in keywords:
                condition |= Q(**{f"{field}__icontains": keyword})
        return condition

    def _keyword_score(self, text: str, keywords, base: float) -> float:
        lowered = str(text or "").lower()
        hits = sum(1 for keyword in keywords if keyword in lowered)
        return round(base + hits * 0.08, 4)

    def _result(
        self,
        *,
        student_id: Optional[int],
        knowledge_point: str,
        student_level: str,
        cache_hit: bool,
        resources: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        resource_list = resources or []
        return {
            "studentId": "" if student_id is None else str(student_id),
            "knowledgePoint": str(knowledge_point or ""),
            "cacheHit": bool(cache_hit),
            "studentLevel": str(student_level or ""),
            "resourceList": resource_list,
            "resources": resource_list,
            "noMatchedResource": not bool(resource_list),
        }

    def _entry_for(self, raw_type: Any, raw_id: Any) -> str:
        resource_type = self._map_type(raw_type)
        if resource_type == "article":
            return f"/community/article/{raw_id}"
        if resource_type == "challenge":
            return f"/challenge/{raw_id}"
        if resource_type in {"resource", "video", "document", "zip", "report", "course", "textbook", "ai_resource"}:
            return f"/resources?highlight_resource={raw_id}&resource={raw_id}"
        return ""

    def _safe_entry(self, entry: Any) -> str:
        value = str(entry or "").strip()
        if not value:
            return ""
        if re.match(r"^[A-Za-z]:[\\/]", value) or "\\" in value:
            return ""
        if value.startswith(("/var/", "/home/", "/usr/", "/opt/", "/tmp/")):
            return ""
        if value.startswith("/") or value.startswith(("http://", "https://")):
            return value[:240]
        return ""

    def _safe_excerpt(self, value: Any, max_length: int) -> str:
        text = re.sub(r"\s+", " ", str(value or "").strip())
        return text[:max_length]

    def _safe_float(self, value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _coerce_student_id(self, student_id: Any) -> Optional[int]:
        try:
            value = int(student_id)
            return value if value > 0 else None
        except (TypeError, ValueError):
            return None

    def _map_type(self, raw_type) -> str:
        mapping = {
            "article": "article",
            "challenge": "challenge",
            "document": "resource",
            "video": "video",
            "tool": "resource",
            "zip": "resource",
            "report": "resource",
            "resource": "resource",
            "ai_resource": "ai_resource",
            "course": "course",
            "textbook": "textbook",
        }
        return mapping.get(str(raw_type or "").lower(), "resource")

    def _dedupe(self, items):
        deduped = {}
        for item in items:
            key = (item.get("type"), item.get("id") or item.get("title"))
            if key not in deduped or item.get("score", 0) > deduped[key].get("score", 0):
                deduped[key] = item
        return list(deduped.values())
