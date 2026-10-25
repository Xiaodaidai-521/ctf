"""HTTP API for module 6.

Students only reach their own attempts, submissions, review cards and retests.
Teachers reach the manual queue, sampling, disputes, corrections and stats.
Every write checks the role and ownership on the server.
"""

from datetime import timedelta

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import status
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from learning_map.models import Capability, CatalogVersion, TaskAttempt, TaskPackage

from . import constants, presenters, serializers
from .models import (
    AssistanceRecord,
    ManualReviewTask,
    RetestAssignment,
    ReviewCard,
    ScoreDispute,
    SubmissionErrorCause,
    SubmissionSnapshot,
    TeacherSamplingBatch,
    TeacherSamplingItem,
    VerificationResult,
)
from .services import correction as correction_service
from .services import disputes, handoff, regression, review, retest, sampling, stats
from .services import submissions as submission_service
from .services import verification


class Module6StatusView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({
            'module': 'skill_review',
            'execution_open': False,
            'ai_required_for_core': False,
            'module7_connected': False,
            'module8_connected': False,
            'rubric_version': constants.RUBRIC_VERSION,
        })


def _is_teacher(user):
    return bool(
        getattr(user, 'is_authenticated', False)
        and (getattr(user, 'is_teacher', False) or getattr(user, 'is_admin', False) or user.is_superuser)
    )


def _require_teacher(user):
    if not _is_teacher(user):
        raise PermissionDenied('需要教师或管理员权限。')


def _attempt_for(user, attempt_id):
    attempt = get_object_or_404(TaskAttempt, attempt_id=attempt_id)
    if attempt.student_id != user.id:
        raise PermissionDenied('该尝试不属于当前用户。')
    return attempt


def _submission_for(user, submission_id, *, teacher=False):
    submission = get_object_or_404(SubmissionSnapshot, submission_id=submission_id)
    if submission.student_id != user.id:
        if not (teacher and _is_teacher(user)):
            raise PermissionDenied('该提交不属于当前用户。')
    return submission


def _task_by_key(catalog, task_key, task_version=''):
    queryset = TaskPackage.objects.filter(catalog=catalog, task_key=task_key)
    if task_version:
        queryset = queryset.filter(version=task_version)
    return queryset.order_by('-version').first()


class MyAttemptsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        attempts = (
            TaskAttempt.objects.filter(student=request.user)
            .select_related('task', 'catalog')
            .order_by('-claimed_at')[:100]
        )
        items = []
        for attempt in attempts:
            submission = (
                SubmissionSnapshot.objects.filter(attempt=attempt)
                .order_by('-created_at').first()
            )
            result = submission.results.filter(is_current=True).first() if submission else None
            items.append({
                'attempt_id': str(attempt.attempt_id),
                'task': {
                    'id': attempt.task.id,
                    'title': attempt.task.title,
                    'version_label': presenters._version_label(attempt.task_version),
                },
                'status': attempt.status,
                'claimed_at': attempt.claimed_at.isoformat(),
                'submission': (
                    presenters.submission_payload(submission, result, teacher=False)
                    if submission else None
                ),
            })
        return Response({'items': items})


class MySubmissionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = (
            SubmissionSnapshot.objects.filter(student=request.user)
            .select_related('task', 'student', 'attempt', 'catalog')
            .order_by('-created_at')
        )
        task_key = request.query_params.get('task_key')
        if task_key:
            queryset = queryset.filter(task__task_key=task_key)
        items = [
            presenters.submission_payload(
                submission, submission.results.filter(is_current=True).first(), teacher=False,
            )
            for submission in queryset[:100]
        ]
        return Response({'items': items})


class SubmissionDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, submission_id):
        teacher = _is_teacher(request.user) and request.query_params.get('view') == 'teacher'
        submission = _submission_for(request.user, submission_id, teacher=teacher)
        result = submission.results.filter(is_current=True).first()
        payload = presenters.timeline_payload(submission, teacher=teacher)
        payload['retest'] = None
        assignment = RetestAssignment.objects.filter(original_submission=submission).first()
        if assignment:
            payload['retest'] = presenters.retest_payload(assignment, teacher=teacher)
        retest_run = RetestAssignment.objects.filter(
            completed_submission=submission,
        ).select_related('original_submission__task').first()
        if retest_run:
            payload['retest_origin'] = {
                'original_task_title': retest_run.original_submission.task.title,
                'original_attempt_id': str(retest_run.original_attempt.attempt_id),
            }
        return Response(payload)


class SubmitAttemptView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, attempt_id):
        attempt = _attempt_for(request.user, attempt_id)
        serializer = serializers.SubmissionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            submission, created = submission_service.create_submission(
                student=request.user,
                attempt=attempt,
                client_submission_id=serializer.validated_data['client_submission_id'],
                payload=serializer.validated_data['payload'],
                assistance_tracking=serializer.validated_data['assistance_tracking'],
            )
        except submission_service.SubmissionConflict as exc:
            raise APIException({'code': exc.code, 'detail': str(exc)}, code='submission_conflict')
        except (submission_service.SubmissionError, ValueError) as exc:
            raise ValidationError({'detail': str(exc)})
        result = submission.results.filter(is_current=True).first()
        payload = presenters.submission_payload(submission, result, teacher=False)
        payload['created'] = created
        return Response(payload, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class HintRequestView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, attempt_id):
        attempt = _attempt_for(request.user, attempt_id)
        serializer = serializers.HintRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            record = submission_service.request_hint(
                student=request.user,
                attempt=attempt,
                level=data['level'],
                source=data['source'],
                content_ref=data.get('content_ref', ''),
            )
        except (ValueError, PermissionError) as exc:
            raise ValidationError({'detail': str(exc)})
        return Response({
            'record_id': str(record.record_id),
            'level': record.level,
            'level_label': constants.HINT_LEVEL_LABELS.get(record.level, ''),
            'source': record.source,
            'shown': record.shown,
            'note': '请求已记录；只有实际展示后才计为帮助。',
        }, status=status.HTTP_201_CREATED)


class HintShowView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, record_id):
        record = get_object_or_404(AssistanceRecord, record_id=record_id)
        if record.student_id != request.user.id and not _is_teacher(request.user):
            raise PermissionDenied('无权展示该提示。')
        record, created = submission_service.show_hint(record=record, actor=request.user)
        return Response({
            'record_id': str(record.record_id),
            'shown': record.shown,
            'shown_at': record.shown_at.isoformat() if record.shown_at else None,
            'created': created,
        })


class StudentCauseView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, submission_id):
        submission = _submission_for(request.user, submission_id)
        serializer = serializers.ErrorCauseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            record = review.upsert_error_cause(
                submission=submission,
                cause=data['cause'],
                status=data['status'],
                source=constants.CAUSE_SOURCE_STUDENT,
                actor=request.user,
                note=data.get('note', ''),
            )
        except review.ReviewError as exc:
            raise ValidationError({'detail': str(exc)})
        return Response({'cause': record.cause, 'status': record.status}, status=status.HTTP_201_CREATED)


class ReviewCardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, submission_id):
        submission = _submission_for(request.user, submission_id)
        card = ReviewCard.objects.filter(submission=submission).first()
        return Response({'review_card': presenters.review_card_payload(card)})

    def put(self, request, submission_id):
        submission = _submission_for(request.user, submission_id)
        serializer = serializers.ReviewCardSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        complete = data.pop('complete', False)
        try:
            card, assignment = review.upsert_review_card(
                student=request.user,
                submission=submission,
                data=data,
                complete=complete,
            )
        except (review.ReviewError, PermissionError) as exc:
            raise ValidationError({'detail': str(exc)})
        return Response({
            'review_card': presenters.review_card_payload(card),
            'retest': presenters.retest_payload(assignment) if assignment else None,
        })


class AnalysisViewRecordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, task_id):
        task = get_object_or_404(TaskPackage, pk=task_id)
        serializer = serializers.AnalysisViewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        attempt = (
            TaskAttempt.objects.filter(student=request.user, task=task)
            .order_by('-claimed_at').first()
        )
        if attempt is None and not _is_teacher(request.user):
            raise PermissionDenied('尚未领取该任务。')
        record = submission_service.record_analysis_view(
            student=request.user,
            task=task,
            attempt=attempt,
            content_ref=serializer.validated_data.get('content_ref', ''),
        )
        return Response({
            'recorded': True,
            'note': '查看解析只记录为复盘与暴露，不修改原尝试结果；之后同题重做不再计为首次独立完成。',
            'record_id': str(record.record_id),
        }, status=status.HTTP_201_CREATED)


class MyRetestsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        assignments = (
            RetestAssignment.objects.filter(student=request.user)
            .select_related('selected_task', 'original_submission__task')
            .order_by('due_at')
        )
        return Response({'items': [
            presenters.retest_payload(assignment) for assignment in assignments
        ]})


class RetestClaimView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, assignment_id):
        assignment = get_object_or_404(RetestAssignment, assignment_id=assignment_id)
        try:
            attempt, created = retest.claim_retest(assignment, request.user)
        except PermissionError as exc:
            raise PermissionDenied(str(exc))
        except ValueError as exc:
            raise ValidationError({'detail': str(exc)})
        return Response({
            'attempt_id': str(attempt.attempt_id),
            'task': {
                'id': attempt.task.id,
                'title': attempt.task.title,
                'version_label': presenters._version_label(attempt.task_version),
            },
            'created': created,
            'note': '复测默认无提示完成；实际使用帮助会记为受助。',
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class DisputeCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, submission_id):
        submission = _submission_for(request.user, submission_id)
        serializer = serializers.DisputeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            dispute, created = disputes.create_dispute(
                student=request.user,
                submission=submission,
                client_dispute_id=serializer.validated_data['client_dispute_id'],
                reason=serializer.validated_data['reason'],
            )
        except disputes.DisputeError as exc:
            raise ValidationError({'detail': str(exc)})
        return Response({
            'dispute_id': str(dispute.dispute_id),
            'status': dispute.status,
            'status_label': dict(constants.DISPUTE_STATUS_CHOICES).get(dispute.status, dispute.status),
            'created': created,
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class MyDisputesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        items = ScoreDispute.objects.filter(student=request.user).select_related(
            'submission__task',
        ).order_by('-created_at')[:100]
        return Response({'items': [
            {
                'dispute_id': str(item.dispute_id),
                'task_title': item.submission.task.title,
                'reason': item.reason,
                'status': item.status,
                'status_label': dict(constants.DISPUTE_STATUS_CHOICES).get(item.status, item.status),
                'resolution': item.resolution,
                'created_at': item.created_at.isoformat(),
                'resolved_at': item.resolved_at.isoformat() if item.resolved_at else None,
            }
            for item in items
        ]})


# ---------------------------------------------------------------- teacher side


class TeacherQueueView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        _require_teacher(request.user)
        now = timezone.now()
        manual = ManualReviewTask.objects.filter(
            status__in=(constants.MANUAL_TASK_PENDING, constants.MANUAL_TASK_CLAIMED),
        ).select_related('submission__task', 'student').order_by('created_at')
        sampling_items = TeacherSamplingItem.objects.filter(
            status__in=(constants.SAMPLING_ITEM_PENDING, constants.SAMPLING_ITEM_CLAIMED),
        ).select_related('batch', 'submission__task', 'submission__student').order_by('created_at')
        disputes_qs = ScoreDispute.objects.filter(
            status__in=(constants.DISPUTE_SUBMITTED, constants.DISPUTE_UNDER_REVIEW),
        ).select_related('submission__task', 'student').order_by('created_at')
        overdue = [item for item in sampling_items if sampling.item_is_overdue(item, now)]
        return Response({
            'counts': {
                'manual_pending': manual.count(),
                'sampling_pending': len(sampling_items),
                'sampling_overdue': len(overdue),
                'disputes_pending': disputes_qs.count(),
            },
            'manual_tasks': [
                {
                    'task_id': str(task.review_id),
                    'student': task.student.username,
                    'task_title': task.submission.task.title,
                    'status': task.status,
                    'created_at': task.created_at.isoformat(),
                }
                for task in manual[:50]
            ],
            'sampling_items': [
                {
                    'item_id': str(item.item_id),
                    'batch_title': item.batch.title,
                    'student': item.submission.student.username,
                    'task_title': item.submission.task.title,
                    'selection_reason': item.selection_reason,
                    'risk_reasons': item.risk_reasons,
                    'status': item.status,
                    'overdue': sampling.item_is_overdue(item, now),
                }
                for item in sampling_items[:50]
            ],
            'disputes': [
                {
                    'dispute_id': str(dispute.dispute_id),
                    'student': dispute.student.username,
                    'task_title': dispute.submission.task.title,
                    'status': dispute.status,
                    'created_at': dispute.created_at.isoformat(),
                }
                for dispute in disputes_qs[:50]
            ],
            'note': '开放题必评、常规抽查与评分争议分别排队，互不替代。',
        })


class TeacherManualTaskListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        _require_teacher(request.user)
        queryset = ManualReviewTask.objects.select_related(
            'submission__task', 'student', 'result', 'submission__attempt',
        ).order_by('created_at')
        status_filter = request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        task_key = request.query_params.get('task_key')
        if task_key:
            queryset = queryset.filter(submission__task__task_key=task_key)
        student_id = request.query_params.get('student')
        if student_id:
            queryset = queryset.filter(student_id=student_id)
        return Response({
            'items': [presenters.manual_task_payload(task) for task in queryset[:100]],
            'counts': {
                'pending': ManualReviewTask.objects.filter(status=constants.MANUAL_TASK_PENDING).count(),
                'claimed': ManualReviewTask.objects.filter(status=constants.MANUAL_TASK_CLAIMED).count(),
                'reviewed': ManualReviewTask.objects.filter(status=constants.MANUAL_TASK_REVIEWED).count(),
            },
        })


class TeacherManualClaimView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, task_id):
        _require_teacher(request.user)
        task = get_object_or_404(ManualReviewTask, review_id=task_id)
        if task.status == constants.MANUAL_TASK_CLAIMED and task.claimed_by_id != request.user.id:
            raise ValidationError({'detail': '该待办已被其他教师认领。'})
        if task.status not in (constants.MANUAL_TASK_PENDING, constants.MANUAL_TASK_CLAIMED):
            raise ValidationError({'detail': '该待办当前不可认领。'})
        task.status = constants.MANUAL_TASK_CLAIMED
        task.claimed_by = request.user
        task.claimed_at = timezone.now()
        task.save(update_fields=['status', 'claimed_by', 'claimed_at', 'updated_at'])
        return Response({'task_id': str(task.review_id), 'status': task.status})


class TeacherManualReviewView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, task_id):
        _require_teacher(request.user)
        task = get_object_or_404(ManualReviewTask, review_id=task_id)
        serializer = serializers.ManualReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            task = verification.review_manual_task(
                task,
                reviewer=request.user,
                scores=data['scores'],
                decision=data['decision'],
                remarks=data['remarks'],
                causes=data.get('causes') or [],
                admin_override=getattr(request.user, 'is_admin', False) or request.user.is_superuser,
            )
        except PermissionError as exc:
            raise PermissionDenied(str(exc))
        except ValueError as exc:
            raise ValidationError({'detail': str(exc)})
        return Response(presenters.manual_task_payload(task))


class TeacherTeacherHelpView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, attempt_id):
        _require_teacher(request.user)
        attempt = get_object_or_404(TaskAttempt, attempt_id=attempt_id)
        serializer = serializers.TeacherHelpSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        record = submission_service.record_teacher_help(
            teacher=request.user,
            attempt=attempt,
            summary=serializer.validated_data['summary'],
        )
        return Response({
            'record_id': str(record.record_id),
            'note': '教师帮助已记录；该尝试的最终提交将计为受助。',
        }, status=status.HTTP_201_CREATED)


