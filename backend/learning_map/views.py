"""HTTP API for module 1.

Every write checks the role on the server.  Students only read/write their own
records; teachers may inspect a student's map and record adjustments; only an
admin may freeze or publish a catalog, and publishing is blocked until every
required delivery item is signed off with real reviewer metadata.
"""

import hmac

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import constants
from .models import (
    Capability,
    CatalogVersion,
    DeliveryRegisterItem,
    DiagnosticSession,
    PathChangeLog,
    TaskAttempt,
    TaskPackage,
    TeacherAdjustment,
    VerificationFact,
)
from .serializers import (
    AttemptSubmitSerializer,
    DeliveryRegisterUpdateSerializer,
    DiagnosticSubmitSerializer,
    TeacherAdjustmentSerializer,
    VerificationFactSerializer,
)
from .services import catalog as catalog_service
from .services.diagnosis import DiagnosisError, serialize_questions, submit_diagnosis
from .services.events import emit_event
from .services.handoff import FactConflict, FactError, build_ack, ingest_verification_fact
from .services.interop import export_case_package, export_xapi_statements
from .services.map import build_capability_map
from .services.pathing import state_for_student
from .services.recommendation import (
    RecommendationError,
    compute_recommendation,
    student_recommendation_view,
)


User = get_user_model()


