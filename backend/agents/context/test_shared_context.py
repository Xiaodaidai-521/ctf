import json

from django.contrib.auth import get_user_model
from django.test import TestCase

from student_profiles.models import LearningPersona, LearningPreference, StudentProfile
from .teaching_context import SharedTeachingContextBuilder
from .student_profile_adapter import StudentProfileContextAdapter


class SharedTeachingContextTests(TestCase):
    def test_bounds_history_resources_weak_points_rag_and_sensitive_fields(self):
        payload = SharedTeachingContextBuilder().build(
            student_id=7,
            question="q",
            task_type="learning_analysis",
            student_profile={"email": "secret@example.com", "learningGoals": "goal", "token": "secret"},
            knowledge_diagnosis={"weakKnowledgePoints": list(range(12))},
            knowledge_context={"retrievalContext": [{"text": "x" * 2000}] * 10},
            resources={"resourceList": [{"id": i} for i in range(20)]},
            conversation_history=[{"role": "user", "content": str(i) + "x" * 900, "token": "bad"} for i in range(12)],
        )
        self.assertEqual(payload["schemaVersion"], "1.1")
        self.assertEqual(len(payload["conversationHistory"]["recentMessages"]), 8)
        self.assertLessEqual(len(payload["conversationHistory"]["recentMessages"][0]["content"]), 500)
        self.assertEqual(len(payload["knowledgeDiagnosis"]["weakKnowledgePoints"]), 5)
        self.assertEqual(len(payload["resources"]["resourceList"]), 8)
        self.assertNotIn("email", payload["studentProfile"])
        self.assertNotIn("token", json.dumps(payload).lower())
        self.assertLessEqual(len(json.dumps(payload["knowledgeContext"], ensure_ascii=False)), 7000)
        json.dumps(payload)

    def test_profile_adapter_returns_only_teaching_fields(self):
        user = get_user_model().objects.create_user(
            username="profile-user", password="secret", email="private@example.com",
        )
        profile = StudentProfile.objects.create(user=user, learning_goals="learn sql", self_assessed_skills={"sql": 1})
        LearningPreference.objects.create(profile=profile, daily_study_hours=1.5)
        LearningPersona.objects.create(profile=profile, persona_label="visual")
        result = StudentProfileContextAdapter().build(user)
        serialized = json.dumps(result).lower()
        self.assertEqual(result["learningGoals"], "learn sql")
        self.assertNotIn("email", serialized)
        self.assertNotIn("password", serialized)
        self.assertNotIn("token", serialized)

    def test_profile_adapter_failure_is_empty(self):
        self.assertEqual(StudentProfileContextAdapter().build(None), {})