class TeacherAttemptTimelineView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, attempt_id):
        _require_teacher(request.user)
        attempt = get_object_or_404(TaskAttempt, attempt_id=attempt_id)
        submission = SubmissionSnapshot.objects.filter(attempt=attempt).order_by('-created_at').first()
        if submission is None:
            return Response({'attempt_id': str(attempt.attempt_id), 'submission': None, 'note': '尚未提交。'})
        return Response(presenters.timeline_payload(submission, teacher=True))


class TeacherCorrectionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, submission_id):
        _require_teacher(request.user)
        submission = get_object_or_404(SubmissionSnapshot, submission_id=submission_id)
        serializer = serializers.CorrectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        sampling_item = None
        if data.get('sampling_item_id'):
            sampling_item = get_object_or_404(TeacherSamplingItem, item_id=data['sampling_item_id'])
        try:
            with transaction.atomic():
                correction = correction_service.create_correction(
                    submission=submission,
                    actor=request.user,
                    source=data['source'],
                    reason=data['reason'],
                    changes=data['changes'],
                    sampling_item=sampling_item,
                )
        except correction_service.CorrectionError as exc:
            raise ValidationError({'detail': str(exc)})
        return Response({
            'correction_id': str(correction.correction_id),
            'original_result_id': str(correction.original_result.result_id),
            'corrected_result_id': str(correction.corrected_result.result_id),
            'before': correction.before,
            'after': correction.after,
            'note': '原判定已保留；模块一事实已重新回传，模块七、八为未接通状态。',
        }, status=status.HTTP_201_CREATED)


