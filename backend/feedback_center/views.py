"""HTTP API for module 7 phase 1.

Students can submit, read only their own feedback, append evidence and download
only visible attachments.  Teachers/admins can use the queue, act on tickets,
create reproducible sampling batches and reconcile shared events.  Every list,
detail, attachment and mutation endpoint checks the role and record ownership on
the server.
"""

import hashlib

from django.contrib.auth import get_user_model
from django.db import DatabaseError, connection
from django.db.models import Case, IntegerField, Q, Value, When
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import constants
from .models import (
    FeedbackCandidate,
    FeedbackIssueGroup,
    FeedbackAccessLog,
    FeedbackAttachment,
    FeedbackEventLink,
    FeedbackSamplingBatch,
    FeedbackTicket,
)
from .serializers import (
    AttachmentUploadSerializer,
    CandidateActivateSerializer,
    CandidateApproveSerializer,
    CandidateCreateSerializer,
    CandidateObserveSerializer,
    CandidateReportSerializer,
    CandidateRollbackSerializer,
    EvidenceAddSerializer,
    FeedbackCreateSerializer,
    IssueGroupConfirmSerializer,
    IssueGroupCreateSerializer,
    IssueGroupMemberSerializer,
    IssueGroupMergeSerializer,
    IssueGroupRejectSerializer,
    IssueGroupSplitSerializer,
    SamplingBatchCreateSerializer,
    TeacherActionSerializer,
)
from .services import evidence as evidence_service
from .services import candidates as candidate_service
from .services import dispute_link, issue_groups, phase3, reconciliation, sampling, submission, workflow
from .services.events import link_payload


User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
        return Response(
            {'code': 'forbidden', 'detail': '需要教师或管理员权限。'},
            status=status.HTTP_403_FORBIDDEN,
        )
    return None


def _can_access(user, ticket):
    if _is_teacher(user):
        return True
    return user.id in (ticket.student_id, ticket.submitter_id)


def _audience(user):
    return 'teacher' if _is_teacher(user) else 'student'


def _label(mapping, value):
    return mapping.get(value, value or '')


def _iso(value):
    return value.isoformat() if value else None


def _attachment_payload(attachment, audience):
    if audience == 'student' and attachment.visibility != constants.VISIBILITY_STUDENT:
        return None
    return {
        'attachment_id': str(attachment.attachment_id),
        'original_name': attachment.original_name,
        'content_type': attachment.content_type,
        'size': attachment.size,
        'visibility': attachment.visibility,
        'visibility_label': _label(constants.VISIBILITY_LABELS, attachment.visibility),
        'download_url': f'/api/feedback/{attachment.ticket.feedback_id}/attachments/{attachment.attachment_id}/download/',
        'created_at': _iso(attachment.created_at),
    }


def _evidence_payload(row, audience):
    if audience == 'student' and row.visibility != constants.VISIBILITY_STUDENT:
        return None
    attachment = _attachment_payload(row.attachment, audience) if row.attachment_id else None
    payload = {
        'evidence_id': str(row.evidence_id),
        'slot': row.slot,
        'slot_label': _label(constants.EVIDENCE_SLOT_LABELS, row.slot),
        'version': row.version,
        'summary': row.summary,
        'status': row.status,
        'status_label': _label(constants.EVIDENCE_STATUS_LABELS, row.status),
        'source': row.source,
        'source_label': _label(constants.EVIDENCE_SOURCE_LABELS, row.source),
        'visibility': row.visibility,
        'visibility_label': _label(constants.VISIBILITY_LABELS, row.visibility),
        'is_current': row.is_current,
        'created_at': _iso(row.created_at),
        'attachment': attachment,
    }
    if audience == 'teacher' or row.source == constants.EVIDENCE_SOURCE_SUBMITTER:
        payload['ref'] = row.ref
    else:
        payload['ref'] = ''
    return payload


def _action_payload(action, audience):
    if audience == 'student' and action.visibility != constants.VISIBILITY_STUDENT:
        return None
    payload = {
        'action_id': str(action.action_id),
        'action': action.action,
        'action_label': _label(constants.ACTION_LABELS, action.action),
        'from_status': action.from_status,
        'from_status_label': _label(constants.STATUS_LABELS, action.from_status),
        'to_status': action.to_status,
        'to_status_label': _label(constants.STATUS_LABELS, action.to_status),
        'reason': action.reason,
        'visibility': action.visibility,
        'ticket_version': action.ticket_version,
        'created_at': _iso(action.created_at),
    }
    if audience == 'teacher':
        payload.update({
            'actor_id': action.actor_id,
            'actor_name': action.actor.username if action.actor else '系统',
            'actor_role': action.actor_role,
            'metadata': action.metadata,
        })
    else:
        if action.actor_id is None:
            payload['actor_name'] = '系统'
        elif action.actor_role == 'student':
            payload['actor_name'] = '学生'
        else:
            payload['actor_name'] = '教师'
    return payload


def _review_payload(review, audience):
    payload = {
        'review_id': str(review.review_id),
        'conclusion': review.conclusion,
        'conclusion_label': _label(constants.STATUS_LABELS, review.conclusion),
        'reason': review.reason,
        'reviewer_name': review.reviewer.username if review.reviewer else '',
        'reviewer_role': review.reviewer_role,
        'is_current': review.is_current,
        'ticket_version': review.ticket_version,
        'supersedes_review_id': str(review.supersedes.review_id) if review.supersedes else '',
        'created_at': _iso(review.created_at),
    }
    if audience == 'teacher':
        payload['evidence_refs'] = review.evidence_refs
        payload['original_decision_snapshot'] = review.original_decision_snapshot
    return payload


