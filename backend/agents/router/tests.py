from django.test import SimpleTestCase

from agents.task_plan import TASK_EXECUTION_PLAN
from . import AgentRouter


class TutorAgentRouterTests(SimpleTestCase):
    CASES = (
        ("为什么成绩下降", "learning_analysis"),
        ("分析我的学习进度", "learning_analysis"),
        ("解释 SQL 注入", "knowledge_explanation"),
        ("什么是 TCP 三次握手", "knowledge_explanation"),
        ("制定一个学习计划", "study_plan"),
        ("推荐相关资源", "resource_recommendation"),
        ("今天天气不错", "question_answer"),
        ("", "question_answer"),
        ("解释 SQL 注入并制定一个学习计划", "study_plan"),
        ("Explain SQL injection", "knowledge_explanation"),
        ("Recommend learning resources", "resource_recommendation"),
    )

    def test_routes_are_deterministic_and_share_the_execution_plan(self):
        router = AgentRouter()
        for question, expected in self.CASES:
            with self.subTest(question=question):
                result = router.route(question)
                self.assertEqual(result["taskType"], expected)
                self.assertEqual(result["requiredAgents"], TASK_EXECUTION_PLAN[expected])
                self.assertIn("matchedRules", result)
                self.assertEqual(result["fallback"], expected == "question_answer")

    def test_empty_and_non_string_input_never_raise(self):
        self.assertEqual(AgentRouter().route(None)["taskType"], "question_answer")
        self.assertEqual(AgentRouter().route({})["taskType"], "question_answer")

