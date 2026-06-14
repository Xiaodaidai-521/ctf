from django.urls import path
from . import views

urlpatterns = [
    path('agents/', views.LearningAgentsView.as_view(), name='learning_agents'),
    path('tutoring/', views.TutoringSessionView.as_view(), name='tutoring_session'),
    path('generate/', views.GenerateContentView.as_view(), name='generate_content'),
    path('assess/', views.AssessKnowledgeView.as_view(), name='assess_knowledge'),
    path('recommend/', views.LearningRecommendView.as_view(), name='learning_recommend'),
]
