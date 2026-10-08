"""Internal convergence point for all tutoring/chat API requests."""

from __future__ import annotations

import logging
import time

from django.conf import settings

from agents.context.teaching_context import SharedTeachingContextBuilder
from agents.context.student_profile_adapter import StudentProfileContextAdapter
from agents.router.tutor_router import TutorAgentRouter
from agents.specialists.tutor_executor import TutorSpecialistExecutor
from agents.task_plan import QUESTION_ANSWER, execution_plan_for
from .performance import TutorPerformanceMetrics, activate_metrics, log_metrics
from .response_adapter import build_compatible_chat_response

logger = logging.getLogger(__name__)


class TutorRequestOrchestrator:
    """Prepare bounded context, call the legacy answer chain, and adapt output."""

    def __init__(self, *, router=None, executor=None, profile_adapter=None, context_builder=None, answer_service=None):
        self.router = router or TutorAgentRouter()
        self.executor = executor or TutorSpecialistExecutor()
        self.profile_adapter = profile_adapter or StudentProfileContextAdapter()
        self.context_builder = context_builder or SharedTeachingContextBuilder()
        self.answer_service = answer_service

    @staticmethod
    def _enabled(name, default=True):
        return bool(getattr(settings, name, default))

    def prepare(self, *, user, message, conversation=None, challenge_info=None, conversation_history=None, existing_request_data=None):
        started = time.monotonic()
        metrics = TutorPerformanceMetrics.create(
            user_id=getattr(user, "id", None), conversation_id=getattr(conversation, "id", None),
        )
        activate_metrics(metrics)
        request_data = existing_request_data if isinstance(existing_request_data, dict) else {}
        route = TutorAgentRouter.fallback_result()
        specialists = {key: dict(value) for key, value in TutorSpecialistExecutor.EMPTY_RESULT.items()}
        fallback_reasons = []

        router_started = time.monotonic()
        if self._enabled("TUTOR_AGENT_ROUTER_ENABLED", True):
            try:
                route = self.router.route(message)
            except Exception as exc:
                fallback_reasons.append("router")
                logger.warning("tutor_orchestrator_router_fallback", extra={
                    "event": "tutor_orchestrator_router_fallback", "request_id": metrics.request_id,
                    "error_type": type(exc).__name__,
                })
        metrics.router_duration_ms = (time.monotonic() - router_started) * 1000
        task_type = route.get("taskType") or QUESTION_ANSWER
        route["requiredAgents"] = execution_plan_for(task_type)
        metrics.task_type = task_type
        metrics.required_agents = list(route["requiredAgents"])

        if self._enabled("TUTOR_SPECIALISTS_ENABLED", True) and route["requiredAgents"]:
            try:
                specialists = self.executor.execute(
                    task_type=task_type, student_id=getattr(user, "id", None), query=message,
                    challenge_info=challenge_info,
                    student_level=request_data.get("student_level") or request_data.get("studentLevel"),
                    knowledge_point=request_data.get("knowledge_point") or request_data.get("knowledgePoint") or request_data.get("concept_name"),
                    existing_rag_context=request_data.get("existing_rag_context"),
                )
                metrics.agent_metrics = specialists.get("agentStatus") or {}
                required_statuses = [metrics.agent_metrics.get(name, {}).get("status") for name in route["requiredAgents"]]
                if required_statuses and all(status != "success" for status in required_statuses):
                    fallback_reasons.append("all_specialists")
            except Exception as exc:
                fallback_reasons.append("specialists")
                logger.warning("tutor_orchestrator_specialists_fallback", extra={
                    "event": "tutor_orchestrator_specialists_fallback", "request_id": metrics.request_id,
                    "task_type": task_type, "error_type": type(exc).__name__,
                })

        resources = specialists.get("resources") or {}
        metrics.resource_cache_hit = bool(resources.get("cacheHit", False))
        teaching_context = None
        if self._enabled("TUTOR_CONTEXT_ENABLED", True):
            try:
                teaching_context = self.context_builder.build(
                    student_id=getattr(user, "id", ""), question=message, task_type=task_type,
                    student_profile=self.profile_adapter.build(user),
                    learning_analysis=specialists.get("learningAnalysis"),
                    knowledge_diagnosis=specialists.get("knowledgeDiagnosis"),
                    knowledge_context=specialists.get("knowledgeContext"),
                    resources=resources, study_strategy=specialists.get("studyStrategy"),
                    conversation_history=conversation_history, extensions={"challenge": challenge_info or {}},
                )
            except Exception as exc:
                fallback_reasons.append("context")
                logger.warning("tutor_orchestrator_context_fallback", extra={
                    "event": "tutor_orchestrator_context_fallback", "request_id": metrics.request_id,
                    "error_type": type(exc).__name__,
                })
        metrics.fallback_used = bool(fallback_reasons) or any(
            item.get("status") == "fallback" for item in metrics.agent_metrics.values()
        )
        return {
            "route": route, "specialists": specialists, "teachingContext": teaching_context,
            "fallbackReasons": fallback_reasons,
            "durationMs": round((time.monotonic() - started) * 1000, 2),
            "conversation": conversation, "performanceMetrics": metrics,
        }

    def call_legacy_answer(self, *, message, conversation_history=None, challenge_info=None, teaching_context=None):
        from .service import get_ai_assistant_service
        service = self.answer_service or get_ai_assistant_service()
        try:
            return service.chat(user_message=message, conversation_history=conversation_history, challenge_info=challenge_info, teaching_context=teaching_context)
        except TypeError as exc:
            if "teaching_context" not in str(exc):
                raise
            logger.warning("tutor_legacy_signature_fallback", extra={"event": "tutor_legacy_signature_fallback", "error_type": type(exc).__name__})
            return service.chat(user_message=message, conversation_history=conversation_history, challenge_info=challenge_info)

    def call_existing_answer_chain(self, preparation, answer_chain):
        teaching_context = preparation.get("teachingContext")
        try:
            return answer_chain(teaching_context)
        except Exception as exc:
            if teaching_context is None:
                raise
            preparation.setdefault("fallbackReasons", []).append("answer_chain_context")
            preparation["performanceMetrics"].fallback_used = True
            logger.warning("tutor_answer_chain_context_fallback", extra={"event": "tutor_answer_chain_context_fallback", "error_type": type(exc).__name__})
            return answer_chain(None)

    async def call_existing_answer_chain_async(self, preparation, answer_chain):
        teaching_context = preparation.get("teachingContext")
        try:
            return await answer_chain(teaching_context)
        except Exception as exc:
            if teaching_context is None:
                raise
            preparation.setdefault("fallbackReasons", []).append("answer_chain_context")
            preparation["performanceMetrics"].fallback_used = True
            logger.warning("tutor_answer_chain_context_fallback", extra={"event": "tutor_answer_chain_context_fallback", "error_type": type(exc).__name__})
            return await answer_chain(None)

    def adapt_response(self, preparation, payload=None, *, responses=None, conversation_id=None, challenge_info=None, metadata=None):
        metrics = preparation.get("performanceMetrics")
        if metrics:
            if conversation_id is not None:
                metrics.conversation_id = conversation_id
            log_metrics(metrics)
        return build_compatible_chat_response(
            payload, responses=responses, conversation_id=conversation_id, challenge_info=challenge_info,
            specialist_result=preparation.get("specialists"), metadata=metadata or self.metadata_summary(preparation),
        )

    @staticmethod
    def metadata_summary(preparation):
        route = preparation.get("route") or {}
        specialists = preparation.get("specialists") or {}
        resources = specialists.get("resources") or {}
        context = preparation.get("teachingContext") or {}
        metrics = preparation.get("performanceMetrics")
        return {
            "taskType": route.get("taskType", QUESTION_ANSWER),
            "requiredAgents": list(route.get("requiredAgents") or []),
            "agentStatus": specialists.get("agentStatus") or {},
            "cacheHit": bool(resources.get("cacheHit", False)),
            "requestId": metrics.request_id if metrics else None,
            "performance": metrics.as_dict() if metrics else {},
            "teachingContext": {
                "schemaVersion": context.get("schemaVersion"), "taskType": context.get("taskType"),
                "hasStudentProfile": bool(context.get("studentProfile")),
                "resourceCount": len((context.get("resources") or {}).get("resourceList") or (context.get("resources") or {}).get("resources") or []),
            } if context else {},
            "duration": preparation.get("durationMs", 0),
            "fallbackReasons": list(preparation.get("fallbackReasons") or []),
        }
