from django.urls import path
from .views import (
    ResourceAdminListView,
    ResourceListView,
    ResourceDetailView,
    ResourceUploadView,
    ResourceMyListView,
    resource_review_view,
    resource_download_view,
)

app_name = 'resources'

urlpatterns = [
    path('', ResourceListView.as_view(), name='list'),
    path('<int:id>/', ResourceDetailView.as_view(), name='detail'),
    path('upload/', ResourceUploadView.as_view(), name='upload'),
    path('my/', ResourceMyListView.as_view(), name='my'),
    path('admin/', ResourceAdminListView.as_view(), name='admin'),
    path('review/', resource_review_view, name='review'),
    path('<int:resource_id>/download/', resource_download_view, name='download'),
]
