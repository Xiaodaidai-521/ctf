from django.test import SimpleTestCase

from agents.task_plan import TASK_EXECUTION_PLAN
from .study_strategy_agent import StudyStrategyAgent
from .tutor_executor import TutorSpecialistExecutor


class Learning:
    def analyze(self, student_id): return {"riskLevel": "high"}


class Diagnosis:
    def analyze(self, **kwargs): return {"weakKnowledgePoints": [{"name": "SQL"}]}


class Resources:
    def prepare(self, **kwargs): return {"resourceList": [{"id": "r1", "title": "SQL"}], "cacheHit": True}


class Knowledge:
    def analyze(self, **kwargs): return {"knowledgePoint": "SQL", "definition": "definition"}


class Broken:
    def analyze(self, *args, **kwargs): raise RuntimeError("boom")


class TutorSpecialistExecutorTests(SimpleTestCase):
    def executor(self, **overrides):
        values = dict(
            learning_analysis_agent=Learning(), knowledge_diagnosis_agent=Diagnosis(),
            resource_agent=Resources(), knowledge_agent=Knowledge(),
            study_strategy_agent=StudyStrategyAgent(),
        )
        values.update(overrides)
        return TutorSpecialistExecutor(**values)

    def test_every_task_uses_the_canonical_execution_matrix(self):
        executor = self.executor()
        for task_type, plan in TASK_EXECUTION_PLAN.items():
            with self.subTest(task_type=task_type):
                result = executor.execute(task_type=task_type, student_id=1, query="SQL")
                self.assertEqual(list(result["agentStatus"]), plan)

    def test_structured_agents_fill_expected_sections(self):
        result = self.executor().execute(task_type="learning_analysis", student_id=1, query="SQL")
        self.assertEqual(result["learningAnalysis"]["riskLevel"], "high")
        self.assertEqual(result["knowledgeDiagnosis"]["weakKnowledgePoints"][0]["name"], "SQL")
        self.assertEqual(result["resources"]["resourceList"][0]["id"], "r1")

    def test_agent_exception_is_structured_and_does_not_abort(self):
        result = self.executor(learning_analysis_agent=Broken()).execute(
            task_type="learning_analysis", student_id=1, query="SQL",
        )
        self.assertEqual(result["learningAnalysis"], {})
        self.assertEqual(result["agentStatus"]["learning_analysis_agent"]["status"], "fallback")
        self.assertEqual(result["resources"]["resourceList"][0]["id"], "r1")

    def test_study_strategy_empty_and_normal_data(self):
        agent = StudyStrategyAgent()
        empty = agent.build()
        normal = agent.build(
            query="learn SQL",
            learning_analysis={"riskLevel": "high", "weakKnowledgePoints": [{"name": "SQL"}]},
            resources={"resourceList": [{"id": "1"}]},
        )
        self.assertEqual(empty["dailyMinutes"], 45)
        self.assertEqual(normal["dailyMinutes"], 60)
        self.assertEqual(normal["priorityKnowledgePoints"], ["SQL"])

