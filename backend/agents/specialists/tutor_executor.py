"""Specialist executor driven exclusively by TASK_EXECUTION_PLAN."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, wait
from contextvars import copy_context
import logging
import time

from django.conf import settings
from django.db import close_old_connections

from agents.task_plan import QUESTION_ANSWER, STUDY_PLAN, TASK_EXECUTION_PLAN, execution_plan_for
from .knowledge_agent import KnowledgeAgent
from .knowledge_diagnosis_agent import KnowledgeDiagnosisAgent
from .learning_analysis_agent import LearningAnalysisAgent
from .cached_resource_agent import ResourceAgent
from .study_strategy_agent import StudyStrategyAgent

logger = logging.getLogger(__name__)


class TutorSpecialistExecutor:
    EMPTY_RESULT = {
        "learningAnalysis": {}, "knowledgeDiagnosis": {}, "knowledgeContext": {},
        "resources": {}, "studyStrategy": {}, "agentStatus": {},
    }
    TARGETS = {
        "learning_analysis_agent": "learningAnalysis",
        "knowledge_diagnosis_agent": "knowledgeDiagnosis",
        "resource_agent": "resources",
        "knowledge_agent": "knowledgeContext",
        "study_strategy_agent": "studyStrategy",
    }

    def __init__(
        self, *, learning_analysis_agent=None, knowledge_diagnosis_agent=None,
        resource_agent=None, knowledge_agent=None, study_strategy_agent=None,
        max_workers=None, agent_timeout=None,
    ):
        self.agents = {
            "learning_analysis_agent": learning_analysis_agent or LearningAnalysisAgent(),
            "knowledge_diagnosis_agent": knowledge_diagnosis_agent or KnowledgeDiagnosisAgent(),
            "resource_agent": resource_agent or ResourceAgent(),
            "knowledge_agent": knowledge_agent or KnowledgeAgent(),
            "study_strategy_agent": study_strategy_agent or StudyStrategyAgent(),
        }
        self.max_workers = min(8, max(1, int(max_workers or getattr(settings, "TUTOR_AGENT_MAX_WORKERS", 3))))
        self.agent_timeout = max(0.05, float(agent_timeout or getattr(settings, "TUTOR_AGENT_TIMEOUT_SECONDS", 8)))

    def execute(
        self, *, task_type, student_id=None, query="", challenge_info=None,
        student_level=None, knowledge_point=None, existing_rag_context=None,
    ):
        canonical = task_type if task_type in TASK_EXECUTION_PLAN else QUESTION_ANSWER
        result = {key: dict(value) for key, value in self.EMPTY_RESULT.items()}
        plan = execution_plan_for(canonical)
        if not plan:
            return result

        first_layer = plan
        dependent = []
        if canonical == STUDY_PLAN:
            first_layer = [name for name in plan if name != "study_strategy_agent"]
            dependent = ["study_strategy_agent"]

        self._run_layer(
            first_layer, result=result, student_id=student_id, query=query,
            challenge_info=challenge_info, student_level=student_level,
            knowledge_point=knowledge_point, existing_rag_context=existing_rag_context,
        )
        self._run_layer(
            dependent, result=result, student_id=student_id, query=query,
            challenge_info=challenge_info, student_level=student_level,
            knowledge_point=knowledge_point, existing_rag_context=existing_rag_context,
        )
        result["agentStatus"] = {
            name: result["agentStatus"][name]
            for name in plan if name in result["agentStatus"]
        }
        return result

    def _run_layer(self, agent_names, **kwargs):
        if not agent_names:
            return
        result = kwargs["result"]
        executor = ThreadPoolExecutor(max_workers=min(self.max_workers, len(agent_names)), thread_name_prefix="tutor-agent")
        future_map = {}
        submitted_at = {}
        try:
            for agent_name in agent_names:
                context = copy_context()
                submitted_at[agent_name] = time.monotonic()
                future = executor.submit(context.run, self._run_worker, agent_name, kwargs)
                future_map[future] = agent_name
            done, pending = wait(future_map, timeout=self.agent_timeout)
            for future in done:
                agent_name = future_map[future]
                started = submitted_at[agent_name]
                try:
                    value = future.result()
                    result[self.TARGETS[agent_name]] = value if isinstance(value, dict) else {}
                    result["agentStatus"][agent_name] = {
                        "status": "success", "durationMs": round((time.monotonic() - started) * 1000, 2),
                    }
                except Exception as exc:
                    self._record_failure(result, agent_name, exc, started)
            for future in pending:
                agent_name = future_map[future]
                future.cancel()
                self._record_failure(result, agent_name, TimeoutError("agent timeout"), submitted_at[agent_name])
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _run_worker(self, agent_name, kwargs):
        close_old_connections()
        try:
            return self._run(agent_name, **kwargs)
        finally:
            close_old_connections()

    def _record_failure(self, result, agent_name, exc, started):
        result["agentStatus"][agent_name] = {
            "status": "fallback", "errorType": type(exc).__name__,
            "durationMs": round((time.monotonic() - started) * 1000, 2),
        }
        logger.warning("tutor_specialist_fallback", extra={
            "event": "tutor_specialist_fallback", "agent": agent_name,
            "error_type": type(exc).__name__,
        })

    def _run(self, agent_name, *, result, student_id, query, challenge_info, student_level, knowledge_point, existing_rag_context):
        agent = self.agents[agent_name]
        if agent_name == "learning_analysis_agent":
            return agent.analyze(student_id)
        if agent_name == "knowledge_diagnosis_agent":
            challenge_id = (challenge_info or {}).get("id") if isinstance(challenge_info, dict) else None
            return agent.analyze(student_id=student_id, query=query, challenge_id=challenge_id)
        if agent_name == "resource_agent":
            return agent.prepare(
                query=query, student_id=student_id, task_type="resource_recommendation",
                student_level=student_level, knowledge_point=knowledge_point,
                existing_rag_context=existing_rag_context,
            )
        if agent_name == "knowledge_agent":
            return agent.analyze(query=query, challenge_info=challenge_info, knowledge_point=knowledge_point)
        if agent_name == "study_strategy_agent":
            return agent.build(
                query=query, learning_analysis=dict(result.get("learningAnalysis") or {}),
                resources=result.get("resources"),
            )
        raise KeyError(agent_name)
