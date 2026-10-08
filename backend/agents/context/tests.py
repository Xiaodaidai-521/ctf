import json
from datetime import datetime

from unittest import TestCase

from .teaching_context import TeachingContext, TeachingContextBuilder


class TeachingContextTests(TestCase):
    def test_empty_context_returns_default_json_shape(self):
        payload = TeachingContext.empty().to_dict()

        self.assertEqual(payload["schemaVersion"], "1.1")
        self.assertEqual(payload["studentId"], "")
        self.assertEqual(payload["question"], "")
        self.assertEqual(payload["taskType"], "")
        self.assertEqual(payload["learningAnalysis"], {})
        self.assertEqual(payload["knowledgeDiagnosis"], {})
        self.assertEqual(payload["resources"], {})
        self.assertEqual(payload["conversationHistory"], {"recentMessages": [], "summary": ""})
        self.assertEqual(payload["extensions"]["exam"], {})
        self.assertEqual(payload["extensions"]["wrongQuestion"], {})
        self.assertEqual(payload["extensions"]["teacherFeedback"], {})
        self.assertEqual(payload["extensions"]["teacherInstruction"], {})
        json.dumps(payload)

    def test_builder_maps_specialist_results_to_standard_sections(self):
        payload = (
            TeachingContextBuilder()
            .with_student(42)
            .with_question("How should I study SQL injection?")
            .with_task_type("study_plan")
            .with_specialist_results({
                "learningAnalysis": {"riskLevel": "medium"},
                "knowledgeDiagnosis": {"masteryScore": 62},
                "resourcePreparation": {"resources": [{"id": "1", "title": "SQL basics"}]},
            })
            .build_dict()
        )

        self.assertEqual(payload["studentId"], "42")
        self.assertEqual(payload["taskType"], "study_plan")
        self.assertEqual(payload["learningAnalysis"], {"riskLevel": "medium"})
        self.assertEqual(payload["knowledgeDiagnosis"], {"masteryScore": 62})
        self.assertEqual(payload["resources"]["resources"][0]["title"], "SQL basics")

    def test_context_sanitizes_non_json_values(self):
        payload = (
            TeachingContextBuilder()
            .with_learning_analysis({"generatedAt": datetime(2026, 7, 16, 8, 0, 0)})
            .with_extension("exam", {"ids": {3, 1}})
            .build_dict()
        )

        json.dumps(payload)
        self.assertEqual(payload["learningAnalysis"]["generatedAt"], "2026-07-16T08:00:00")
        self.assertEqual(sorted(payload["extensions"]["exam"]["ids"]), [1, 3])
