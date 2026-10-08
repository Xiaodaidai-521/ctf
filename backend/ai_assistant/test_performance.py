import time
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.models.signals import post_save
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from agents.context.student_profile_adapter import StudentProfileContextAdapter
from agents.specialists.cached_resource_agent import ResourceAgent
from agents.specialists.tutor_executor import TutorSpecialistExecutor
from ai_assistant.cache_services import (
    diagnosis_cache_key, profile_cache_key, safe_cache_set,
)
from ai_assistant.performance import TutorPerformanceMetrics
from ai_assistant.prompt_budget import build_teaching_context_summary, trim_history
from ai_providers.base import extract_usage
from learning_analytics.models import AdminLearningScore
from resources.models import Resource, ResourceCache
from student_profiles.models import LearningPersona, LearningPreference, StudentProfile
from submissions.models import Submission


User = get_user_model()


class SlowLearning:
    def analyze(self, student_id):
        time.sleep(0.12)
        return {"student": student_id}


class SlowDiagnosis:
    def analyze(self, **kwargs):
        time.sleep(0.12)
        return {"weakKnowledgePoints": []}


class SlowResources:
    def prepare(self, **kwargs):
        time.sleep(0.12)
        return {"resourceList": []}


class FastKnowledge:
    def analyze(self, **kwargs):
        return {}


class Strategy:
    def build(self, **kwargs):
        return {"days": 7}


class ParallelExecutorTests(SimpleTestCase):
    def executor(self, **kwargs):
        values = dict(
            learning_analysis_agent=SlowLearning(), knowledge_diagnosis_agent=SlowDiagnosis(),
            resource_agent=SlowResources(), knowledge_agent=FastKnowledge(),
            study_strategy_agent=Strategy(), max_workers=3, agent_timeout=1,
        )
        values.update(kwargs)
        return TutorSpecialistExecutor(**values)

    def test_learning_analysis_runs_independent_agents_in_parallel(self):
        started = time.monotonic()
        result = self.executor().execute(task_type="learning_analysis", student_id=1, query="why")
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 0.25)
        self.assertEqual(list(result["agentStatus"]), [
            "learning_analysis_agent", "knowledge_diagnosis_agent", "resource_agent",
        ])

    def test_study_plan_waits_for_first_layer_before_strategy(self):
        started = time.monotonic()
        result = self.executor().execute(task_type="study_plan", student_id=1, query="plan")
        self.assertLess(time.monotonic() - started, 0.25)
        self.assertEqual(result["studyStrategy"]["days"], 7)

    def test_agent_timeout_is_structured(self):
        result = self.executor(agent_timeout=0.05).execute(task_type="learning_analysis", student_id=1)
        self.assertTrue(all(item["status"] == "fallback" for item in result["agentStatus"].values()))


class ProfileCacheTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="profile-cache-a")
        self.other = User.objects.create_user(username="profile-cache-b")
        self.profile = StudentProfile.objects.create(user=self.user, learning_goals="SQL")
        LearningPreference.objects.create(profile=self.profile, preferred_pace="intensive")
        LearningPersona.objects.create(profile=self.profile, persona_label="visual")

    def test_hit_miss_invalidation_and_student_isolation(self):
        adapter = StudentProfileContextAdapter()
        with self.assertNumQueries(1):
            first = adapter.build(self.user)
        with self.assertNumQueries(0):
            second = adapter.build(self.user)
        self.assertEqual(first, second)
        self.assertNotEqual(profile_cache_key(self.user.id), profile_cache_key(self.other.id))
        self.profile.learning_goals = "TCP"
        self.profile.save()
        with self.assertNumQueries(1):
            refreshed = adapter.build(self.user)
        self.assertEqual(refreshed["learningGoals"], "TCP")

    def test_cache_failure_falls_back_to_database(self):
        with patch("ai_assistant.cache_services.cache.get", side_effect=RuntimeError("cache down")):
            with self.assertNumQueries(1):
                self.assertEqual(StudentProfileContextAdapter().build(self.user)["learningGoals"], "SQL")


class DiagnosisInvalidationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="diagnosis-cache")
        self.teacher = User.objects.create_user(username="diagnosis-teacher")

    def test_submission_event_invalidates_student_diagnosis(self):
        key = diagnosis_cache_key(self.user.id)
        safe_cache_set(key, {"masteryScore": 50}, 300)
        self.assertIsNotNone(cache.get(key))
        post_save.send(sender=Submission, instance=SimpleNamespace(user_id=self.user.id), created=True)
        self.assertIsNone(cache.get(key))

    def test_admin_learning_score_invalidates_student_diagnosis(self):
        key = diagnosis_cache_key(self.user.id)
        safe_cache_set(key, {"masteryScore": 70}, 300)
        self.assertIsNotNone(cache.get(key))
        AdminLearningScore.objects.create(
            student=self.user,
            scored_by=self.teacher,
            measured_at=timezone.localdate(),
            total_score=88,
            dimension_scores={"mastery": 88},
        )
        self.assertIsNone(cache.get(key))


class ResourceCacheTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="resource-cache")
        self.resource = Resource.objects.create(
            title="TCP basics", description="TCP", resource_type="document", file="resources/tcp.pdf",
            category="network", status="approved", uploader=self.user,
        )

    def test_cache_hit_does_not_call_rag_and_rechecks_visibility(self):
        agent = ResourceAgent()
        point = agent._normalize_knowledge_point("TCP")
        ResourceCache.objects.create(
            studentId=self.user.id, knowledgePoint=agent._versioned_point(point),
            resourceList=[{"id": str(self.resource.id), "title": self.resource.title, "type": "document"}],
        )
        with patch.object(agent, "_retrieve_vector_resources") as rag:
            result = agent.prepare(query="TCP", student_id=self.user.id)
        rag.assert_not_called()
        self.assertTrue(result["cacheHit"])
        self.assertEqual(len(result["resourceList"]), 1)

        self.resource.status = "pending"
        self.resource.save()
        self.assertFalse(ResourceCache.objects.exists())


class PromptAndMetricsTests(SimpleTestCase):
    @override_settings(TUTOR_PROMPT_BUDGETS={"teaching_context_chars": 700, "history_chars": 120})
    def test_task_scoping_size_resource_and_history_bounds(self):
        context = {"teaching_context": {
            "taskType": "study_plan",
            "learningAnalysis": {"weakKnowledgePoints": [{"name": str(i)} for i in range(20)]},
            "knowledgeContext": {"irrelevant": "x" * 1000},
            "resources": {"resourceList": [{"id": str(i), "title": "r" * 40} for i in range(20)]},
            "studyStrategy": {"days": 7},
            "studentProfile": {"goal": "learn"},
        }}
        summary = build_teaching_context_summary(context)
        self.assertLessEqual(len(summary), 700)
        self.assertNotIn("irrelevant", summary)
        history = trim_history([{"role": "user", "content": str(i) * 80} for i in range(20)])
        self.assertLessEqual(len(history), 8)
        self.assertLessEqual(sum(len(item["content"]) for item in history), 120)

    def test_monitoring_fields_and_nullable_usage(self):
        fields = TutorPerformanceMetrics.create(user_id=7).as_dict()
        expected = {
            "request_id", "conversation_id", "user_id_hash", "task_type", "required_agents",
            "total_duration_ms", "router_duration_ms", "agent_metrics", "rag_duration_ms",
            "llm_duration_ms", "llm_call_count", "rag_call_count", "prompt_tokens",
            "completion_tokens", "total_tokens", "profile_cache_hit", "diagnosis_cache_hit",
            "resource_cache_hit", "fallback_used", "status",
        }
        self.assertEqual(set(fields), expected)
        self.assertIsNone(fields["prompt_tokens"])

    def test_langchain_usage_is_normalized_without_fabrication(self):
        response = SimpleNamespace(usage_metadata={"input_tokens": 10, "output_tokens": 4, "total_tokens": 14})
        self.assertEqual(extract_usage(response)["prompt_tokens"], 10)
        self.assertIsNone(extract_usage(SimpleNamespace()))