class TeacherCardConfirmView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, card_id):
        _require_teacher(request.user)
        card = get_object_or_404(ReviewCard, card_id=card_id)
        serializer = serializers.CardConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        card = review.confirm_review_card(
            card=card, teacher=request.user,
            confirmation=serializer.validated_data['confirmation'],
        )
        return Response(presenters.review_card_payload(card, teacher=True))


class TeacherRetestListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        _require_teacher(request.user)
        queryset = RetestAssignment.objects.select_related(
            'selected_task', 'student', 'original_submission__task', 'started_attempt',
        ).order_by('due_at')
        status_filter = request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return Response({'items': [
            presenters.retest_payload(assignment, teacher=True) for assignment in queryset[:200]
        ]})


class TeacherRetestAdjustView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, assignment_id):
        _require_teacher(request.user)
        assignment = get_object_or_404(RetestAssignment, assignment_id=assignment_id)
        serializer = serializers.RetestScheduleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if 'due_days' not in data:
            raise ValidationError({'detail': '必须提供 due_days。'})
        if not data.get('reason'):
            raise ValidationError({'detail': '改期必须记录原因。'})
        base = assignment.scheduled_at or timezone.now()
        due_at = base + timedelta(days=data['due_days'])
        assignment.due_at = due_at
        assignment.grace_until = due_at + timedelta(days=7)
        assignment.adjustment_note = data['reason']
        assignment.save(update_fields=['due_at', 'grace_until', 'adjustment_note', 'updated_at'])
        return Response(presenters.retest_payload(assignment, teacher=True))


