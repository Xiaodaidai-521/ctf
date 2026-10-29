from django.urls import path
from . import views

urlpatterns = [
    path('materials/', views.MaterialListView.as_view()),
    path('materials/<uuid:material_id>/chunks/', views.ChunksView.as_view()),
    path('materials/<uuid:material_id>/revisions/', views.RevisionView.as_view()),
    path('materials/<uuid:material_id>/<str:action>/', views.ActionView.as_view()),
    path('grants/', views.GrantView.as_view()),
]
