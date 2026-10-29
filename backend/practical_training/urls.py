from django.urls import path
from . import views

app_name = 'practical_training'
urlpatterns = [
    path('assignments/<uuid:assignment_id>/review/', views.ReviewView.as_view()),
    path('mappings/<int:mapping_id>/control/', views.MappingControlView.as_view()),
    path('mappings/<int:mapping_id>/review/', views.MappingReviewView.as_view()),
    path('environments/<int:container_id>/approve/', views.EnvironmentApprovalView.as_view()),
    path('assignments/<uuid:assignment_id>/control/', views.AssignmentControlView.as_view()),
    path('assignments/<uuid:assignment_id>/repair/', views.RepairView.as_view()),
    path('assignments/<uuid:assignment_id>/repair/<uuid:claim_id>/verify/', views.RepairVerifyView.as_view()),
    path('assignments/<uuid:assignment_id>/start/', views.StartView.as_view()),
    path('assignments/<uuid:assignment_id>/verify/', views.VerifyView.as_view()),
    path('assignments/<uuid:assignment_id>/self-report/', views.SelfReportView.as_view()),
    path('assignments/<uuid:assignment_id>/evidence/<uuid:evidence_id>/', views.EvidenceView.as_view()),
    path('mappings/', views.MappingListView.as_view()),
    path('mappings/<int:mapping_id>/claim/', views.AllocateView.as_view()),
    path('assignments/', views.AssignmentListView.as_view()),
    path('assignments/<uuid:assignment_id>/', views.AssignmentView.as_view()),
    path('assignments/<uuid:assignment_id>/hints/', views.HintRequestView.as_view()),
    path('assignments/<uuid:assignment_id>/hints/<uuid:record_id>/display/', views.HintDisplayView.as_view()),
]
