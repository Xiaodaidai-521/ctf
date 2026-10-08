"""Backward-compatible specialist executor driven by TASK_EXECUTION_PLAN."""

from __future__ import annotations

from typing import Dict, Optional

from agents.context.teaching_context import SharedTeachingContextBuilder
from agents.task_plan import QUESTION_ANSWER

from .knowledge_agent import KnowledgeAgent
from .knowledge_diagnosis_agent import KnowledgeDiagnosisAgent
from .learning_analysis_agent import LearningAnalysisAgent
from .resource_agent import ResourceAgent
from .study_strategy_agent import StudyStrategyAgent
from .tutor_executor import TutorSpecialistExecutor


class SpecialistAgentExecutor:
    """Compatibility adapter; execution is delegated to the canonical executor."""

    DEFAULT_RESULT = {
        "learningAnalysis": {}, "knowledgeDiagnosis": {}, "knowledgeContext": {},
        "resourcePreparation": {}, "studyStrategy": {}, "agentStatus": {},
        "teachingContext": {}, "context": {},
    }

    def __init__(
        self, *, learning_analysis_agent: Optional[LearningAnalysisAgent] = None,
        knowledge_diagnosis_agent: Optional[KnowledgeDiagnosisAgent] = None,
        resource_agent: Optional[ResourceAgent] = None,
        knowledge_agent: Optional[KnowledgeAgent] = None,
        study_strategy_agent: Optional[StudyStrategyAgent] = None,
    ):
        self.delegate = TutorSpecialistExecutor(
            learning_analysis_agent=learning_analysis_agent,
            knowledge_diagnosis_agent=knowledge_diagnosis_agent,
            resource_agent=resource_agent,
            knowledge_agent=knowledge_agent,
            study_strategy_agent=study_strategy_agent,
        )

    def execute(
        self, *, agent_route: Optional[Dict], student_id: Optional[int], query: str = "",
        challenge_id: Optional[int] = None, student_level: Optional[str] = None,
        knowledge_point: Optional[str] = None, existing_rag_context: Optional[Dict] = None,
    ) -> Dict:
        task_type = (agent_route or {}).get("taskType") or QUESTION_ANSWER
        challenge_info = {"id": challenge_id} if challenge_id else None
        canonical = self.delegate.execute(
            task_type=task_type, student_id=student_id, query=query,
            challenge_info=challenge_info, student_level=student_level,
            knowledge_point=knowledge_point, existing_rag_context=existing_rag_context,
        )
        teaching_context = SharedTeachingContextBuilder().build(
            student_id=student_id, question=query, task_type=task_type,
            learning_analysis=canonical.get("learningAnalysis"),
            knowledge_diagnosis=canonical.get("knowledgeDiagnosis"),
            knowledge_context=canonical.get("knowledgeContext"),
            resources=canonical.get("resources"),
            study_strategy=canonical.get("studyStrategy"),
        )
        return {
            **canonical,
            "resourcePreparation": canonical.get("resources") or {},
            "teachingContext": teaching_context,
            "context": {"teaching_context": teaching_context},
        }