class ProcessDueRetestsView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        _require_teacher(request.user)
        serializer = serializers.ProcessDueSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        now = serializer.validated_data.get('now') or timezone.now()
        result = retest.process_due_retests(now=now)
        return Response({
            **result,
            'evaluated_at': now.isoformat(),
            'note': '仅推进日期状态；未参加不等于知识错误，也不代表学习保持效果。',
        })


class TeacherSamplingBatchView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        _require_teacher(request.user)
        batches = TeacherSamplingBatch.objects.select_related('task', 'capability', 'created_by').order_by('-created_at')[:50]
        return Response({'items': [
            {
                'batch_id': str(batch.batch_id),
                'title': batch.title,
                'catalog_version': batch.catalog.version,
                'scope': batch.scope,
                'sample_size': batch.sample_size,
                'high_risk_size': batch.high_risk_size,
                'random_seed': batch.random_seed,
                'basis': batch.basis,
                'deadline': batch.deadline.isoformat(),
                'status': batch.status,
                'created_at': batch.created_at.isoformat(),
                'item_counts': {
                    status_value: batch.items.filter(status=status_value).count()
                    for status_value, _label in constants.SAMPLING_ITEM_STATUS_CHOICES
                },
            }
            for batch in batches
        ]})

    def post(self, request):
        _require_teacher(request.user)
        serializer = serializers.SamplingBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        catalog = get_object_or_404(CatalogVersion, version=data['catalog_version'])
        task = None
        if data.get('task_key'):
            task = _task_by_key(catalog, data['task_key'], data.get('task_version', ''))
            if task is None:
                raise ValidationError({'detail': '任务不在该目录版本中。'})
        capability = None
        if data.get('capability_id'):
            capability = get_object_or_404(Capability, catalog=catalog, stable_id=data['capability_id'])
        try:
            batch = sampling.create_batch(
                actor=request.user,
                catalog=catalog,
                title=data['title'],
                window_start=data['window_start'],
                window_end=data['window_end'],
                basis=data['basis'],
                deadline=data['deadline'],
                sample_size=data['sample_size'],
                high_risk_size=data['high_risk_size'],
                random_seed=data['random_seed'],
                task=task,
                capability=capability,
            )
        except sampling.SamplingError as exc:
            raise ValidationError({'detail': str(exc)})
        return Response({
            'batch_id': str(batch.batch_id),
            'scope': batch.scope,
            'items': batch.items.count(),
        }, status=status.HTTP_201_CREATED)


class TeacherSamplingItemListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        _require_teacher(request.user)
        queryset = TeacherSamplingItem.objects.select_related(
            'batch', 'submission__task', 'submission__student', 'result', 'correction',
        ).order_by('created_at')
        batch_id = request.query_params.get('batch')
        if batch_id:
            queryset = queryset.filter(batch__batch_id=batch_id)
        status_filter = request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        selection = request.query_params.get('selection')
        if selection:
            queryset = queryset.filter(selection_reason=selection)
        now = timezone.now()
        return Response({'items': [
            {
                'item_id': str(item.item_id),
                'batch_id': str(item.batch.batch_id),
                'batch_title': item.batch.title,
                'student': item.submission.student.username,
                'task_title': item.submission.task.title,
                'selection_reason': item.selection_reason,
                'risk_reasons': item.risk_reasons,
                'status': item.status,
                'overdue': sampling.item_is_overdue(item, now),
                'claimed_by': item.claimed_by_id,
                'result': presenters.submission_payload(
                    item.submission, item.result, teacher=True,
                ) if item.result else None,
                'findings': item.findings,
                'notes': item.notes,
                'correction_id': str(item.correction.correction_id) if item.correction else None,
            }
            for item in queryset[:200]
        ]})


class TeacherSamplingClaimView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, item_id):
        _require_teacher(request.user)
        item = get_object_or_404(TeacherSamplingItem, item_id=item_id)
        try:
            item, created = sampling.claim_item(item, request.user)
        except sampling.SamplingError as exc:
            raise ValidationError({'detail': str(exc)})
        return Response({'item_id': str(item.item_id), 'status': item.status, 'created': created})


