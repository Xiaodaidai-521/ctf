from django.urls import path

from .pipeline_views import LearningEffectSummaryView, LearningEventBatchView
from .views import (
    AdminLearningScoreView,
    AdminStudentReportView,
    AdminTeachingPlanView,
    InsightsView,
    KnowledgeMapView,
    ProgressReportView,
    ResourceLearningFeedbackView,
    ResourceLearningFeedbackDetailView,
    TeachingPlanView,
    TeacherAdjustmentView,
    TeacherAdjustmentEffectView,
    TeacherAdjustmentProposalView,
    TeacherLearningEffectView,
    TeacherLearningScoreView,
    TeacherStudentBehaviorView,
    TeacherStudentReportView,
    TeacherTeachingPlanView,
    WeeklySummaryView,
)

urlpatterns = [
    path('learning/events/batch/', LearningEventBatchView.as_view(), name='learning-event-batch'),
    path('learning/effect/', LearningEffectSummaryView.as_view(), name='learning-effect-summary'),
    path('insights/', InsightsView.as_view(), name='learning-insights'),
    path('weekly-summary/', WeeklySummaryView.as_view(), name='weekly-summary'),
    path('progress-report/', ProgressReportView.as_view(), name='progress-report'),
    path('knowledge-map/', KnowledgeMapView.as_view(), name='knowledge-map'),
    path('admin/student-report/', AdminStudentReportView.as_view(), name='admin-student-report'),
    path('admin/scores/', AdminLearningScoreView.as_view(), name='admin-learning-scores'),
    path('teaching-plan/', TeachingPlanView.as_view(), name='teaching-plan'),
    path('admin/teaching-plan/<int:student_id>/', AdminTeachingPlanView.as_view(), name='admin-teaching-plan'),
    path('resource-feedback/', ResourceLearningFeedbackView.as_view(), name='resource-learning-feedback'),
    path('resource-feedback/<int:resource_id>/', ResourceLearningFeedbackDetailView.as_view(), name='resource-learning-feedback-detail'),
    path('teacher/students/<int:student_id>/behavior/', TeacherStudentBehaviorView.as_view(), name='teacher-student-behavior'),
    path('teacher/proposals/', TeacherAdjustmentProposalView.as_view(), name='teacher-adjustment-proposals'),
    path('teacher/proposals/<int:proposal_id>/effect/', TeacherAdjustmentEffectView.as_view(), name='teacher-adjustment-effect'),
    path('teacher/learning-effect/', TeacherLearningEffectView.as_view(), name='teacher-learning-effect'),
    path('teacher/adjustments/<int:adjustment_id>/', TeacherAdjustmentView.as_view(), name='teacher-adjustment'),
    path('teacher/scores/', TeacherLearningScoreView.as_view(), name='teacher-learning-scores'),
    path('teacher/teaching-plan/<int:student_id>/', TeacherTeachingPlanView.as_view(), name='teacher-teaching-plan'),
    path('teacher/student-report/', TeacherStudentReportView.as_view(), name='teacher-student-report'),
]

