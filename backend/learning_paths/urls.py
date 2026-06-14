from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    LearningPathViewSet, PathModuleViewSet, UserProgressViewSet,
    RecommendationViewSet, KnowledgeConceptViewSet, LabAttemptViewSet
)

router = DefaultRouter()
router.register(r'paths', LearningPathViewSet, basename='learning-path')
router.register(r'modules', PathModuleViewSet, basename='path-module')
router.register(r'progress', UserProgressViewSet, basename='user-progress')
router.register(r'recommendations', RecommendationViewSet, basename='recommendations')
router.register(r'knowledge-concepts', KnowledgeConceptViewSet, basename='knowledge-concept')
router.register(r'lab-attempts', LabAttemptViewSet, basename='lab-attempt')

urlpatterns = [
    path('', include(router.urls)),
]
