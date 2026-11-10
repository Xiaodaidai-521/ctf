from django.urls import path
from .views import (
    ResourceAdminListView,
    ResourceListView,
    ResourceDetailView,
    ResourceUploadView,
    ResourceMyListView,
    resource_review_view,
    resource_download_view,
    resource_cover_download_view,
    resource_file_operation_view,
    resource_share_view,
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
    path('<int:resource_id>/cover/download/', resource_cover_download_view, name='cover-download'),
    path('file-operations/<uuid:operation_id>/', resource_file_operation_view, name='file-operation'),
    path('<int:resource_id>/shares/', resource_share_view, name='share'),
    path('<int:resource_id>/cover/shares/', resource_share_view, {'field': 'cover_image'}, name='cover-share'),
]