class CatalogNotPublishedAPI(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = 'catalog_not_published'


class PublishBlockedAPI(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = 'publish_blocked'


class FactConflictAPI(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = 'fact_id_conflict'


class DomainErrorAPI(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = 'invalid_request'


def _is_teacher(user):
    return bool(
        getattr(user, 'is_authenticated', False)
        and (getattr(user, 'is_teacher', False) or getattr(user, 'is_admin', False) or user.is_superuser)
    )


def _is_admin(user):
    return bool(
        getattr(user, 'is_authenticated', False)
        and (getattr(user, 'is_admin', False) or user.is_superuser)
    )


def _require_teacher(user):
    if not _is_teacher(user):
        raise PermissionDenied('需要教师或管理员权限。')


def _is_course_owner(user):
    """Directory review is a course-owner task, not a general teacher right.

    The platform has no separate course-owner role yet, so this is the
    explicit allow-list: admin, superuser, or a teacher account flagged as
    course owner.  Regular students never pass.
    """

    if not getattr(user, 'is_authenticated', False):
        return False
    if _is_admin(user):
        return True
    return bool(getattr(user, 'can_manage_catalog', False))


def _require_admin(user):
    if not _is_admin(user):
        raise PermissionDenied('需要管理员权限。')


def _require_course_owner(user):
    if not _is_course_owner(user):
        raise PermissionDenied('需要课程负责人或管理员权限。')


def _service_authorized(request):
    expected = getattr(settings, 'LEARNING_MAP_SERVICE_TOKEN', '')
    provided = request.headers.get('X-Learning-Map-Service-Token', '')
    if not expected or not provided:
        return False
    return hmac.compare_digest(expected, provided)


def _readable_catalog(user, version=None):
    try:
        return catalog_service.readable_catalog(user, version=version)
    except catalog_service.CatalogUnavailable as exc:
        raise CatalogNotPublishedAPI({'code': exc.code, 'detail': exc.detail})


def _student_for(user, student_id=None):
    if student_id is None or int(student_id) == user.id:
        return user
    _require_teacher(user)
    return get_object_or_404(User, pk=student_id)


def _attempt_payload(attempt):
    return {
        'attempt_id': str(attempt.attempt_id),
        'task': {
            'task_key': attempt.task.task_key,
            'version': attempt.task_version,
            'title': attempt.task.title,
        },
        'capability_ids': attempt.capability_ids,
        'status': attempt.status,
        'status_label': attempt.get_status_display(),
        'claimed_at': attempt.claimed_at.isoformat(),
        'submitted_at': attempt.submitted_at.isoformat() if attempt.submitted_at else None,
        'evidence_ref': attempt.evidence_ref,
    }


def _adjustment_payload(adjustment):
    return {
        'id': adjustment.id,
        'student': adjustment.student_id,
        'teacher': adjustment.teacher_id,
        'capability_id': adjustment.capability.stable_id if adjustment.capability else '',
        'task_key': adjustment.task.task_key if adjustment.task else '',
        'task_version': adjustment.task.version if adjustment.task else '',
        'action': adjustment.action,
        'rationale': adjustment.rationale,
        'status': adjustment.status,
        'created_at': adjustment.created_at.isoformat(),
    }


class ModuleStatusView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        published = catalog_service.latest_published()
        return Response({
            'module': 'learning_map',
            'catalog_published': bool(published),
            'published_catalog_version': published.version if published else None,
            'execution_open': False,
            'ai_required_for_core': False,
        })


class CatalogView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        catalog = _readable_catalog(request.user, request.query_params.get('version'))
        if not _is_teacher(request.user):
            return Response({
                'version': catalog.version,
                'label': catalog.label,
                'status_label': (
                    '已发布' if catalog.status == constants.CATALOG_STATUS_PUBLISHED else '预览（未发布）'
                ),
                'is_published': catalog.status == constants.CATALOG_STATUS_PUBLISHED,
                'updated_at': catalog.updated_at.isoformat() if catalog.updated_at else None,
                'capabilities': [
                    {
                        'title': capability.title,
                        'track_label': constants.TRACK_LABELS[capability.track],
                        'dimension_label': constants.DIMENSION_LABELS[capability.dimension],
                        'availability_label': (
                            '已开放' if capability.status == constants.CAPABILITY_STATUS_OPEN
                            else '暂未开放'
                        ),
                    }
                    for capability in catalog.capabilities.order_by('track', 'course_order', 'stable_id')
                ],
                'counts': {
                    'open_capabilities': catalog.capabilities.filter(
                        status=constants.CAPABILITY_STATUS_OPEN,
                    ).count(),
                    'total_capabilities': catalog.capabilities.count(),
                },
            })

        payload = catalog_service.catalog_version_payload(catalog)
        payload.update({
            'capabilities': [
                {
                    'capability_id': capability.stable_id,
                    'title': capability.title,
                    'track': capability.track,
                    'dimension': capability.dimension,
                    'status': capability.status,
                    'course_order': capability.course_order,
                }
                for capability in catalog.capabilities.order_by('track', 'course_order', 'stable_id')
            ],
            'counts': {
                'capabilities': catalog.capabilities.count(),
                'open_capabilities': catalog.capabilities.filter(status=constants.CAPABILITY_STATUS_OPEN).count(),
                'tasks': catalog.tasks.count(),
                'diagnostic_questions': catalog.diagnostic_questions.count(),
            },
        })
        return Response(payload)


class TeacherCatalogView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        _require_course_owner(request.user)
        catalog = _readable_catalog(request.user, request.query_params.get('version'))
        readiness = catalog_service.publish_readiness(catalog)
        capabilities = []
        for capability in catalog.capabilities.prefetch_related('knowledge_points', 'prerequisites', 'tasks').order_by('track', 'course_order', 'stable_id'):
            capabilities.append({
                'capability_id': capability.stable_id,
                'title': capability.title,
                'observable_objective': capability.observable_objective,
                'track': capability.track,
                'dimension': capability.dimension,
                'difficulty': capability.difficulty,
                'status': capability.status,
                'status_label': capability.get_status_display(),
                'course_order': capability.course_order,
                'knowledge_point_ids': sorted(point.stable_id for point in capability.knowledge_points.all()),
                'prerequisite_ids': sorted(prerequisite.stable_id for prerequisite in capability.prerequisites.all()),
                'source_refs': capability.source_refs,
                'tasks': [
                    {
                        'task_key': task.task_key,
                        'version': task.version,
                        'title': task.title,
                        'purpose': task.purpose,
                        'status': task.status,
                        'recommendable': task.is_recommendable,
                        'has_required_parts': task.has_required_parts,
                        'requires_milestone_i': task.requires_milestone_i,
                    }
                    for task in capability.tasks.filter(catalog=catalog).order_by('course_order', 'task_key')
                ],
            })
        payload = {
            **catalog_service.catalog_version_payload(catalog),
            'readiness': readiness,
            'capabilities': capabilities,
            'wstg_mappings': [
                {
                    'scenario_id': mapping.scenario_id,
                    'scenario_title': mapping.scenario_title,
                    'wstg_version': mapping.wstg_version,
                    'capability_id': mapping.capability.stable_id if mapping.capability else '',
                    'difficulty': mapping.difficulty,
                    'exercise_ref': mapping.exercise_ref,
                    'acceptance_evidence': mapping.acceptance_evidence,
                    'prerequisite_ids': mapping.prerequisite_ids,
                    'status': mapping.status,
                    'translator': mapping.translator_id,
                    'translator_name': mapping.translator.username if mapping.translator else '',
                    'reviewer': mapping.reviewer_id,
                    'reviewer_name': mapping.reviewer.username if mapping.reviewer else '',
                    'reviewed_at': mapping.reviewed_at.isoformat() if mapping.reviewed_at else None,
                    'notes': mapping.notes,
                }
                for mapping in catalog.wstg_mappings.select_related(
                    'capability', 'translator', 'reviewer',
                ).order_by('scenario_id')
            ],
            'basis_cards': [
                {
                    'card_id': card.card_id,
                    'capability_id': card.capability.stable_id if card.capability else '',
                    'source_title': card.source_title,
                    'source_clause': card.source_clause,
                    'source_version': card.source_version,
                    'source_url': card.source_url,
                    'applicable_facts': card.applicable_facts,
                    'classification_conclusion': card.classification_conclusion,
                    'uncertainties': card.uncertainties,
                    'protection_measures': card.protection_measures,
                    'scoring_evidence': card.scoring_evidence,
                    'verified_date': card.verified_date.isoformat() if card.verified_date else None,
                    'owner': card.owner_id,
                    'owner_name': card.owner.username if card.owner else '',
                    'status': card.status,
                }
                for card in catalog.data_basis_cards.select_related(
                    'capability', 'owner',
                ).order_by('card_id')
            ],
            'legacy_mappings': [
                {
                    'source_system': mapping.source_system,
                    'source_label': mapping.source_label,
                    'source_ref': mapping.source_ref,
                    'capability_id': mapping.capability.stable_id if mapping.capability else '',
                    'knowledge_point_id': mapping.knowledge_point.stable_id if mapping.knowledge_point else '',
                    'mapping_status': mapping.mapping_status,
                    'note': mapping.note,
                }
                for mapping in catalog.legacy_mappings.select_related('capability', 'knowledge_point')
            ],
            'delivery_items': [
                {
                    'delivery_no': item.delivery_no,
                    'title': item.title,
                    'status': item.status,
                    'status_label': item.get_status_display(),
                    'version': item.version,
                    'author': item.author_id,
                    'author_name': item.author.username if item.author else '',
                    'reviewer': item.reviewer_id,
                    'reviewer_name': item.reviewer.username if item.reviewer else '',
                    'attachment_path': item.attachment_path,
                    'signed_off_at': item.signed_off_at.isoformat() if item.signed_off_at else None,
                    'open_issues': item.open_issues,
                }
                for item in catalog.delivery_items.select_related(
                    'author', 'reviewer',
                ).order_by('delivery_no')
            ],
        }
        return Response(payload)


class MyMapView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        catalog = _readable_catalog(request.user, request.query_params.get('version'))
        return Response(build_capability_map(
            student=request.user,
            catalog=catalog,
            goal_track=request.query_params.get('goal_track'),
            audience='student',
        ))


class TeacherStudentMapView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, student_id):
        _require_teacher(request.user)
        student = get_object_or_404(User, pk=student_id)
        catalog = _readable_catalog(request.user, request.query_params.get('version'))
        return Response(build_capability_map(
            student=student,
            catalog=catalog,
            goal_track=request.query_params.get('goal_track'),
            audience='teacher',
        ))


class DiagnosticQuestionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        catalog = _readable_catalog(request.user, request.query_params.get('version'))
        track = request.query_params.get('track', constants.TRACK_BOTH)
        tracks = (
            [constants.TRACK_DATA, constants.TRACK_NETWORK]
            if track == constants.TRACK_BOTH else [track]
        )
        if any(item not in (constants.TRACK_DATA, constants.TRACK_NETWORK) for item in tracks):
            raise DomainErrorAPI({'detail': '主线参数不合法。'})
        return Response({
            'catalog_version': catalog.version,
            'track': track,
            'questions': serialize_questions(catalog, tracks),
        })


class DiagnosticSubmitView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = DiagnosticSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        catalog = _readable_catalog(request.user, request.data.get('version'))
        try:
            session = submit_diagnosis(
                student=request.user,
                catalog=catalog,
                goal_track=serializer.validated_data['goal_track'],
                answers=serializer.validated_data['answers'],
                session_id=serializer.validated_data.get('session_id'),
            )
        except DiagnosisError as exc:
            raise DomainErrorAPI({'detail': str(exc)})
        result = session.result
        return Response({
            'catalog_version': catalog.version,
            'result': {
                'question_count': result.get('question_count', 0),
                'answered_count': result.get('answered_count', 0),
                'items': [
                    {
                        'title': catalog.capabilities.get(stable_id=stable_id).title,
                        'result_label': _diagnosis_result_label(entry.get('result')),
                    }
                    for stable_id, entry in sorted(result.get('capabilities', {}).items())
                ],
            },
        }, status=status.HTTP_201_CREATED)


def _diagnosis_result_label(result):
    return {
        constants.DIAGNOSIS_LIKELY_MASTERED: '诊断表现较好，可安排验收任务',
        constants.DIAGNOSIS_NEEDS_LEARNING: '建议先做基础练习',
        constants.DIAGNOSIS_INSUFFICIENT: '证据不足（有题未答）',
        constants.DIAGNOSIS_UNKNOWN: '未诊断',
    }.get(result, '已记录')


def _recommendation_payload(run, audience):
    if audience == 'student':
        return student_recommendation_view(run)
    return {
        'run_id': run.id,
        'generated_at': run.created_at.isoformat(),
        'inputs_hash': run.inputs_hash,
        'ai_used': False,
        **run.output,
    }


class MyRecommendationsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        catalog = _readable_catalog(request.user, request.query_params.get('version'))
        try:
            run = compute_recommendation(
                student=request.user,
                catalog=catalog,
                goal_track=request.query_params.get('goal_track') or constants.TRACK_BOTH,
            )
        except RecommendationError as exc:
            raise DomainErrorAPI({'detail': str(exc)})
        return Response(_recommendation_payload(run, audience='student'))


class TeacherStudentRecommendationsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, student_id):
        _require_teacher(request.user)
        student = get_object_or_404(User, pk=student_id)
        catalog = _readable_catalog(request.user, request.query_params.get('version'))
        try:
            run = compute_recommendation(
                student=student,
                catalog=catalog,
                goal_track=request.query_params.get('goal_track') or constants.TRACK_BOTH,
            )
        except RecommendationError as exc:
            raise DomainErrorAPI({'detail': str(exc)})
        return Response(_recommendation_payload(run, audience='teacher'))


def _states_satisfied(student, catalog):
    return {
        state.capability.stable_id
        for state in state_for_student(student, catalog).values()
        if state.state in constants.PREREQUISITE_SATISFIED_STATES
    }


class ClaimTaskView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, task_id):
        catalog = _readable_catalog(request.user, request.data.get('version'))
        task = get_object_or_404(TaskPackage, pk=task_id, catalog=catalog)
        if task.status != constants.TASK_STATUS_FROZEN:
            raise DomainErrorAPI({'code': 'task_not_open', 'detail': '任务暂未开放，不能领取。'})
        if task.requires_milestone_i:
            raise DomainErrorAPI({'code': 'task_not_open', 'detail': '任务暂未开放。'})
        if not task.environment_available:
            raise DomainErrorAPI({'code': 'environment_unavailable', 'detail': '任务环境当前不可用。'})
        if task.materials_withdrawn:
            raise DomainErrorAPI({'code': 'materials_withdrawn', 'detail': '任务材料已撤回。'})

        satisfied = _states_satisfied(request.user, catalog)
        required_capabilities = {
            capability.stable_id for capability in task.prerequisite_capabilities.all()
        }
        unmet = required_capabilities - satisfied
        if unmet:
            teacher_override = TeacherAdjustment.objects.filter(
                student=request.user,
                catalog=catalog,
                task=task,
                action='assign_task',
                status__in=['recorded', 'applied'],
            ).exists()
            if not teacher_override:
                unmet_titles = [
                    capability.title for capability in task.prerequisite_capabilities.all()
                    if capability.stable_id in unmet
                ]
                raise DomainErrorAPI({
                    'code': 'prerequisite_unmet',
                    'detail': f'先修尚未完成：{"、".join(unmet_titles)}',
                })

        with transaction.atomic():
            existing = TaskAttempt.objects.select_for_update().filter(
                student=request.user,
                task=task,
                status__in=(constants.ATTEMPT_CLAIMED, constants.ATTEMPT_IN_PROGRESS),
            ).order_by('-claimed_at').first()
            if existing:
                return Response({**_attempt_payload(existing), 'created': False})

            attempt = TaskAttempt.objects.create(
                student=request.user,
                catalog=catalog,
                task=task,
                task_version=task.version,
                capability_ids=sorted(capability.stable_id for capability in task.capabilities.all()),
                status=constants.ATTEMPT_CLAIMED,
            )
            emit_event(
                user=request.user,
                event_type='task_claim',
                event_id=f'lm-task-claim-{attempt.attempt_id}',
                catalog=catalog,
                task=task,
                attempt_id=attempt.attempt_id,
                capability_ids=attempt.capability_ids,
                extra={'task_purpose': task.purpose, 'execution_mode': task.execution_mode},
            )
        return Response({**_attempt_payload(attempt), 'created': True}, status=status.HTTP_201_CREATED)


class SubmitAttemptView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, attempt_id):
        attempt = get_object_or_404(TaskAttempt, attempt_id=attempt_id, student=request.user)
        if attempt.status == constants.ATTEMPT_VERIFIED:
            raise DomainErrorAPI({'code': 'attempt_frozen', 'detail': '该尝试已完成核验，不能覆盖。'})
        serializer = AttemptSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if attempt.status == constants.ATTEMPT_PENDING_VERIFICATION:
            return Response({
                **_attempt_payload(attempt),
                'created': False,
                'detail': '提交已保存，等待核验结果。',
            })
        with transaction.atomic():
            attempt.status = constants.ATTEMPT_PENDING_VERIFICATION
            attempt.submitted_at = timezone.now()
            attempt.submission_snapshot = serializer.validated_data['submission_snapshot']
            attempt.evidence_ref = serializer.validated_data['evidence_ref']
            attempt.save(update_fields=[
                'status', 'submitted_at', 'submission_snapshot', 'evidence_ref',
            ])
            emit_event(
                user=request.user,
                event_type='task_submit',
                event_id=f'lm-task-submit-{attempt.attempt_id}',
                catalog=attempt.catalog,
                task=attempt.task,
                attempt_id=attempt.attempt_id,
                capability_ids=attempt.capability_ids,
                evidence_ref=attempt.evidence_ref,
                extra={'module6_connected': False},
            )
        return Response({
            **_attempt_payload(attempt),
            'created': True,
            'detail': '提交已保存，等待核验结果。',
        }, status=status.HTTP_202_ACCEPTED)


