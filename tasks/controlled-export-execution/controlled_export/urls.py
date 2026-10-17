from django.urls import path

from .views import (
    CreateShareView,
    ExecuteExportView,
    RecordDeliveryResultView,
    RevokeShareView,
    RotateShareTokenView,
    ShareAccessView,
)


urlpatterns = [
    path("executions/", ExecuteExportView.as_view(), name="controlled-export-execute"),
    path("shares/", CreateShareView.as_view(), name="controlled-export-share-create"),
    path("shares/<uuid:share_id>/rotate-token/", RotateShareTokenView.as_view(), name="controlled-export-share-rotate"),
    path("shares/<uuid:share_id>/revoke/", RevokeShareView.as_view(), name="controlled-export-share-revoke"),
    path("shares/<uuid:share_id>/<str:operation>/", ShareAccessView.as_view(), name="controlled-export-share-access"),
    path(
        "deliveries/<uuid:delivery_id>/result/",
        RecordDeliveryResultView.as_view(),
        name="controlled-export-delivery-result",
    ),
]
