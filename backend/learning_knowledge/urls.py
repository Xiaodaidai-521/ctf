from django.urls import path
from . import views

urlpatterns = [
    path('search/', views.SearchView.as_view()),
    path('evidence/<uuid:evidence_id>/', views.EvidenceView.as_view()),
    path('evidence/<uuid:evidence_id>/download/', views.EvidenceDownloadView.as_view()),
    path('evidence-issues/', views.IssueView.as_view()),
]