class VerificationFactIngestView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        if not (_is_teacher(request.user) or _service_authorized(request)):
            raise PermissionDenied('仅教师、管理员或带服务令牌的核验服务可以回传核验事实。')
        serializer = VerificationFactSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        data['student'] = get_object_or_404(User, pk=data['student'])
        try:
            fact, state, changed, created = ingest_verification_fact(data, actor=request.user if request.user.is_authenticated else None)
        except FactConflict as exc:
            raise FactConflictAPI({'detail': str(exc)})
        except FactError as exc:
            raise DomainErrorAPI({'detail': str(exc)})
        return Response(
            build_ack(fact, state, changed, created),
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class MyChangelogView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        catalog = _readable_catalog(request.user, request.query_params.get('version'))
        logs = PathChangeLog.objects.filter(
            student=request.user, catalog=catalog,
        ).select_related('capability').order_by('-created_at')[:200]
        return Response({'catalog_version': catalog.version, 'items': [
            {
                'capability_title': log.capability.title if log.capability else '学习路径',
                'from_state_label': constants.STATE_LABELS.get(log.from_state, ''),
                'to_state_label': constants.STATE_LABELS.get(log.to_state, log.to_state),
                'reason_label': constants.reason_label(log.reason),
                'created_at': log.created_at.isoformat(),
            }
            for log in logs
        ]})


class TeacherStudentChangelogView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, student_id):
        _require_teacher(request.user)
        student = get_object_or_404(User, pk=student_id)
        catalog = _readable_catalog(request.user, request.query_params.get('version'))
        logs = PathChangeLog.objects.filter(
            student=student, catalog=catalog,
        ).select_related('capability').order_by('-created_at')[:200]
        return Response({'catalog_version': catalog.version, 'items': [
            {
                'capability_id': log.capability.stable_id if log.capability else '',
                'from_state': log.from_state,
                'to_state': log.to_state,
                'reason': log.reason,
                'rule_version': log.rule_version,
                'fact_id': log.trigger_fact.fact_id if log.trigger_fact else '',
                'created_at': log.created_at.isoformat(),
            }
            for log in logs
        ]})