def _referral_payload(referral, audience):
    payload = {
        'referral_id': str(referral.referral_id),
        'destination': referral.destination,
        'destination_label': _label(constants.DESTINATION_LABELS, referral.destination),
        'status': referral.status,
        'status_label': _label(constants.REFERRAL_STATUS_LABELS, referral.status),
        'created_at': _iso(referral.created_at),
        'acknowledged_at': _iso(referral.acknowledged_at),
    }
    if audience == 'teacher':
        payload.update({
            'note': referral.note,
            'external_ref': referral.external_ref,
            'ack_note': referral.ack_note,
            'created_by': referral.created_by_id,
            'acknowledged_by': referral.acknowledged_by_id,
        })
    return payload


def _relation_payload(relation, ticket, audience):
    if relation.from_ticket_id == ticket.id:
        other = relation.to_ticket
        direction = 'outgoing'
    else:
        other = relation.from_ticket
        direction = 'incoming'
    payload = {
        'related_feedback_id': str(other.feedback_id),
        'relation_type': relation.relation_type,
        'relation_type_label': _label(constants.RELATION_TYPE_LABELS, relation.relation_type),
        'direction': direction,
    }
    if audience == 'teacher':
        payload['note'] = relation.note
    return payload


def _ticket_summary(ticket, audience):
    payload = {
        'feedback_id': str(ticket.feedback_id),
        'category': ticket.category,
        'category_label': _label(constants.CATEGORY_LABELS, ticket.category),
        'issue_type': ticket.issue_type,
        'issue_type_label': _label(constants.ISSUE_TYPE_LABELS, ticket.issue_type),
        'status': ticket.status,
        'status_label': _label(constants.STATUS_LABELS, ticket.status),
        'version': ticket.version,
        'created_at': _iso(ticket.created_at),
        'waiting_days': ticket.waiting_days,
        'impact_level': ticket.impact_level,
        'impact_label': _label(constants.IMPACT_LABELS, ticket.impact_level),
        'novelty': ticket.novelty,
        'novelty_label': _label(constants.NOVELTY_LABELS, ticket.novelty),
        'conflict_flag': ticket.conflict_flag,
        'priority_reason': ticket.priority_reason,
        'missing_evidence': list(ticket.missing_evidence or []),
        'missing_evidence_labels': [
            _label(constants.EVIDENCE_SLOT_LABELS, slot) for slot in (ticket.missing_evidence or [])
        ],
        'duplicate_of': str(ticket.duplicate_of.feedback_id) if ticket.duplicate_of else None,
        'duplicate_count': ticket.duplicates.count(),
        'candidate_eligible': ticket.candidate_eligible,
        'effect_status': ticket.effect_status,
        'effect_status_label': _label(constants.EFFECT_LABELS, ticket.effect_status),
        'handling_destination': ticket.handling_destination,
        'handling_destination_label': _label(constants.DESTINATION_LABELS, ticket.handling_destination),
        'owner_name': ticket.owner.username if ticket.owner else '',
        'owner_role': ticket.owner_role,
        'owner_role_label': _label(constants.OWNER_ROLE_LABELS, ticket.owner_role),
        'task_title': ticket.task.title if ticket.task else '',
        'task_version': ticket.task_version,
    }
    if audience == 'teacher':
        payload.update({
            'student_id': ticket.student_id,
            'student_name': ticket.student.username,
            'submitter_id': ticket.submitter_id,
            'submitter_name': ticket.submitter.username,
            'submitter_role': ticket.submitter_role,
            'catalog_version': ticket.catalog.version if ticket.catalog else '',
            'task_key': ticket.task.task_key if ticket.task else '',
            'attempt_id': str(ticket.attempt.attempt_id) if ticket.attempt else '',
            'attempt_ref': ticket.attempt_ref,
            'capability_id': ticket.capability.stable_id if ticket.capability else '',
            'knowledge_point_id': ticket.knowledge_point.stable_id if ticket.knowledge_point else '',
        })
    return payload


