from django.urls import path
from .views import (
    LearningDirectionListView,
    StudentProfileView,
    OnboardingView,
    PersonaView,
    OnboardingInterviewView,
    StudentProfileReportView,
    PersonaGrowthView,
    DynamicGrowthProfileView,
    StudentProfileReportReviewView,
)

urlpatterns = [
    path('learning-directions/', LearningDirectionListView.as_view(), name='learning-directions'),
    path('me/', StudentProfileView.as_view(), name='student-profile'),
    path('onboarding/', OnboardingView.as_view(), name='onboarding'),
    path('me/persona/', PersonaView.as_view(), name='persona'),
    path('me/growth/', DynamicGrowthProfileView.as_view(), name='dynamic-growth-profile'),
    path('me/persona-growth/', PersonaGrowthView.as_view(), name='persona-growth'),
    path('onboarding/interview/', OnboardingInterviewView.as_view(), name='onboarding-interview'),
    path('me/reports/', StudentProfileReportView.as_view(), name='profile-reports'),
    path('review/reports/', StudentProfileReportReviewView.as_view(), name='profile-report-review'),
]
