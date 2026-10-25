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
    path('teacher/phase3/issue-groups/', views.IssueGroupListCreateView.as_view(), name='feedback-issue-groups'),
    path('teacher/phase3/issue-groups/merge/', views.IssueGroupMergeView.as_view(), name='feedback-issue-group-merge'),
    path('teacher/phase3/issue-groups/<uuid:group_id>/', views.IssueGroupDetailView.as_view(), name='feedback-issue-group'),
    path('teacher/phase3/issue-groups/<uuid:group_id>/members/', views.IssueGroupMemberView.as_view(), name='feedback-issue-group-member'),
    path('teacher/phase3/issue-groups/<uuid:group_id>/confirm/', views.IssueGroupConfirmView.as_view(), name='feedback-issue-group-confirm'),
    path('teacher/phase3/issue-groups/<uuid:group_id>/reject/', views.IssueGroupRejectView.as_view(), name='feedback-issue-group-reject'),
    path('teacher/phase3/issue-groups/<uuid:group_id>/split/', views.IssueGroupSplitView.as_view(), name='feedback-issue-group-split'),
    path('teacher/phase3/candidates/', views.CandidateListCreateView.as_view(), name='feedback-phase3-candidates'),
    path('teacher/phase3/candidates/<uuid:candidate_id>/', views.CandidateDetailView.as_view(), name='feedback-phase3-candidate'),
    path('teacher/phase3/candidates/<uuid:candidate_id>/submit/', views.CandidateSubmitView.as_view(), name='feedback-candidate-submit'),
    path('teacher/phase3/candidates/<uuid:candidate_id>/report/', views.CandidateReportView.as_view(), name='feedback-candidate-report'),
    path('teacher/phase3/candidates/<uuid:candidate_id>/complete-evaluation/', views.CandidateCompleteEvaluationView.as_view(), name='feedback-candidate-complete-evaluation'),
    path('teacher/phase3/candidates/<uuid:candidate_id>/approve/', views.CandidateApproveView.as_view(), name='feedback-candidate-approve'),
    path('teacher/phase3/candidates/<uuid:candidate_id>/activate/', views.CandidateActivateView.as_view(), name='feedback-candidate-activate'),
    path('teacher/phase3/candidates/<uuid:candidate_id>/observe/', views.CandidateObserveView.as_view(), name='feedback-candidate-observe'),
    path('teacher/phase3/candidates/<uuid:candidate_id>/stable/', views.CandidateStableView.as_view(), name='feedback-candidate-stable'),
    path('teacher/phase3/candidates/<uuid:candidate_id>/rollback/', views.CandidateRollbackView.as_view(), name='feedback-candidate-rollback'),
    path('teacher/<uuid:feedback_id>/dispute-link/', views.FeedbackDisputeLinkView.as_view(), name='feedback-dispute-link'),
    path('teacher/<uuid:feedback_id>/', views.TeacherFeedbackDetailView.as_view(), name='feedback-teacher-detail'),
    path(
        'teacher/<uuid:feedback_id>/actions/',
        views.TeacherFeedbackActionView.as_view(),
        name='feedback-teacher-action',
    ),
]
