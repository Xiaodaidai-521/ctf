from django.urls import path
from . import views
from .teacher_views import TeacherMaterialView

urlpatterns = [
    path('cases/', views.CasesView.as_view()),
    path('cases/<str:task_key>/', views.CaseView.as_view()),
    path('cases/<str:task_key>/claim/', views.ClaimView.as_view()),
    path('attempts/<uuid:attempt_id>/', views.AttemptView.as_view()),
    path('attempts/<uuid:attempt_id>/basis/', views.BasisView.as_view()),
    path('attempts/<uuid:attempt_id>/scans/', views.ScansView.as_view()),
    path('scans/<uuid:scan_id>/', views.ScanView.as_view()),
    path('profiles/<uuid:profile_id>/reviews/', views.ReviewsView.as_view()),
    path('attempts/<uuid:attempt_id>/replays/', views.ReplaysView.as_view()),
    path('replays/<uuid:replay_id>/', views.ReplayView.as_view()),
    path('attempts/<uuid:attempt_id>/submissions/', views.SubmissionsView.as_view()),
    path('submissions/<uuid:submission_id>/', views.SubmissionView.as_view()),
    path('attempts/<uuid:attempt_id>/help/', views.HelpView.as_view()),
    path('help/<uuid:request_id>/display/', views.HelpDisplayView.as_view()),
    path('attempts/<uuid:attempt_id>/analysis/', views.AnalysisView.as_view()),
    path('teacher/cases/', views.TeacherCasesView.as_view()),
    path('teacher/cases/<str:task_key>/material/', TeacherMaterialView.as_view()),
    path('teacher/cases/<str:task_key>/attempts/', views.TeacherCaseView.as_view()),
    path('teacher/cases/<str:task_key>/attempts/<uuid:attempt_id>/help/', views.TeacherHelpView.as_view()),
]