def _ticket_payload(ticket, audience, request=None):
    payload = {
        'schema_version': constants.FEEDBACK_SCHEMA_VERSION,
        'feedback_id': str(ticket.feedback_id),
        'category': ticket.category,
        'category_label': _label(constants.CATEGORY_LABELS, ticket.category),
        'issue_type': ticket.issue_type,
        'issue_type_label': _label(constants.ISSUE_TYPE_LABELS, ticket.issue_type),
        'status': ticket.status,
        'status_label': _label(constants.STATUS_LABELS, ticket.status),
        'version': ticket.version,
        'created_at': _iso(ticket.created_at),
        'submitted_at': _iso(ticket.submitted_at),
        'deduplicated_at': _iso(ticket.deduplicated_at),
        'reviewed_at': _iso(ticket.reviewed_at),
        'handling_started_at': _iso(ticket.handling_started_at),
        'handled_at': _iso(ticket.handled_at),
        'reopened_at': _iso(ticket.reopened_at),
        'last_evidence_at': _iso(ticket.last_evidence_at),
        'due_at': _iso(ticket.due_at),
        'waiting_days': ticket.waiting_days,
        'dispute': ticket.dispute,
        'expected_result': ticket.expected_result,
        'reason': ticket.reason,
        'task_title': ticket.task.title if ticket.task else '',
        'task_version': ticket.task_version,
        'attempt_status': ticket.attempt.get_status_display() if ticket.attempt else '',
        'capability_title': ticket.capability.title if ticket.capability else '',
        'knowledge_point_name': ticket.knowledge_point.name if ticket.knowledge_point else '',
        'impact_level': ticket.impact_level,
        'impact_label': _label(constants.IMPACT_LABELS, ticket.impact_level),
        'novelty': ticket.novelty,
        'novelty_label': _label(constants.NOVELTY_LABELS, ticket.novelty),
        'conflict_flag': ticket.conflict_flag,
        'priority_reason': ticket.priority_reason,
        'owner_name': ticket.owner.username if ticket.owner else '',
        'owner_role': ticket.owner_role,
        'owner_role_label': _label(constants.OWNER_ROLE_LABELS, ticket.owner_role),
        'handling_destination': ticket.handling_destination,
        'handling_destination_label': _label(constants.DESTINATION_LABELS, ticket.handling_destination),
        'handling_action': ticket.handling_action,
        'handling_note': ticket.handling_note,
        'effect_status': ticket.effect_status,
        'effect_status_label': _label(constants.EFFECT_LABELS, ticket.effect_status),
        'effect_note': ticket.effect_note,
        'evidence_complete': ticket.evidence_complete,
        'mapping_complete': ticket.mapping_complete,
        'candidate_eligible': ticket.candidate_eligible,
        'missing_evidence': list(ticket.missing_evidence or []),
        'missing_evidence_labels': [
            _label(constants.EVIDENCE_SLOT_LABELS, slot) for slot in (ticket.missing_evidence or [])
        ],
        'missing_mapping': evidence_service.mapping_missing_fields(ticket),
        'duplicate_of': str(ticket.duplicate_of.feedback_id) if ticket.duplicate_of else None,
        'duplicate_count': ticket.duplicates.count(),
        'production_effects': ticket.production_effects,
        'rule_activation': {
            'candidate_created': False,
            'config_changed': False,
            'rule_effective': False,
            'note': '反馈处理完成不等于新规则已生效；第三阶段候选管理本轮未启用。',
        },
        'execution_feedback_open': constants.EXECUTION_FEEDBACK_OPEN,
        'milestone_i_open': constants.MILESTONE_I_OPEN,
    }
    if audience == 'teacher':
        payload.update({
            'student_id': ticket.student_id,
            'student_name': ticket.student.username,
            'submitter_id': ticket.submitter_id,
            'submitter_name': ticket.submitter.username,
            'submitter_role': ticket.submitter_role,
            'catalog_version': ticket.catalog.version if ticket.catalog else '',
            'task_key': ticket.task.task_key if ticket.task else '',
            'task_status': ticket.task.status if ticket.task else '',
            'task_purpose': ticket.task.purpose if ticket.task else '',
            'attempt_id': str(ticket.attempt.attempt_id) if ticket.attempt else '',
            'attempt_ref': ticket.attempt_ref,
            'capability_id': ticket.capability.stable_id if ticket.capability else '',
            'knowledge_point_id': ticket.knowledge_point.stable_id if ticket.knowledge_point else '',
            'original_decision_ref': ticket.original_decision_ref,
            'original_decision_version': ticket.original_decision_version,
            'original_decision_snapshot': ticket.original_decision_snapshot,
            'context_snapshot': ticket.context_snapshot,
            'retest_fact_ref': ticket.retest_fact_ref,
            'retest_attempt_ref': ticket.retest_attempt_ref,
            'effect_updated_at': _iso(ticket.effect_updated_at),
            'dedup_key': ticket.dedup_key,
            'event_links': [link_payload(link) for link in ticket.event_links.select_related('action').order_by('created_at')],
            'reconciliation': reconciliation.ticket_reconciliation(ticket),
            'access_log_count': ticket.access_logs.count(),
        })
    else:
        payload.update({
            'original_decision_ref': ticket.original_decision_ref,
            'original_decision_version': ticket.original_decision_version,
        })

    evidence_rows = ticket.evidence.filter(is_current=True).select_related('attachment').order_by('slot')
    payload['evidence'] = [
        item for item in (_evidence_payload(row, audience) for row in evidence_rows) if item
    ]
    payload['attachments'] = [
        item for item in (
            _attachment_payload(attachment, audience)
            for attachment in ticket.attachments.order_by('-created_at')
        ) if item
    ]
    payload['actions'] = [
        item for item in (
            _action_payload(action, audience)
            for action in ticket.actions.select_related('actor').order_by('created_at')
        ) if item
    ]
    payload['reviews'] = [
        _review_payload(review, audience)
        for review in ticket.reviews.select_related('reviewer', 'supersedes').order_by('created_at')
    ]
    payload['referrals'] = [
        _referral_payload(referral, audience)
        for referral in ticket.referrals.order_by('created_at')
    ]
    relations = list(ticket.relations_from.select_related('from_ticket', 'to_ticket')) + list(
        ticket.relations_to.select_related('from_ticket', 'to_ticket')
    )
    payload['relations'] = [_relation_payload(relation, ticket, audience) for relation in relations]
    return payload


def _log_access(ticket, user, action, *, allowed=True, note=''):
    FeedbackAccessLog.objects.create(
        ticket=ticket, actor=user if getattr(user, 'is_authenticated', False) else None,
        action=action, allowed=allowed, note=note[:255],
    )


