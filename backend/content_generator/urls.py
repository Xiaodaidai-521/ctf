from django.urls import path
from . import views

urlpatterns = [
    path('generate/tutorial/', views.GenerateTutorialView.as_view(), name='generate-tutorial'),
    path('generate/quiz/', views.GenerateQuizView.as_view(), name='generate-quiz'),
    path('generate/diagram/', views.GenerateDiagramView.as_view(), name='generate-diagram'),
    path('generate/exercise/', views.GenerateExerciseView.as_view(), name='generate-exercise'),
    path('<int:pk>/', views.GeneratedContentDetailView.as_view(), name='content-detail'),
    path('<int:pk>/regenerate/', views.RegenerateContentView.as_view(), name='content-regenerate'),
]
