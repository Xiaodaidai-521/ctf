"""Sequence-aware recommendation helpers for learning dashboard surfaces.

The project does not ship a trained DKT/AKT/S3Rec model, so this module keeps
the same signals in a deterministic scoring layer:

* DKT-like mastery: updates the current concept mastery from sequential
  attempts, successes, and failures.
* AKT-like attention: boosts concepts related to recent learning and penalizes
  long review gaps.
* S3Rec/GNN-like dependency walk: uses concept relations and module
  prerequisites to choose a reachable next concept instead of a random weak one.

The functions are deliberately model-agnostic. A trained model can later replace
the scoring internals while keeping the payloads consumed by the frontend.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence

from django.contrib.contenttypes.models import ContentType
from django.db.models import Count, Q
from django.utils import timezone


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


@dataclass
class ConceptScore:
    concept: object
    mastery: float
    recall: float
    attention: float
    dependency: float
    readiness: float
    score: float
    source: str
    reasons: List[str] = field(default_factory=list)


class KnowledgeSequenceRecommender:
    """Build next-step and content scores from a student's learning sequence."""

    RECENT_EVENT_LIMIT = 80

    def __init__(self, user):
        self.user = user

    def build_concept_scores(self, limit: int = 12) -> List[ConceptScore]:
        from .models import (
            ConceptRelation,
            KnowledgeConcept,
            UserKnowledgeState,
            UserLearningBehavior,
        )

        states = {
            state.concept_id: state
            for state in UserKnowledgeState.objects.filter(user=self.user)
            .select_related("concept")
        }

        concepts = list(KnowledgeConcept.objects.all())
        if not concepts:
            return []

        events = list(
            UserLearningBehavior.objects.filter(user=self.user)
            .prefetch_related("concepts")
            .order_by("-timestamp")[: self.RECENT_EVENT_LIMIT]
        )
        recent_concept_ids = self._extract_recent_concept_ids(events)
        recent_weights = self._recent_attention_weights(recent_concept_ids)

        relation_weights = self._relation_weights(ConceptRelation, recent_weights)
        dependency_readiness = self._dependency_readiness(ConceptRelation, states)

        scores = []
        for concept in concepts:
            state = states.get(concept.id)
            mastery = self._dkt_mastery(state, concept.id, events)
            recall = self._recall_probability(state)
            attention = _clamp(recent_weights.get(concept.id, 0) + relation_weights.get(concept.id, 0))
            dependency = dependency_readiness.get(concept.id, 1.0)

            weakness_gap = 1 - mastery
            forgetting_gap = 1 - recall
            difficulty_fit = self._difficulty_fit(concept, mastery)
            sequence_score = (
                weakness_gap * 0.34
                + forgetting_gap * 0.22
                + attention * 0.20
                + dependency * 0.14
                + difficulty_fit * 0.10
            )

            reasons = self._score_reasons(mastery, recall, attention, dependency)
            scores.append(
                ConceptScore(
                    concept=concept,
                    mastery=round(mastery, 3),
                    recall=round(recall, 3),
                    attention=round(attention, 3),
                    dependency=round(dependency, 3),
                    readiness=round(difficulty_fit, 3),
                    score=round(sequence_score, 4),
                    source="DKT+AKT+S3Rec",
                    reasons=reasons,
                )
            )

        return sorted(scores, key=lambda item: item.score, reverse=True)[:limit]

    def next_learning_recommendations(self, limit: int = 3) -> List[Dict]:
        recs = []
        for item in self.build_concept_scores(limit=limit):
            concept = item.concept
            title = f"知识追踪下一步：{concept.name}"
            reason = (
                f"DKT估计掌握率{int(item.mastery * 100)}%，"
                f"AKT关注到相关知识与遗忘间隔，"
                f"S3Rec/GNN依赖分{int(item.dependency * 100)}%。"
                f"{'；'.join(item.reasons)}"
            )
            recs.append(
                {
                    "type": "sequence_recommendation",
                    "title": title,
                    "reason": reason,
                    "action_link": self._best_concept_link(concept),
                    "priority": 1,
                    "estimated_time": "30-60分钟",
                    "expected_gain": "补齐下一关键知识点，提升后续题目通过率",
                    "concept_id": concept.id,
                    "concept_name": concept.name,
                    "tracking_model": item.source,
                    "mastery_probability": item.mastery,
                    "recall_probability": item.recall,
                    "sequence_score": item.score,
                }
            )
        return recs

    def rank_articles(self, articles: Sequence, limit: int) -> List:
        concept_scores = self.build_concept_scores(limit=20)
        if not concept_scores:
            return list(articles)[:limit]

        score_by_concept = {item.concept.id: item for item in concept_scores}
        text_terms = {
            item.concept.id: {item.concept.name.lower(), item.concept.slug.lower()}
            for item in concept_scores
        }

        linked = self._linked_article_concepts(articles)
        ranked = []
        for index, article in enumerate(articles):
            article_score = self._article_base_score(article, index)
            matched = []

            for concept_id in linked.get(article.id, []):
                if concept_id in score_by_concept:
                    article_score += score_by_concept[concept_id].score * 2.2
                    matched.append(score_by_concept[concept_id].concept.name)

            haystack = f"{article.title} {article.summary} {article.tags}".lower()
            for concept_id, terms in text_terms.items():
                if any(term and term in haystack for term in terms):
                    article_score += score_by_concept[concept_id].score * 1.35
                    matched.append(score_by_concept[concept_id].concept.name)

            article.sequence_reason = self._article_reason(matched)
            article.sequence_score = round(article_score, 4)
            ranked.append((article_score, article))

        ranked.sort(key=lambda pair: pair[0], reverse=True)
        return [article for _, article in ranked[:limit]]

    def _extract_recent_concept_ids(self, events: Sequence) -> List[int]:
        concept_ids = []
        for event in events:
            concept_ids.extend(event.concepts.values_list("id", flat=True))
        return concept_ids

    def _recent_attention_weights(self, concept_ids: Sequence[int]) -> Dict[int, float]:
        weights = {}
        for idx, concept_id in enumerate(concept_ids[:40]):
            weights[concept_id] = weights.get(concept_id, 0) + math.exp(-idx / 8)
        max_weight = max(weights.values(), default=1)
        return {key: value / max_weight for key, value in weights.items()}

    def _relation_weights(self, relation_model, recent_weights: Dict[int, float]) -> Dict[int, float]:
        if not recent_weights:
            return {}

        related = {}
        relations = relation_model.objects.filter(
            Q(from_concept_id__in=recent_weights.keys())
            | Q(to_concept_id__in=recent_weights.keys())
        )
        type_multiplier = {
            "SIMILAR": 0.65,
            "REQUIRES": 0.75,
            "TEACHES": 0.70,
            "PART_OF": 0.45,
        }
        for rel in relations:
            if rel.from_concept_id in recent_weights:
                target_id = rel.to_concept_id
                base = recent_weights[rel.from_concept_id]
            else:
                target_id = rel.from_concept_id
                base = recent_weights[rel.to_concept_id]
            related[target_id] = max(
                related.get(target_id, 0),
                base * rel.strength * type_multiplier.get(rel.relation_type, 0.4),
            )
        return related

    def _dependency_readiness(self, relation_model, states: Dict[int, object]) -> Dict[int, float]:
        readiness = {}
        requires = relation_model.objects.filter(relation_type="REQUIRES")
        grouped = {}
        for rel in requires:
            grouped.setdefault(rel.to_concept_id, []).append(rel.from_concept_id)

        for concept_id, prereq_ids in grouped.items():
            prereq_mastery = [
                getattr(states.get(prereq_id), "mastery_level", 0.18)
                for prereq_id in prereq_ids
            ]
            readiness[concept_id] = sum(prereq_mastery) / max(len(prereq_mastery), 1)
        return readiness

    def _dkt_mastery(self, state, concept_id: int, events: Sequence) -> float:
        mastery = float(getattr(state, "mastery_level", 0.18) or 0.18)
        relevant = []
        for event in reversed(events):
            if concept_id in set(event.concepts.values_list("id", flat=True)):
                relevant.append(event)

        for event in relevant[-20:]:
            if event.success is True or event.behavior_type in {"complete_lab", "complete_module"}:
                mastery += (1 - mastery) * 0.16
            elif event.success is False or event.behavior_type == "submit_flag":
                mastery -= mastery * 0.08
            elif event.behavior_type in {"view_theory", "view_lab", "start_lab"}:
                mastery += (1 - mastery) * 0.04
        return _clamp(mastery)

    def _recall_probability(self, state) -> float:
        if not state:
            return 0.45
        recall = float(state.recall_probability or 0)
        if recall > 0:
            return _clamp(recall)

        last_reviewed = getattr(state, "last_reviewed", None)
        if not last_reviewed:
            return 0.42
        hours = (timezone.now() - last_reviewed).total_seconds() / 3600
        half_life_hours = 24 * (3 + 14 * float(state.mastery_level or 0))
        return _clamp(math.exp(-hours / half_life_hours))

    def _difficulty_fit(self, concept, mastery: float) -> float:
        difficulty = float(getattr(concept, "difficulty_level", 1) or 1)
        target = 1 + mastery * 4
        return _clamp(1 - abs(difficulty - target) / 4)

    def _score_reasons(self, mastery: float, recall: float, attention: float, dependency: float) -> List[str]:
        reasons = []
        if mastery < 0.45:
            reasons.append("当前掌握率偏低，适合优先补强")
        if recall < 0.55:
            reasons.append("遗忘风险较高，需要及时复习")
        if attention > 0.35:
            reasons.append("与近期学习轨迹高度相关")
        if dependency > 0.65:
            reasons.append("前置知识基本具备，可以进入下一步")
        return reasons or ["序列模型判断其处在合适学习窗口"]

    def _best_concept_link(self, concept) -> str:
        from challenges.models import Challenge
        from .models import ConceptResource, PathModule

        challenge_ct = ContentType.objects.get_for_model(Challenge)
        module_ct = ContentType.objects.get_for_model(PathModule)

        challenge_id = ConceptResource.objects.filter(
            concept=concept,
            content_type=challenge_ct,
            role__in=["practice", "assessment"],
        ).values_list("object_id", flat=True).first()
        if challenge_id:
            return f"/challenges/{challenge_id}"

        module_id = ConceptResource.objects.filter(
            concept=concept,
            content_type=module_ct,
        ).values_list("object_id", flat=True).first()
        if module_id:
            return "/learning-paths"

        return "/learning-paths"

    def _linked_article_concepts(self, articles: Sequence) -> Dict[int, List[int]]:
        from articles.models import Article
        from .models import ConceptResource

        article_ids = [article.id for article in articles]
        if not article_ids:
            return {}

        article_ct = ContentType.objects.get_for_model(Article)
        resources = ConceptResource.objects.filter(
            content_type=article_ct,
            object_id__in=article_ids,
        ).values("object_id", "concept_id")

        linked = {}
        for row in resources:
            linked.setdefault(row["object_id"], []).append(row["concept_id"])
        return linked

    def _article_base_score(self, article, index: int) -> float:
        heat = (
            math.log1p(article.view_count)
            + math.log1p(article.like_count) * 1.6
            + math.log1p(article.collect_count) * 1.2
            + math.log1p(article.comment_count)
        )
        editorial = 0.6 if article.is_recommend else 0
        freshness = max(0, 1 - index / 50)
        return heat * 0.08 + editorial + freshness * 0.15

    def _article_reason(self, matched: Iterable[str]) -> str:
        names = []
        for name in matched:
            if name not in names:
                names.append(name)
        if names:
            return f"匹配知识追踪目标：{'、'.join(names[:3])}"
        return "结合热度、编辑推荐与当前学习序列排序"