class TeacherAdjustmentView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        _require_teacher(request.user)  # any teacher may read their own assignments
        student_id = request.query_params.get('student')
        catalog = _readable_catalog(request.user, request.query_params.get('version'))
        queryset = TeacherAdjustment.objects.filter(catalog=catalog).select_related('capability', 'task')
        if student_id:
            queryset = queryset.filter(student_id=student_id)
        return Response({'catalog_version': catalog.version, 'items': [
            _adjustment_payload(adjustment) for adjustment in queryset.order_by('-created_at')[:200]
        ]})

    def post(self, request):
        _require_teacher(request.user)
        serializer = TeacherAdjustmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        catalog = get_object_or_404(CatalogVersion, version=data['catalog_version'])
        student = get_object_or_404(User, pk=data['student'])
        capability = None
        if data.get('capability_id'):
            capability = get_object_or_404(Capability, catalog=catalog, stable_id=data['capability_id'])
        task = None
        if data.get('task_key'):
            task = get_object_or_404(
                TaskPackage,
                catalog=catalog,
                task_key=data['task_key'],
                version=data.get('task_version') or '',
            )
            if task.requires_milestone_i or not task.environment_available or task.materials_withdrawn:
                raise DomainErrorAPI({'detail': '该任务当前不可用，不能指定。'})
        adjustment = TeacherAdjustment.objects.create(
            catalog=catalog,
            teacher=request.user,
            student=student,
            capability=capability,
            task=task,
            action=data['action'],
            rationale=data['rationale'],
            status=data['status'],
        )
        emit_event(
            user=student,
            event_type='teacher_help',
            event_id=f'lm-adjustment-{adjustment.id}',
            catalog=catalog,
            task=task,
            capability_ids=[capability.stable_id] if capability else [],
            extra={
                'adjustment_id': adjustment.id,
                'teacher_id': request.user.id,
                'action': adjustment.action,
                'rationale': adjustment.rationale,
            },
        )
        return Response(_adjustment_payload(adjustment), status=status.HTTP_201_CREATED)


