from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ExamLevelRuleViewSet, TheoryQuestionViewSet, PracticeExamViewSet,
    TheoryExamViewSet, ExamRecordViewSet
)

router = DefaultRouter()
router.register(r'level-rules', ExamLevelRuleViewSet, basename='exam-level-rule')
router.register(r'theory-questions', TheoryQuestionViewSet, basename='theory-question')
router.register(r'practice-exams', PracticeExamViewSet, basename='practice-exam')
router.register(r'theory-exams', TheoryExamViewSet, basename='theory-exam')
router.register(r'records', ExamRecordViewSet, basename='exam-record')

urlpatterns = [
    path('', include(router.urls)),
]
