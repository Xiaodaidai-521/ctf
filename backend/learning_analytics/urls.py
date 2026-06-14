from django.urls import path

from .views import (
    AdminLearningScoreView,
    AdminStudentReportView,
    AdminTeachingPlanView,
    InsightsView,
    KnowledgeMapView,
    ProgressReportView,
    TeachingPlanView,
    WeeklySummaryView,
)

urlpatterns = [
    path('insights/', InsightsView.as_view(), name='learning-insights'),
    path('weekly-summary/', WeeklySummaryView.as_view(), name='weekly-summary'),
    path('progress-report/', ProgressReportView.as_view(), name='progress-report'),
    path('knowledge-map/', KnowledgeMapView.as_view(), name='knowledge-map'),
    path('admin/student-report/', AdminStudentReportView.as_view(), name='admin-student-report'),
    path('admin/scores/', AdminLearningScoreView.as_view(), name='admin-learning-scores'),
    path('teaching-plan/', TeachingPlanView.as_view(), name='teaching-plan'),
    path('admin/teaching-plan/<int:student_id>/', AdminTeachingPlanView.as_view(), name='admin-teaching-plan'),
]