class DeliveryRegisterView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        _require_course_owner(request.user)
        catalog = _readable_catalog(request.user, request.query_params.get('version'))
        items = DeliveryRegisterItem.objects.filter(catalog=catalog).select_related(
            'author', 'reviewer',
        ).order_by('delivery_no')
        return Response({
            'catalog_version': catalog.version,
            'readiness': catalog_service.publish_readiness(catalog),
            'items': [
                {
                    'delivery_no': item.delivery_no,
                    'title': item.title,
                    'required_contents': item.required_contents,
                    'version': item.version,
                    'author': item.author_id,
                    'author_name': item.author.username if item.author else '',
                    'reviewer': item.reviewer_id,
                    'reviewer_name': item.reviewer.username if item.reviewer else '',
                    'planned_hours': str(item.planned_hours) if item.planned_hours is not None else None,
                    'due_date': item.due_date.isoformat() if item.due_date else None,
                    'status': item.status,
                    'status_label': item.get_status_display(),
                    'signed_off_at': item.signed_off_at.isoformat() if item.signed_off_at else None,
                    'open_issues': item.open_issues,
                    'attachment_path': item.attachment_path,
                    'notes': item.notes,
                }
                for item in items
            ],
        })


class DeliveryRegisterDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, delivery_no):
        _require_course_owner(request.user)
        item = get_object_or_404(DeliveryRegisterItem, delivery_no=delivery_no)
        serializer = DeliveryRegisterUpdateSerializer(item, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({
            'delivery_no': item.delivery_no,
            'status': item.status,
            'status_label': item.get_status_display(),
            'signed_off_at': item.signed_off_at.isoformat() if item.signed_off_at else None,
            'reviewer': item.reviewer_id,
            'attachment_path': item.attachment_path,
        })


class CatalogFreezeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, version):
        _require_admin(request.user)
        catalog = get_object_or_404(CatalogVersion, version=version)
        try:
            catalog_service.freeze_catalog(catalog, actor=request.user)
        except catalog_service.PublishBlocked as exc:
            raise PublishBlockedAPI({'missing': exc.missing, 'detail': '冻结条件未满足。'})
        except ValueError as exc:
            raise DomainErrorAPI({'detail': str(exc)})
        return Response({
            **catalog_service.catalog_version_payload(catalog),
            'readiness': catalog_service.publish_readiness(catalog),
        })


