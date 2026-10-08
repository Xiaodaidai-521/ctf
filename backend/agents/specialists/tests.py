from unittest import TestCase

from agents.router import AgentRouter

from .executor import SpecialistAgentExecutor


class _LearningAgent:
    def analyze(self, student_id):
        return {"riskLevel": "medium"}


class _KnowledgeAgent:
    def analyze(self, *, student_id, query="", challenge_id=None):
        return {"masteryScore": 68}


class _ResourceAgent:
    def prepare(self, *, query, student_id=None, task_type=None, **kwargs):
        return {"resources": [{"id": "r1", "title": "SQL basics"}]}


class SpecialistAgentExecutorTeachingContextTests(TestCase):
    def test_executor_writes_structured_results_into_teaching_context(self):
        executor = SpecialistAgentExecutor(
            learning_analysis_agent=_LearningAgent(),
            knowledge_diagnosis_agent=_KnowledgeAgent(),
            resource_agent=_ResourceAgent(),
        )

        result = executor.execute(
            agent_route={"taskType": AgentRouter.STUDY_PLAN},
            student_id=7,
            query="How should I study SQL injection?",
        )

        self.assertEqual(result["learningAnalysis"], {"riskLevel": "medium"})
        self.assertEqual(result["knowledgeDiagnosis"], {})
        self.assertEqual(result["resourcePreparation"]["resources"][0]["id"], "r1")

        teaching_context = result["teachingContext"]
        self.assertEqual(teaching_context["schemaVersion"], "1.1")
        self.assertEqual(teaching_context["studentId"], "7")
        self.assertEqual(teaching_context["taskType"], AgentRouter.STUDY_PLAN)
        self.assertEqual(teaching_context["learningAnalysis"], {"riskLevel": "medium"})
        self.assertEqual(teaching_context["knowledgeDiagnosis"], {})
        self.assertEqual(teaching_context["resources"]["resources"][0]["title"], "SQL basics")
        self.assertEqual(result["context"]["teaching_context"], teaching_context)
