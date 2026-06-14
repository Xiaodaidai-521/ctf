from django.urls import path
from . import views

app_name = 'submissions'

urlpatterns = [
    path('my/', views.MySubmissionListView.as_view(), name='my_submissions'),
    path('all/', views.SubmissionListView.as_view(), name='all_submissions'),
    path('stats/', views.submission_stats_view, name='submission_stats'),
    path('admin/stats/', views.admin_submission_stats_view, name='admin_submission_stats'),
]
