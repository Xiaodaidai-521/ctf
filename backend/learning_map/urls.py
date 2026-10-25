from django.urls import path

from . import views


urlpatterns = [
    path('status/', views.ModuleStatusView.as_view(), name='learning-map-status'),
    path('catalog/', views.CatalogView.as_view(), name='learning-map-catalog'),
    path('teacher/catalog/', views.TeacherCatalogView.as_view(), name='learning-map-teacher-catalog'),

    path('me/map/', views.MyMapView.as_view(), name='learning-map-my-map'),
    path('teacher/students/<int:student_id>/map/', views.TeacherStudentMapView.as_view(), name='learning-map-student-map'),

    path('diagnostic/questions/', views.DiagnosticQuestionsView.as_view(), name='learning-map-diagnostic-questions'),
    path('diagnostic/submit/', views.DiagnosticSubmitView.as_view(), name='learning-map-diagnostic-submit'),

    path('me/recommendations/', views.MyRecommendationsView.as_view(), name='learning-map-my-recommendations'),
    path('teacher/students/<int:student_id>/recommendations/', views.TeacherStudentRecommendationsView.as_view(), name='learning-map-student-recommendations'),

    path('me/attempts/', views.AttemptListView.as_view(), name='learning-map-my-attempts'),
    path('tasks/<int:task_id>/claim/', views.ClaimTaskView.as_view(), name='learning-map-claim-task'),
    path('attempts/<uuid:attempt_id>/submit/', views.SubmitAttemptView.as_view(), name='learning-map-submit-attempt'),

    path('verification-facts/', views.VerificationFactIngestView.as_view(), name='learning-map-verification-facts'),
    path('me/changelog/', views.MyChangelogView.as_view(), name='learning-map-my-changelog'),
    path('teacher/students/<int:student_id>/changelog/', views.TeacherStudentChangelogView.as_view(), name='learning-map-student-changelog'),

    path('teacher/adjustments/', views.TeacherAdjustmentView.as_view(), name='learning-map-adjustments'),

    path('delivery-register/', views.DeliveryRegisterView.as_view(), name='learning-map-delivery-register'),
    path('delivery-register/<str:delivery_no>/', views.DeliveryRegisterDetailView.as_view(), name='learning-map-delivery-register-detail'),

    path('admin/catalog/<str:version>/freeze/', views.CatalogFreezeView.as_view(), name='learning-map-freeze-catalog'),
    path('admin/catalog/<str:version>/publish/', views.CatalogPublishView.as_view(), name='learning-map-publish-catalog'),
    path('export/catalog/<str:version>/', views.CatalogExportView.as_view(), name='learning-map-export-catalog'),
]
