from django.urls import path

from .views import (
    HintDisplayView,
    HintRequestView,
    PauseRunView,
    PracticeActionCreateView,
    ResumeRunView,
    StudentAnalysisView,
    TaskTutorView,
    TeacherTicketCreateView,
    TeacherTicketDetailView,
    TeacherTicketHelpView,
    TeachingRunCreateView,
    TeachingRunDetailView,
)


app_name = 'teaching_agent'

urlpatterns = [
    path('runs/', TeachingRunCreateView.as_view(), name='run-create'),
    path('runs/<uuid:run_id>/', TeachingRunDetailView.as_view(), name='run-detail'),
    path('runs/<uuid:run_id>/actions/', PracticeActionCreateView.as_view(), name='practice-action-create'),
    path('runs/<uuid:run_id>/tutor/', TaskTutorView.as_view(), name='task-tutor'),
    path('runs/<uuid:run_id>/hints/request/', HintRequestView.as_view(), name='hint-request'),
    path('runs/<uuid:run_id>/hints/<str:request_id>/display/', HintDisplayView.as_view(), name='hint-display'),
    path('runs/<uuid:run_id>/pause/', PauseRunView.as_view(), name='run-pause'),
    path('runs/<uuid:run_id>/resume/', ResumeRunView.as_view(), name='run-resume'),
    path('runs/<uuid:run_id>/teacher-tickets/', TeacherTicketCreateView.as_view(), name='ticket-create'),
    path('runs/<uuid:run_id>/analysis/', StudentAnalysisView.as_view(), name='student-analysis'),
    path('teacher-tickets/<uuid:ticket_id>/', TeacherTicketDetailView.as_view(), name='ticket-detail'),
    path('teacher-tickets/<uuid:ticket_id>/help/', TeacherTicketHelpView.as_view(), name='ticket-help'),
]
