from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'challenges', views.ChallengeViewSet, basename='challenge')

app_name = 'challenges'

urlpatterns = [
    path('', include(router.urls)),
    path('categories/', views.CategoryListView.as_view(), name='category_list'),
    path('challenge/<int:pk>/', views.challenge_detail_view, name='challenge_detail'),
]

