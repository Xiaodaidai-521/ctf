from django.urls import path

from . import views


app_name = 'agent_runtime'

urlpatterns = [
    path('learning-runs/', views.LearningRunCreateView.as_view(), name='learning_run_create'),
    path('runs/', views.AgentRunListView.as_view(), name='run_list'),
    path('runs/<int:pk>/', views.AgentRunDetailView.as_view(), name='run_detail'),
]
