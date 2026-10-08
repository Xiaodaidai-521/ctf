import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from rest_framework.test import APIClient

from agents.router.tutor_router import TutorAgentRouter
from agents.specialists.knowledge_agent import KnowledgeAgent
from ai_assistant.models import AIConversation, AIMessage
from ai_assistant.performance import TutorPerformanceMetrics, activate_metrics, current_metrics, log_metrics
from ai_assistant.response_adapter import build_compatible_chat_response
from ai_assistant.service import AIAssistantService, MultiAgentChatService
from ai_assistant.tutor_request_orchestrator import TutorRequestOrchestrator


User = get_user_model()


class KnowledgeAgentTests(SimpleTestCase):
    def test_empty_normal_and_retrieval_failure(self):
        self.assertEqual(KnowledgeAgent().analyze(query=""), KnowledgeAgent.DEFAULT_RESULT)
        package = {
            "items": [{
                "id": 1, "title": "SQL injection", "summary": "SQL injection definition",
                "source_type": "article", "metadata": {
                    "prerequisites": ["SQL"], "common_mistakes": ["string concatenation"],
                },
            }],
        }
        with patch.object(MultiAgentChatService, "build_knowledge_context", return_value=package):
            result = KnowledgeAgent().analyze(query="Explain SQL injection", knowledge_point="SQL injection")
        self.assertEqual(result["definition"], "SQL injection definition")
        self.assertEqual(result["prerequisites"], ["SQL"])
        self.assertEqual(result["sources"][0]["id"], "1")
        with patch.object(MultiAgentChatService, "build_knowledge_context", side_effect=RuntimeError("rag down")):
            fallback = KnowledgeAgent().analyze(query="SQL")
        self.assertEqual(fallback, KnowledgeAgent.DEFAULT_RESULT)


class TutorRouterResourceIntentTests(SimpleTestCase):
    def test_resource_intent_terms_route_to_resource_agent(self):
        router = TutorAgentRouter()
        for question in ("SQL注入入门资料", "给我SQL注入入门的资源", "有没有 SQL injection documents"):
            with self.subTest(question=question):
                routed = router.route(question)
                self.assertEqual(routed["taskType"], "resource_recommendation")
                self.assertIn("resource_agent", routed["requiredAgents"])

    def test_plain_intro_question_can_stay_question_answer(self):
        routed = TutorAgentRouter().route("sql注入入门")
        self.assertEqual(routed["taskType"], "question_answer")

class PromptAndResponseContractTests(SimpleTestCase):
    def test_optional_teaching_context_keeps_none_context_compatible(self):
        captured = []

        class LegacyChain:
            async def chat_with_agent(self, agent_id, message, context, history):
                captured.append((message, context, history))
                return {"content": "ok"}

        service = AIAssistantService()
        service.service = LegacyChain()
        self.assertEqual(service.chat("hello"), "ok")
        self.assertIsNone(captured[-1][1])
        self.assertEqual(service.chat("hello", teaching_context={"schemaVersion": "1.1", "taskType": "question_answer"}), "ok")
        self.assertEqual(captured[-1][1]["teaching_context"]["schemaVersion"], "1.1")

    def test_response_adapter_filters_internal_fields(self):
        result = build_compatible_chat_response({
            "content": "answer", "workflowId": "hidden", "agentContext": {"secret": 1},
        })
        self.assertEqual(result["answer"], "answer")
        self.assertEqual(result["role"], "assistant")
        self.assertNotIn("workflowId", result)
        self.assertNotIn("agentContext", result)

    def test_response_adapter_preserves_or_adds_timestamp(self):
        preserved = build_compatible_chat_response({"content": "answer", "timestamp": "fixed-time"})
        generated = build_compatible_chat_response({"content": "answer"})
        self.assertEqual(preserved["timestamp"], "fixed-time")
        self.assertTrue(generated["timestamp"])


class FailingRouter:
    def route(self, message):
        raise RuntimeError("router down")


class AnalysisRouter:
    def route(self, message):
        return {
            "taskType": "learning_analysis",
            "requiredAgents": ["learning_analysis_agent", "knowledge_diagnosis_agent", "resource_agent"],
            "matchedRules": ["analysis"], "fallback": False,
        }


class FailingExecutor:
    def execute(self, **kwargs):
        raise RuntimeError("agents down")


class FakeAnswerService:
    def __init__(self): self.calls = []
    def chat(self, **kwargs):
        self.calls.append(kwargs)
        return "legacy answer"