class CatalogPublishView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, version):
        _require_admin(request.user)
        catalog = get_object_or_404(CatalogVersion, version=version)
        try:
            catalog_service.publish_catalog(catalog, actor=request.user)
        except catalog_service.PublishBlocked as exc:
            raise PublishBlockedAPI({'missing': exc.missing, 'detail': '发布条件未满足。'})
        except ValueError as exc:
            raise DomainErrorAPI({'detail': str(exc)})
        return Response({
            **catalog_service.catalog_version_payload(catalog),
            'readiness': catalog_service.publish_readiness(catalog),
        })


class CatalogExportView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, version):
        _require_course_owner(request.user)
        catalog = get_object_or_404(CatalogVersion, version=version)
        export_format = request.query_params.get('format', 'case')
        if export_format == 'case':
            return Response(export_case_package(catalog))
        if export_format == 'xapi':
            student_id = request.query_params.get('student')
            if not student_id:
                raise DomainErrorAPI({'detail': '导出 xAPI 样例需要 student 参数。'})
            student = get_object_or_404(User, pk=student_id)
            return Response({
                'catalog_version': catalog.version,
                'student': student.id,
                'statements': export_xapi_statements(student, catalog),
                'external_lrs_connected': False,
            })
        raise DomainErrorAPI({'detail': '仅支持 format=case 或 format=xapi。'})


class AttemptListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        catalog = _readable_catalog(request.user, request.query_params.get('version'))
        attempts = TaskAttempt.objects.filter(
            student=request.user, catalog=catalog,
        ).select_related('task').order_by('-claimed_at')[:100]
        return Response({'catalog_version': catalog.version, 'items': [
            _attempt_payload(attempt) for attempt in attempts
        ]})
