from django.urls import path

from . import views


urlpatterns = [
    path('status/', views.Module6StatusView.as_view(), name='skill-review-status'),

    # Student
    path('me/attempts/', views.MyAttemptsView.as_view(), name='skill-review-my-attempts'),
    path('me/submissions/', views.MySubmissionsView.as_view(), name='skill-review-my-submissions'),
    path('submissions/<uuid:submission_id>/', views.SubmissionDetailView.as_view(), name='skill-review-submission'),
    path('attempts/<uuid:attempt_id>/submit/', views.SubmitAttemptView.as_view(), name='skill-review-submit'),
    path('attempts/<uuid:attempt_id>/hints/', views.HintRequestView.as_view(), name='skill-review-request-hint'),
    path('hints/<uuid:record_id>/show/', views.HintShowView.as_view(), name='skill-review-show-hint'),
    path('submissions/<uuid:submission_id>/causes/', views.StudentCauseView.as_view(), name='skill-review-student-cause'),
    path('submissions/<uuid:submission_id>/review-card/', views.ReviewCardView.as_view(), name='skill-review-card'),
    path('tasks/<int:task_id>/analysis-view/', views.AnalysisViewRecordView.as_view(), name='skill-review-analysis-view'),
    path('me/retests/', views.MyRetestsView.as_view(), name='skill-review-my-retests'),
    path('retests/<uuid:assignment_id>/claim/', views.RetestClaimView.as_view(), name='skill-review-retest-claim'),
    path('submissions/<uuid:submission_id>/disputes/', views.DisputeCreateView.as_view(), name='skill-review-dispute-create'),
    path('me/disputes/', views.MyDisputesView.as_view(), name='skill-review-my-disputes'),

    # Teacher
    path('teacher/queue/', views.TeacherQueueView.as_view(), name='skill-review-teacher-queue'),
    path('teacher/manual-tasks/', views.TeacherManualTaskListView.as_view(), name='skill-review-manual-list'),
    path('teacher/manual-tasks/<uuid:task_id>/claim/', views.TeacherManualClaimView.as_view(), name='skill-review-manual-claim'),
    path('teacher/manual-tasks/<uuid:task_id>/review/', views.TeacherManualReviewView.as_view(), name='skill-review-manual-review'),
    path('teacher/attempts/<uuid:attempt_id>/help/', views.TeacherTeacherHelpView.as_view(), name='skill-review-teacher-help'),
    path('teacher/attempts/<uuid:attempt_id>/timeline/', views.TeacherAttemptTimelineView.as_view(), name='skill-review-timeline'),
    path('teacher/submissions/<uuid:submission_id>/corrections/', views.TeacherCorrectionView.as_view(), name='skill-review-correction'),
    path('teacher/cards/<uuid:card_id>/confirm/', views.TeacherCardConfirmView.as_view(), name='skill-review-card-confirm'),
    path('teacher/retests/', views.TeacherRetestListView.as_view(), name='skill-review-teacher-retests'),
    path('teacher/retests/<uuid:assignment_id>/adjust/', views.TeacherRetestAdjustView.as_view(), name='skill-review-retest-adjust'),
    path('teacher/retests/process-due/', views.ProcessDueRetestsView.as_view(), name='skill-review-process-due'),
    path('teacher/sampling/batches/', views.TeacherSamplingBatchView.as_view(), name='skill-review-sampling-batches'),
    path('teacher/sampling/items/', views.TeacherSamplingItemListView.as_view(), name='skill-review-sampling-items'),
    path('teacher/sampling/items/<uuid:item_id>/claim/', views.TeacherSamplingClaimView.as_view(), name='skill-review-sampling-claim'),
    path('teacher/sampling/items/<uuid:item_id>/review/', views.TeacherSamplingReviewView.as_view(), name='skill-review-sampling-review'),
    path('teacher/disputes/', views.TeacherDisputeListView.as_view(), name='skill-review-teacher-disputes'),
    path('teacher/disputes/<uuid:dispute_id>/resolve/', views.TeacherDisputeResolveView.as_view(), name='skill-review-dispute-resolve'),
    path('teacher/stats/', views.TeacherStatsView.as_view(), name='skill-review-stats'),
    path('teacher/regression-cases/', views.RegressionCasesView.as_view(), name='skill-review-regression'),
    path('teacher/notices/<int:notice_id>/retry/', views.TeacherNoticeRetryView.as_view(), name='skill-review-notice-retry'),
]