def _get_ticket(feedback_id):
    return get_object_or_404(
        FeedbackTicket.objects.select_related(
            'catalog', 'task', 'attempt', 'capability', 'knowledge_point',
            'duplicate_of', 'owner', 'handling_owner', 'current_review',
            'student', 'submitter',
        ),
        feedback_id=feedback_id,
    )


def _error(exc):
    return Response(
        {'code': exc.code, 'detail': exc.detail, **exc.extra},
        status=exc.status_code,
    )


# ---------------------------------------------------------------------------
# Public/student endpoints
# ---------------------------------------------------------------------------

class FeedbackStatusView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        try:
            tables = set(connection.introspection.table_names())
            skill_review_connected = 'skill_review_verificationresult' in tables
        except Exception:
            skill_review_connected = False
        return Response({
            'module': 'feedback_center',
            'schema_version': constants.FEEDBACK_SCHEMA_VERSION,
            'phase3_contract_version': constants.PHASE3_CONTRACT_VERSION,
            'execution_feedback_open': constants.EXECUTION_FEEDBACK_OPEN,
            'milestone_i_open': constants.MILESTONE_I_OPEN,
            'candidate_management_enabled': constants.CANDIDATE_MANAGEMENT_ENABLED,
            'candidate_release_enabled': constants.CANDIDATE_RELEASE_ENABLED,
            'ai_required_for_core': False,
            'production_effects': {
                'export_triggered': False,
                'quota_reserved': False,
                'policy_changed': False,
            },
            'module6_fact_source': 'learning_map.VerificationFact + learning_analytics.LearningEvent',
            'module6_extension_connected': skill_review_connected,
            'note': '首期只读教学反馈；不触发执行、不预占生产配额、不修改生产策略。',
        })


class FeedbackOptionsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            'schema_version': constants.FEEDBACK_SCHEMA_VERSION,
            'categories': [
                {
                    'value': value,
                    'label': label,
                    'issue_types': [
                        {'value': issue_value, 'label': issue_label}
                        for issue_value, issue_label in constants.issue_type_choices(value)
                    ],
                    'required_slots': [
                        {'slot': slot, 'label': _label(constants.EVIDENCE_SLOT_LABELS, slot)}
                        for slot in constants.REQUIRED_SLOTS.get(value, [])
                    ],
                }
                for value, label in constants.CATEGORY_CHOICES
            ],
            'conditional_slots': [
                {
                    'category': category,
                    'issue_type': issue_type,
                    'slots': [
                        {'slot': slot, 'label': _label(constants.EVIDENCE_SLOT_LABELS, slot)}
                        for slot in slots
                    ],
                }
                for (category, issue_type), slots in constants.CONDITIONAL_REQUIRED_SLOTS.items()
            ],
            'statuses': [
                {'value': value, 'label': label} for value, label in constants.STATUS_CHOICES
            ],
            'destinations': [
                {'value': value, 'label': label} for value, label in constants.DESTINATION_CHOICES
            ],
            'owner_roles': [
                {'value': value, 'label': label} for value, label in constants.OWNER_ROLE_CHOICES
            ],
            'impact_levels': [
                {'value': value, 'label': label} for value, label in constants.IMPACT_CHOICES
            ],
            'novelty': [
                {'value': value, 'label': label} for value, label in constants.NOVELTY_CHOICES
            ],
            'effect_statuses': [
                {'value': value, 'label': label} for value, label in constants.EFFECT_CHOICES
            ],
            'evidence_statuses': [
                {'value': value, 'label': label} for value, label in constants.EVIDENCE_STATUS_CHOICES
            ],
            'execution_feedback_open': constants.EXECUTION_FEEDBACK_OPEN,
            'milestone_i_open': constants.MILESTONE_I_OPEN,
            'attachment_max_bytes': constants.ATTACHMENT_MAX_BYTES,
            'attachment_allowed_extensions': sorted(constants.ATTACHMENT_ALLOWED_EXTENSIONS),
        })


class FeedbackCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = FeedbackCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = submission.create_feedback(request.user, serializer.validated_data)
        except submission.FeedbackError as exc:
            return _error(exc)
        except evidence_service.EvidenceError as exc:
            return Response(
                {'code': exc.code, 'detail': str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except DatabaseError:
            return Response(
                {
                    'code': 'save_failed_retry',
                    'detail': '保存失败，请使用同一客户端提交标识重试。',
                    'retryable': True,
                    'client_request_id': serializer.validated_data.get('client_request_id'),
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        payload = _ticket_payload(result.ticket, _audience(request.user), request)
        payload.update({
            'created': result.created,
            'idempotent_replay': result.idempotent,
            'event_sync': result.event_sync,
        })
        return Response(
            payload,
            status=status.HTTP_201_CREATED if result.created else status.HTTP_200_OK,
        )


class MyFeedbackListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = FeedbackTicket.objects.filter(
            Q(submitter=request.user) | Q(student=request.user),
        ).select_related('task', 'duplicate_of', 'owner', 'student', 'submitter').order_by('-created_at')
        status_filter = request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        category = request.query_params.get('category')
        if category:
            queryset = queryset.filter(category=category)
        total = queryset.count()
        items = [_ticket_summary(ticket, 'student') for ticket in queryset[:100]]
        counts = {
            value: queryset.filter(status=value).count()
            for value, _ in constants.STATUS_CHOICES
        }
        return Response({
            'schema_version': constants.FEEDBACK_SCHEMA_VERSION,
            'total': total,
            'counts': counts,
            'items': items,
            'execution_feedback_open': constants.EXECUTION_FEEDBACK_OPEN,
            'milestone_i_open': constants.MILESTONE_I_OPEN,
        })


class FeedbackDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, feedback_id):
        ticket = _get_ticket(feedback_id)
        if not _can_access(request.user, ticket):
            _log_access(ticket, request.user, constants.ACCESS_VIEW_DETAIL, allowed=False, note='forbidden')
            return Response(
                {'code': 'forbidden', 'detail': '只能查看本人反馈；教师按职责访问。'},
                status=status.HTTP_403_FORBIDDEN,
            )
        _log_access(ticket, request.user, constants.ACCESS_VIEW_DETAIL, allowed=True)
        return Response(_ticket_payload(ticket, _audience(request.user), request))


class FeedbackEvidenceAddView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, feedback_id):
        ticket = _get_ticket(feedback_id)
        if not _can_access(request.user, ticket):
            return Response(
                {'code': 'forbidden', 'detail': '只能为本人反馈补充证据。'},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = EvidenceAddSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            ticket, sync = submission.add_student_evidence(
                request.user, ticket,
                serializer.validated_data['items'],
                serializer.validated_data.get('reason') or '',
            )
        except submission.FeedbackError as exc:
            return _error(exc)
        except evidence_service.EvidenceError as exc:
            return Response(
                {'code': exc.code, 'detail': str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        payload = _ticket_payload(ticket, _audience(request.user), request)
        payload['event_sync'] = sync
        return Response(payload, status=status.HTTP_200_OK)


class FeedbackAttachmentUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, feedback_id):
        ticket = _get_ticket(feedback_id)
        if not _can_access(request.user, ticket):
            return Response(
                {'code': 'forbidden', 'detail': '只能为本人反馈上传附件。'},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = AttachmentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        upload = serializer.validated_data['file']
        visibility = serializer.validated_data.get('visibility') or constants.VISIBILITY_STUDENT
        if not _is_teacher(request.user) and visibility == constants.VISIBILITY_STAFF:
            return Response(
                {'code': 'forbidden', 'detail': '学生不能上传仅教师可见的附件。'},
                status=status.HTTP_403_FORBIDDEN,
            )
        digest = hashlib.sha256()
        for chunk in upload.chunks():
            digest.update(chunk)
        upload.seek(0)
        attachment = FeedbackAttachment.objects.create(
            ticket=ticket,
            file=upload,
            original_name=(upload.name or 'attachment').rsplit('/', 1)[-1].rsplit('\\', 1)[-1],
            content_type=getattr(upload, 'content_type', '') or 'application/octet-stream',
            size=upload.size,
            sha256=digest.hexdigest(),
            visibility=visibility,
            uploaded_by=request.user,
        )
        _log_access(ticket, request.user, 'upload_attachment', allowed=True)
        return Response(
            _attachment_payload(attachment, _audience(request.user)),
            status=status.HTTP_201_CREATED,
        )


class FeedbackAttachmentDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, feedback_id, attachment_id):
        ticket = _get_ticket(feedback_id)
        attachment = get_object_or_404(
            FeedbackAttachment, ticket=ticket, attachment_id=attachment_id,
        )
        if not _can_access(request.user, ticket):
            _log_access(ticket, request.user, constants.ATTACHMENT_DOWNLOAD_ACTION, allowed=False, note='forbidden')
            return Response(
                {'code': 'forbidden', 'detail': '无权访问该附件。'},
                status=status.HTTP_403_FORBIDDEN,
            )
        if not _is_teacher(request.user) and attachment.visibility != constants.VISIBILITY_STUDENT:
            _log_access(ticket, request.user, constants.ATTACHMENT_DOWNLOAD_ACTION, allowed=False, note='staff_only')
            return Response(
                {'code': 'forbidden', 'detail': '该附件仅教师可见。'},
                status=status.HTTP_403_FORBIDDEN,
            )
        _log_access(ticket, request.user, constants.ATTACHMENT_DOWNLOAD_ACTION, allowed=True)
        response = FileResponse(
            attachment.file.open('rb'),
            as_attachment=True,
            filename=attachment.original_name,
            content_type='application/octet-stream',
        )
        response['X-Content-Type-Options'] = 'nosniff'
        return response


# ---------------------------------------------------------------------------
# Teacher endpoints
# ---------------------------------------------------------------------------

def _queue_queryset(request):
    queryset = FeedbackTicket.objects.select_related(
        'task', 'student', 'submitter', 'owner', 'duplicate_of', 'catalog',
        'attempt', 'capability', 'knowledge_point',
    )
    include_duplicates = request.query_params.get('include_duplicates', 'false').lower() in ('1', 'true', 'yes')
    if not include_duplicates:
        queryset = queryset.exclude(status=constants.STATUS_DUPLICATE).exclude(duplicate_of__isnull=False)
    statuses = [item for item in (request.query_params.get('status') or '').split(',') if item]
    if statuses:
        queryset = queryset.filter(status__in=statuses)
    category = request.query_params.get('category')
    if category:
        queryset = queryset.filter(category=category)
    issue_type = request.query_params.get('issue_type')
    if issue_type:
        queryset = queryset.filter(issue_type=issue_type)
    owner = request.query_params.get('owner')
    if owner == 'me':
        queryset = queryset.filter(owner=request.user)
    elif owner == 'unassigned':
        queryset = queryset.filter(owner__isnull=True)
    elif owner:
        queryset = queryset.filter(owner_id=owner)
    return queryset


def _priority_order(queryset):
    return queryset.annotate(
        impact_rank=Case(
            *[When(impact_level=value, then=Value(rank)) for value, rank in constants.IMPACT_RANK.items()],
            default=Value(0), output_field=IntegerField(),
        ),
        novelty_rank=Case(
            *[When(novelty=value, then=Value(rank)) for value, rank in constants.NOVELTY_RANK.items()],
            default=Value(0), output_field=IntegerField(),
        ),
    ).order_by('-conflict_flag', '-impact_rank', '-novelty_rank', 'created_at')


class TeacherFeedbackQueueView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        denied = _require_teacher(request.user)
        if denied:
            return denied
        queryset = _queue_queryset(request)
        counts = {
            value: queryset.filter(status=value).count()
            for value, _ in constants.STATUS_CHOICES
        }
        sort = request.query_params.get('sort', 'priority')
        if sort == 'newest':
            queryset = queryset.order_by('-created_at')
        elif sort == 'waiting':
            queryset = queryset.order_by('created_at')
        else:
            queryset = _priority_order(queryset)
        try:
            page = max(1, int(request.query_params.get('page', 1)))
            page_size = min(100, max(1, int(request.query_params.get('page_size', 20))))
        except (TypeError, ValueError):
            page, page_size = 1, 20
        total = queryset.count()
        start = (page - 1) * page_size
        items = [
            _ticket_summary(ticket, 'teacher')
            for ticket in queryset[start:start + page_size]
        ]
        return Response({
            'schema_version': constants.FEEDBACK_SCHEMA_VERSION,
            'total': total,
            'page': page,
            'page_size': page_size,
            'counts': counts,
            'sort': sort,
            'items': items,
            'note': '默认按证据冲突、影响、新颖性、等待时间排序；重复投诉数不参与正确性或优先级计算。',
        })


class TeacherFeedbackDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, feedback_id):
        denied = _require_teacher(request.user)
        if denied:
            return denied
        ticket = _get_ticket(feedback_id)
        _log_access(ticket, request.user, constants.ACCESS_VIEW_DETAIL, allowed=True)
        return Response(_ticket_payload(ticket, 'teacher', request))


class TeacherFeedbackActionView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, feedback_id):
        denied = _require_teacher(request.user)
        if denied:
            return denied
        ticket = _get_ticket(feedback_id)
        serializer = TeacherActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            ticket, action_row, sync = workflow.perform_action(
                request.user, ticket,
                serializer.validated_data['action'],
                serializer.validated_data,
            )
        except workflow.WorkflowError as exc:
            return _error(exc)
        payload = _ticket_payload(ticket, 'teacher', request)
        payload.update({
            'action': action_row.action,
            'action_id': str(action_row.action_id),
            'event_sync': sync,
        })
        return Response(payload, status=status.HTTP_200_OK)


class SamplingBatchListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        denied = _require_teacher(request.user)
        if denied:
            return denied
        batches = FeedbackSamplingBatch.objects.select_related('created_by').order_by('-created_at')[:50]
        return Response({
            'schema_version': constants.FEEDBACK_SCHEMA_VERSION,
            'items': [sampling.batch_payload(batch, include_items=False) for batch in batches],
            'note': '抽样批次保存范围、总体摘要、随机种子与入选原因；高风险样本单列。',
        })

    def post(self, request):
        denied = _require_teacher(request.user)
        if denied:
            return denied
        serializer = SamplingBatchCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        scope = dict(data.get('scope') or {})
        scope.setdefault('exclude_prior', data.get('exclude_prior', True))
        scope.setdefault('include_duplicates', data.get('include_duplicates', False))
        try:
            batch = sampling.create_batch(
                request.user,
                scope=scope,
                sample_size=data.get('sample_size'),
                sample_ratio=data.get('sample_ratio'),
                random_seed=data.get('random_seed'),
                risk_ticket_ids=data.get('risk_ticket_ids') or [],
                notes=data.get('notes') or '',
            )
        except sampling.SamplingError as exc:
            return Response({'code': exc.code, 'detail': exc.detail}, status=status.HTTP_400_BAD_REQUEST)
        return Response(sampling.batch_payload(batch), status=status.HTTP_201_CREATED)


class SamplingBatchDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, batch_id):
        denied = _require_teacher(request.user)
        if denied:
            return denied
        batch = get_object_or_404(
            FeedbackSamplingBatch.objects.select_related('created_by'), batch_id=batch_id,
        )
        return Response(sampling.batch_payload(batch))


class FeedbackReconciliationView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        denied = _require_teacher(request.user)
        if denied:
            return denied
        return Response(reconciliation.queue(limit=200))


class FeedbackReconciliationRetryView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        denied = _require_teacher(request.user)
        if denied:
            return denied
        ticket_id = request.data.get('ticket_id')
        if ticket_id:
            result = reconciliation.retry(request.user, ticket_id=ticket_id)
            if result.get('error') == 'ticket_not_found':
                return Response({'code': 'ticket_not_found', 'detail': '反馈工单不存在。'}, status=status.HTTP_404_NOT_FOUND)
            return Response(result)
        return Response(reconciliation.retry(request.user))


class Phase3ContractView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        denied = _require_teacher(request.user)
        if denied:
            return denied
        return Response(phase3.contract_payload())


def _service_error(exc):
    code = getattr(exc, "code", "invalid_request")
    status_code = (
        status.HTTP_409_CONFLICT
        if code in (constants.PHASE3_WRITE_DISABLED, constants.PHASE3_RELEASE_DISABLED)
        else status.HTTP_400_BAD_REQUEST
    )
    return Response({"code": code, "detail": str(exc)}, status=status_code)


def _decorate_phase3(payload):
    payload["phase3_write_enabled"] = candidate_service.phase3_enabled()
    payload["release_enabled"] = candidate_service.release_enabled()
    return payload


class IssueGroupListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        denied = _require_teacher(request.user)
        if denied:
            return denied
        queryset = FeedbackIssueGroup.objects.select_related("catalog", "task").order_by("-created_at")
        state_filter = request.query_params.get("status")
        if state_filter:
            queryset = queryset.filter(status=state_filter)
        category = request.query_params.get("category")
        if category:
            queryset = queryset.filter(category=category)
        return Response(_decorate_phase3({
            "items": [
                issue_groups.group_payload(group, include_members=False)
                for group in queryset[:100]
            ],
        }))

    def post(self, request):
        denied = _require_teacher(request.user)
        if denied:
            return denied
        serializer = IssueGroupCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        catalog = None
        if data.get("catalog_version"):
            from learning_map.models import CatalogVersion

            catalog = CatalogVersion.objects.filter(version=data["catalog_version"]).first()
            if catalog is None:
                return Response({"detail": "目录版本不存在。"}, status=status.HTTP_400_BAD_REQUEST)
        task = None
        if data.get("task_key"):
            from learning_map.models import TaskPackage

            task = TaskPackage.objects.filter(
                catalog=catalog,
                task_key=data["task_key"],
                version=data.get("task_version") or "",
            ).first()
            if task is None:
                return Response({"detail": "任务不存在。"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            group = issue_groups.create_group(
                actor=request.user,
                title=data["title"],
                category=data["category"],
                issue_type=data["issue_type"],
                window_start=data["window_start"],
                window_end=data["window_end"],
                catalog=catalog,
                task=task,
                notes=data.get("notes", ""),
            )
        except issue_groups.IssueGroupError as exc:
            return _service_error(exc)
        return Response(issue_groups.group_payload(group), status=status.HTTP_201_CREATED)


class IssueGroupDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, group_id):
        denied = _require_teacher(request.user)
        if denied:
            return denied
        group = get_object_or_404(FeedbackIssueGroup, group_id=group_id)
        return Response(_decorate_phase3(issue_groups.group_payload(group)))


class IssueGroupMemberView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, group_id):
        denied = _require_teacher(request.user)
        if denied:
            return denied
        group = get_object_or_404(FeedbackIssueGroup, group_id=group_id)
        serializer = IssueGroupMemberSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        ticket = get_object_or_404(FeedbackTicket, feedback_id=data["feedback_id"])
        try:
            member, created = issue_groups.add_member(
                group,
                ticket,
                actor=request.user,
                included=data["included"],
                reason=data.get("reason", ""),
            )
        except issue_groups.IssueGroupError as exc:
            return _service_error(exc)
        return Response(
            {
                "member": {
                    "feedback_id": str(member.ticket.feedback_id),
                    "included": member.included,
                    "exclusion_reason": member.exclusion_reason,
                },
                "created": created,
                "counts": group.counts,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class IssueGroupConfirmView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, group_id):
        denied = _require_teacher(request.user)
        if denied:
            return denied
        group = get_object_or_404(FeedbackIssueGroup, group_id=group_id)
        serializer = IssueGroupConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            group = issue_groups.confirm_group(
                group, reviewer=request.user, notes=serializer.validated_data.get("notes", ""),
            )
        except issue_groups.IssueGroupError as exc:
            return _service_error(exc)
        return Response(issue_groups.group_payload(group))


class IssueGroupRejectView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, group_id):
        denied = _require_teacher(request.user)
        if denied:
            return denied
        group = get_object_or_404(FeedbackIssueGroup, group_id=group_id)
        serializer = IssueGroupRejectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            group = issue_groups.reject_group(
                group, reviewer=request.user, reason=serializer.validated_data["reason"],
            )
        except issue_groups.IssueGroupError as exc:
            return _service_error(exc)
        return Response(issue_groups.group_payload(group))


class IssueGroupSplitView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, group_id):
        denied = _require_teacher(request.user)
        if denied:
            return denied
        group = get_object_or_404(FeedbackIssueGroup, group_id=group_id)
        serializer = IssueGroupSplitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            new_group = issue_groups.split_group(
                group,
                feedback_ids=serializer.validated_data["feedback_ids"],
                actor=request.user,
                title=serializer.validated_data.get("title", ""),
            )
        except issue_groups.IssueGroupError as exc:
            return _service_error(exc)
        return Response(issue_groups.group_payload(new_group), status=status.HTTP_201_CREATED)


class IssueGroupMergeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        denied = _require_teacher(request.user)
        if denied:
            return denied
        serializer = IssueGroupMergeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        groups = list(
            FeedbackIssueGroup.objects.filter(group_id__in=serializer.validated_data["group_ids"])
        )
        try:
            merged = issue_groups.merge_groups(
                groups,
                actor=request.user,
                title=serializer.validated_data.get("title", ""),
            )
        except issue_groups.IssueGroupError as exc:
            return _service_error(exc)
        return Response(issue_groups.group_payload(merged), status=status.HTTP_201_CREATED)


class CandidateListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        denied = _require_teacher(request.user)
        if denied:
            return denied
        queryset = FeedbackCandidate.objects.select_related("owner").order_by("-created_at")
        state_filter = request.query_params.get("state")
        if state_filter:
            queryset = queryset.filter(state=state_filter)
        return Response(_decorate_phase3({
            "items": [candidate_service.candidate_payload(row) for row in queryset[:100]],
        }))

    def post(self, request):
        denied = _require_teacher(request.user)
        if denied:
            return denied
        serializer = CandidateCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            candidate = candidate_service.create_candidate(
                actor=request.user, **serializer.validated_data,
            )
        except candidate_service.CandidateError as exc:
            return _service_error(exc)
        return Response(
            candidate_service.candidate_payload(candidate), status=status.HTTP_201_CREATED,
        )


class CandidateDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, candidate_id):
        denied = _require_teacher(request.user)
        if denied:
            return denied
        candidate = get_object_or_404(FeedbackCandidate, candidate_id=candidate_id)
        return Response(_decorate_phase3(candidate_service.candidate_payload(candidate)))


class CandidateSubmitView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, candidate_id):
        denied = _require_teacher(request.user)
        if denied:
            return denied
        candidate = get_object_or_404(FeedbackCandidate, candidate_id=candidate_id)
        try:
            candidate = candidate_service.submit_for_evaluation(candidate, actor=request.user)
        except candidate_service.CandidateError as exc:
            return _service_error(exc)
        return Response(candidate_service.candidate_payload(candidate))


class CandidateReportView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, candidate_id):
        denied = _require_teacher(request.user)
        if denied:
            return denied
        candidate = get_object_or_404(FeedbackCandidate, candidate_id=candidate_id)
        serializer = CandidateReportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            candidate = candidate_service.attach_report(
                candidate, actor=request.user, report=dict(serializer.validated_data),
            )
        except candidate_service.CandidateError as exc:
            return _service_error(exc)
        return Response(candidate_service.candidate_payload(candidate))


class CandidateCompleteEvaluationView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, candidate_id):
        denied = _require_teacher(request.user)
        if denied:
            return denied
        candidate = get_object_or_404(FeedbackCandidate, candidate_id=candidate_id)
        try:
            candidate = candidate_service.complete_evaluation(
                candidate, actor=request.user, note=request.data.get("note", ""),
            )
        except candidate_service.CandidateError as exc:
            return _service_error(exc)
        return Response(candidate_service.candidate_payload(candidate))


class CandidateApproveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, candidate_id):
        denied = _require_teacher(request.user)
        if denied:
            return denied
        candidate = get_object_or_404(FeedbackCandidate, candidate_id=candidate_id)
        serializer = CandidateApproveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            candidate = candidate_service.approve(
                candidate, approver=request.user, **serializer.validated_data,
            )
        except candidate_service.CandidateError as exc:
            return _service_error(exc)
        return Response(candidate_service.candidate_payload(candidate))


class CandidateActivateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, candidate_id):
        denied = _require_teacher(request.user)
        if denied:
            return denied
        candidate = get_object_or_404(FeedbackCandidate, candidate_id=candidate_id)
        serializer = CandidateActivateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            candidate = candidate_service.activate(
                candidate,
                operator=request.user,
                applicable_future_tasks=serializer.validated_data.get("applicable_future_tasks", []),
            )
        except candidate_service.CandidateError as exc:
            return _service_error(exc)
        return Response(candidate_service.candidate_payload(candidate))


class CandidateObserveView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, candidate_id):
        denied = _require_teacher(request.user)
        if denied:
            return denied
        candidate = get_object_or_404(FeedbackCandidate, candidate_id=candidate_id)
        serializer = CandidateObserveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            candidate = candidate_service.record_observation(
                candidate, actor=request.user, **serializer.validated_data,
            )
        except candidate_service.CandidateError as exc:
            return _service_error(exc)
        return Response(candidate_service.candidate_payload(candidate))


class CandidateStableView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, candidate_id):
        denied = _require_teacher(request.user)
        if denied:
            return denied
        candidate = get_object_or_404(FeedbackCandidate, candidate_id=candidate_id)
        try:
            candidate = candidate_service.mark_stable(
                candidate, actor=request.user, note=request.data.get("note", ""),
            )
        except candidate_service.CandidateError as exc:
            return _service_error(exc)
        return Response(candidate_service.candidate_payload(candidate))


class CandidateRollbackView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, candidate_id):
        denied = _require_teacher(request.user)
        if denied:
            return denied
        candidate = get_object_or_404(FeedbackCandidate, candidate_id=candidate_id)
        serializer = CandidateRollbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            candidate = candidate_service.rollback(
                candidate, operator=request.user, **serializer.validated_data,
            )
        except candidate_service.CandidateError as exc:
            return _service_error(exc)
        return Response(candidate_service.candidate_payload(candidate))


class FeedbackDisputeLinkView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, feedback_id):
        denied = _require_teacher(request.user)
        if denied:
            return denied
        ticket = _get_ticket(feedback_id)
        try:
            link, created = dispute_link.open_dispute_for_ticket(ticket, actor=request.user)
        except dispute_link.DisputeLinkError as exc:
            return _service_error(exc)
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        return Response(
            {**dispute_link.link_payload(link), "created": created},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def get(self, request, feedback_id):
        denied = _require_teacher(request.user)
        if denied:
            return denied
        ticket = _get_ticket(feedback_id)
        link = getattr(ticket, "module6_dispute_link", None)
        if link is None:
            return Response({"linked": False})
        link, changed = dispute_link.sync_dispute_status(link)
        return Response({**dispute_link.link_payload(link), "linked": True, "changed": changed})