class TutorOrchestratorFallbackTests(SimpleTestCase):
    @override_settings(TUTOR_AGENT_ROUTER_ENABLED=True, TUTOR_SPECIALISTS_ENABLED=True, TUTOR_CONTEXT_ENABLED=True)
    def test_router_and_specialist_failures_still_call_legacy_chain(self):
        answer = FakeAnswerService()
        router_orchestrator = TutorRequestOrchestrator(router=FailingRouter(), answer_service=answer)
        prepared = router_orchestrator.prepare(user=None, message="hello")
        self.assertEqual(prepared["route"]["taskType"], "question_answer")
        self.assertEqual(router_orchestrator.call_legacy_answer(message="hello"), "legacy answer")

        specialist_orchestrator = TutorRequestOrchestrator(
            router=AnalysisRouter(), executor=FailingExecutor(), answer_service=answer,
        )
        prepared = specialist_orchestrator.prepare(user=None, message="analysis")
        result = specialist_orchestrator.call_legacy_answer(
            message="analysis", teaching_context=prepared["teachingContext"],
        )
        self.assertEqual(result, "legacy answer")
        self.assertIn("specialists", prepared["fallbackReasons"])
        self.assertEqual(len(answer.calls), 2)

    @override_settings(TUTOR_AGENT_ROUTER_ENABLED=False, TUTOR_SPECIALISTS_ENABLED=False, TUTOR_CONTEXT_ENABLED=False)
    def test_switches_disable_new_stages_without_blocking(self):
        prepared = TutorRequestOrchestrator().prepare(user=None, message="制定学习计划")
        self.assertEqual(prepared["route"]["taskType"], "question_answer")
        self.assertIsNone(prepared["teachingContext"])


    @override_settings(TUTOR_METRICS_ENABLED=False)
    def test_metrics_switch_disables_request_local_metrics_logging(self):
        metrics = TutorPerformanceMetrics.create(user_id=1)
        self.assertIsNone(activate_metrics(metrics))
        self.assertIsNone(current_metrics())
        with patch("ai_assistant.performance.logger.info") as info:
            log_metrics(metrics)
        info.assert_not_called()


class MainChainApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="chain-user", password="pass12345")
        self.other = User.objects.create_user(username="other-user", password="pass12345")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    @patch("ai_assistant.tutor_request_orchestrator.TutorRequestOrchestrator.call_legacy_answer", return_value="legacy response")
    def test_legacy_conversation_api_compatibility_history_and_isolation(self, legacy_answer):
        conversation = AIConversation.objects.create(user=self.user)
        response = self.client.post(f"/api/ai/conversations/{conversation.id}/chat/", {"message": "hello"}, format="json")
        self.assertEqual(response.status_code, 200)
        for field in ("content", "answer", "role", "timestamp", "conversation_id", "responses", "challenge_info"):
            self.assertIn(field, response.data)
        self.assertEqual(response.data["content"], "legacy response")
        self.assertEqual(AIMessage.objects.filter(conversation=conversation).count(), 2)
        metadata = AIMessage.objects.filter(conversation=conversation, role="assistant").get().metadata
        self.assertIn("taskType", metadata)
        self.assertNotIn("studentProfile", json.dumps(metadata))
        legacy_answer.assert_called_once()

        self.client.force_authenticate(self.other)
        forbidden = self.client.post(f"/api/ai/conversations/{conversation.id}/chat/", {"message": "steal"}, format="json")
        self.assertEqual(forbidden.status_code, 404)

    @patch("ai_assistant.tutor_request_orchestrator.TutorRequestOrchestrator.call_legacy_answer", return_value="legacy response")
    def test_each_tutor_switch_can_be_disabled_without_breaking_legacy_chat_contract(self, legacy_answer):
        switches = (
            "TUTOR_AGENT_ROUTER_ENABLED",
            "TUTOR_SPECIALISTS_ENABLED",
            "TUTOR_CONTEXT_ENABLED",
            "TUTOR_RESOURCE_CACHE_ENABLED",
            "TUTOR_METRICS_ENABLED",
        )
        for switch in switches:
            with self.subTest(switch=switch), self.settings(**{switch: False}):
                conversation = AIConversation.objects.create(user=self.user)
                response = self.client.post(
                    f"/api/ai/conversations/{conversation.id}/chat/",
                    {"message": "hello"},
                    format="json",
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data["content"], "legacy response")
                self.assertEqual(response.data["answer"], "legacy response")
                for field in ("content", "answer", "role", "timestamp", "conversation_id", "responses", "challenge_info"):
                    self.assertIn(field, response.data)
        self.assertEqual(legacy_answer.call_count, len(switches))

    def test_learning_tutoring_api_uses_compatible_envelope(self):
        resource_item = {
            "id": 26,
            "title": "SQL injection intro",
            "type": "ai_resource",
            "entry": "/resources?highlight_resource=26&resource=26",
            "summary": "Basics",
            "score": 0.88,
            "matchScore": 0.77,
            "source": "rag",
        }
        preparation = {
            "route": {"taskType": "resource_recommendation", "requiredAgents": ["resource_agent"]},
            "specialists": {
                "resources": {
                    "resourceList": [resource_item],
                    "resources": [resource_item],
                    "noMatchedResource": False,
                },
                "agentStatus": {},
            },
            "teachingContext": {"resources": {"resourceList": [resource_item]}},
            "fallbackReasons": [],
            "durationMs": 1,
        }

        async def fake_tutoring(self, **kwargs):
            return {"steps": [{"content": "tutor answer", "provider": "fake", "step": 1}]}

        with patch("ai_assistant.views._TUTOR_REQUEST_ORCHESTRATOR.prepare", return_value=preparation), \
             patch("ai_assistant.learning_orchestrator.LearningOrchestrator.tutoring_session", fake_tutoring):
            response = self.client.post("/api/ai/learning/tutoring/", {
                "concept_name": "SQL", "question": "hello", "student_level": "beginner",
            }, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["answer"], "tutor answer")
        self.assertEqual(response.data["role"], "assistant")
        self.assertIn("timestamp", response.data)
        self.assertTrue(response.data["conversation_id"])
        self.assertEqual(response.data["resourceList"][0]["entry"], "/resources?highlight_resource=26&resource=26")
        self.assertNotIn("score", response.data["resourceList"][0])
        conversation = AIConversation.objects.get(id=response.data["conversation_id"])
        metadata = AIMessage.objects.filter(conversation=conversation, role="assistant").latest("created_at").metadata
        self.assertEqual(metadata["resourceList"][0]["title"], "SQL injection intro")
        self.assertNotIn("score", metadata["resourceList"][0])
        self.assertNotIn("matchScore", metadata["resourceList"][0])
        self.assertNotIn("source", metadata["resourceList"][0])

    def test_multi_agent_chat_uses_compatible_envelope(self):
        async def fake_hybrid(**kwargs):
            return {"mode": "collaborative", "responses": [{
                "agent_id": "xiaohei", "agent_name": "xiaohei", "content": "multi answer", "provider": "fake",
            }]}

        with patch("ai_assistant.views.solve_challenge_hybrid_async", fake_hybrid):
            response = self.client.post("/api/ai/multi-agent/chat/", {
                "message": "hello", "agent_ids": ["xiaohei"],
            }, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["answer"], "multi answer")
        self.assertEqual(response.data["content"], "multi answer")
        self.assertIn("timestamp", response.data)
        self.assertNotIn("teaching_context", response.data)


class StreamingHistoryTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.user = User.objects.create_user(username="stream-user", password="pass12345")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_stream_done_uses_compatible_envelope_and_sqlite_history_is_saved(self):
        async def fake_chat(self, agent_id, message, context=None, conversation_history=None):
            return {"agent_id": agent_id, "agent_name": "Agent", "content": "stream answer", "provider": "fake"}

        def fake_knowledge(self, query, challenge_info=None, scope="category", limit=5):
            return {"context_text": "", "scope": scope, "resolved_scope": scope, "items": [], "keywords": [], "cache_hit": False}

        with patch.object(MultiAgentChatService, "chat_with_agent", fake_chat), patch.object(MultiAgentChatService, "build_knowledge_context", fake_knowledge):
            response = self.client.post("/api/ai/multi-agent/chat/stream/", {
                "message": "hello", "agent_ids": ["analyst"],
            }, format="json")
            body = b"".join(response.streaming_content).decode("utf-8")
        done = None
        for block in body.split("\n\n"):
            if block.startswith("event: done"):
                data_line = next(line for line in block.splitlines() if line.startswith("data: "))
                done = json.loads(data_line[6:])
        self.assertIsNotNone(done)
        self.assertEqual(done["content"], "stream answer")
        self.assertEqual(done["answer"], "stream answer")
        self.assertEqual(done["role"], "assistant")
        self.assertIn("timestamp", done)
        conversation = AIConversation.objects.get(id=done["conversation_id"])
        self.assertTrue(AIMessage.objects.filter(conversation=conversation, role="assistant", content="stream answer").exists())
