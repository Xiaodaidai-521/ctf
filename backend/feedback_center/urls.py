from django.urls import path

from . import views


urlpatterns = [
    path('status/', views.FeedbackStatusView.as_view(), name='feedback-status'),
    path('options/', views.FeedbackOptionsView.as_view(), name='feedback-options'),

    path('', views.FeedbackCreateView.as_view(), name='feedback-create'),
    path('me/', views.MyFeedbackListView.as_view(), name='feedback-my-list'),
    path('<uuid:feedback_id>/', views.FeedbackDetailView.as_view(), name='feedback-detail'),
    path('<uuid:feedback_id>/evidence/', views.FeedbackEvidenceAddView.as_view(), name='feedback-add-evidence'),
    path('<uuid:feedback_id>/attachments/', views.FeedbackAttachmentUploadView.as_view(), name='feedback-upload-attachment'),
    path(
        '<uuid:feedback_id>/attachments/<uuid:attachment_id>/download/',
        views.FeedbackAttachmentDownloadView.as_view(),
        name='feedback-download-attachment',
    ),

    path('teacher/queue/', views.TeacherFeedbackQueueView.as_view(), name='feedback-teacher-queue'),
    path('teacher/sampling-batches/', views.SamplingBatchListCreateView.as_view(), name='feedback-sampling-batches'),
    path(
        'teacher/sampling-batches/<uuid:batch_id>/',
        views.SamplingBatchDetailView.as_view(),
        name='feedback-sampling-batch-detail',
    ),
    path('teacher/reconciliation/', views.FeedbackReconciliationView.as_view(), name='feedback-reconciliation'),
    path(
        'teacher/reconciliation/retry/',
        views.FeedbackReconciliationRetryView.as_view(),
        name='feedback-reconciliation-retry',
    ),
    path('teacher/phase3/contracts/', views.Phase3ContractView.as_view(), name='feedback-phase3-contracts'),
    path('teacher/phase3/candidates/', views.Phase3CandidateStubView.as_view(), name='feedback-phase3-candidates'),
    path('teacher/<uuid:feedback_id>/', views.TeacherFeedbackDetailView.as_view(), name='feedback-teacher-detail'),
    path(
        'teacher/<uuid:feedback_id>/actions/',
        views.TeacherFeedbackActionView.as_view(),
        name='feedback-teacher-action',
    ),
]