class TeacherSamplingReviewView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, item_id):
        _require_teacher(request.user)
        item = get_object_or_404(TeacherSamplingItem, item_id=item_id)
        serializer = serializers.SamplingReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        correction = None
        try:
            with transaction.atomic():
                if data.get('correction'):
                    payload = data['correction']
                    correction = correction_service.create_correction(
                        submission=item.submission,
                        actor=request.user,
                        source=constants.CORRECTION_SOURCE_SAMPLING,
                        reason=payload.get('reason', ''),
                        changes=payload.get('changes') or {},
                        sampling_item=item,
                    )
                item = sampling.review_item(
                    item,
                    teacher=request.user,
                    findings=data['findings'],
                    notes=data.get('notes', ''),
                    needs_correction=bool(data.get('needs_correction') or correction),
                    correction=correction,
                )
        except correction_service.CorrectionError as exc:
            raise ValidationError({'detail': str(exc)})
        except sampling.SamplingError as exc:
            raise ValidationError({'detail': str(exc)})
        return Response({
            'item_id': str(item.item_id),
            'status': item.status,
            'correction_id': str(correction.correction_id) if correction else None,
        })


class TeacherDisputeListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        _require_teacher(request.user)
        queryset = ScoreDispute.objects.select_related(
            'submission__task', 'student', 'result',
        ).order_by('-created_at')
        status_filter = request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return Response({'items': [
            {
                'dispute_id': str(dispute.dispute_id),
                'student': dispute.student.username,
                'task_title': dispute.submission.task.title,
                'reason': dispute.reason,
                'status': dispute.status,
                'status_label': dict(constants.DISPUTE_STATUS_CHOICES).get(dispute.status, dispute.status),
                'result_id': str(dispute.result.result_id) if dispute.result else None,
                'resolution': dispute.resolution,
                'created_at': dispute.created_at.isoformat(),
            }
            for dispute in queryset[:100]
        ]})


class TeacherDisputeResolveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, dispute_id):
        _require_teacher(request.user)
        dispute = get_object_or_404(ScoreDispute, dispute_id=dispute_id)
        serializer = serializers.DisputeResolveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            dispute = disputes.resolve_dispute(
                dispute,
                teacher=request.user,
                status=data['status'],
                resolution=data['resolution'],
            )
        except disputes.DisputeError as exc:
            raise ValidationError({'detail': str(exc)})
        return Response({
            'dispute_id': str(dispute.dispute_id),
            'status': dispute.status,
            'note': '处理争议不直接改分；需要改分请走更正版本。',
        })


class TeacherStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        _require_teacher(request.user)
        catalog = CatalogVersion.objects.filter(version=request.query_params.get('version')).first()
        if catalog is None:
            catalog = CatalogVersion.objects.filter(status='published').order_by('-published_at').first()
        if catalog is None:
            catalog = CatalogVersion.objects.order_by('-created_at').first()
        if catalog is None:
            raise ValidationError({'detail': '没有可用目录版本。'})
        start = parse_datetime(request.query_params.get('start') or '')
        end = parse_datetime(request.query_params.get('end') or '')
        return Response(stats.build_stats(catalog=catalog, start=start, end=end))


class RegressionCasesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        _require_teacher(request.user)
        return Response(regression.regression_cases())


class TeacherNoticeRetryView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, notice_id):
        _require_teacher(request.user)
        from .models import DownstreamNotice

        notice = get_object_or_404(DownstreamNotice, pk=notice_id)
        notice = handoff.retry_module1_notice(notice)
        return Response({
            'notice_id': notice.id,
            'target': notice.target,
            'status': notice.status,
            'attempts': notice.attempts,
            'last_error': notice.last_error,
        })
