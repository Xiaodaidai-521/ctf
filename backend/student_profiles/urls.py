from django.urls import path
from .views import (
    LearningDirectionListView,
    StudentProfileView,
    OnboardingView,
    PersonaView,
)

urlpatterns = [
    path('learning-directions/', LearningDirectionListView.as_view(), name='learning-directions'),
    path('me/', StudentProfileView.as_view(), name='student-profile'),
    path('onboarding/', OnboardingView.as_view(), name='onboarding'),
    path('me/persona/', PersonaView.as_view(), name='persona'),
]
