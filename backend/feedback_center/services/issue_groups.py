"""Cross-attempt issue groups (module 7, phase 3).

A group is evidence, not a conclusion.  Members are proposed by a deterministic
filter and must be confirmed by hand; counts are snapshotted at confirmation so
a later ticket edit cannot silently change what a candidate was approved on.
"""

from django.db import transaction
from django.utils import timezone

from .. import constants
from ..models import (
    FeedbackIssueGroup,
    FeedbackIssueGroupEvent,
    FeedbackIssueGroupMember,
    FeedbackTicket,
)


class IssueGroupError(ValueError):
    code = 'issue_group_invalid'


def _normalized_dispute(text):
    return ' '.join((text or '').split()).strip().lower()


def _instance_key(ticket):
    """Same attempt + same category + same issue type + same dispute = one instance."""

    attempt_key = (
        str(ticket.attempt_id) if ticket.attempt_id else (ticket.attempt_ref or f'ticket:{ticket.pk}')
    )
    return (
        attempt_key,
        ticket.category,
        ticket.issue_type,
        _normalized_dispute(ticket.dispute),
    )


def compute_counts(group):
    members = list(
        group.members.select_related('ticket').order_by('created_at')
    )
    included = [member for member in members if member.included]
    tickets = [member.ticket for member in included]
    instance_keys = {_instance_key(ticket) for ticket in tickets}
    students = {ticket.student_id for ticket in tickets}
    missing_evidence = sum(1 for ticket in tickets if ticket.missing_evidence)
    excluded = [member for member in members if not member.included]
    return {
        'raw_feedback': len(members),
        'included_feedback': len(included),
        'excluded_feedback': len(excluded),
        'deduplicated_instances': len(instance_keys),
        'distinct_students': len(students),
        'missing_evidence': missing_evidence,
        'instance_keys': sorted('|'.join(key) for key in instance_keys),
    }


def suggest_members(*, category, issue_type, catalog=None, task=None,
                    window_start, window_end):
    """Deterministic member proposal.

    Only tickets that already passed fact review are proposed; duplicates are
    excluded and their main record is used instead.
    """

    queryset = FeedbackTicket.objects.filter(
        category=category,
        issue_type=issue_type,
        status__in=constants.CANDIDATE_SOURCE_STATUSES,
        duplicate_of__isnull=True,
        created_at__gte=window_start,
        created_at__lte=window_end,
    ).select_related('student', 'task')
    if catalog is not None:
        queryset = queryset.filter(catalog=catalog)
    if task is not None:
        queryset = queryset.filter(task=task, task_version=task.version)
    return list(queryset.order_by('created_at', 'feedback_id'))


@transaction.atomic
def create_group(*, actor, title, category, issue_type, window_start, window_end,
                 catalog=None, task=None, notes=''):
    if window_start > window_end:
        raise IssueGroupError('时间窗开始不能晚于结束。')
    if not title.strip():
        raise IssueGroupError('问题组名称不能为空。')
    tickets = suggest_members(
        category=category, issue_type=issue_type, catalog=catalog, task=task,
        window_start=window_start, window_end=window_end,
    )
    group = FeedbackIssueGroup.objects.create(
        title=title.strip(),
        category=category,
        issue_type=issue_type,
        catalog=catalog,
        task=task,
        task_version=task.version if task else '',
        knowledge_point_ids=sorted(
            {
                ticket.knowledge_point.stable_id
                for ticket in tickets
                if ticket.knowledge_point_id
            }
        ),
        window_start=window_start,
        window_end=window_end,
        status=constants.ISSUE_GROUP_PENDING_CONFIRMATION,
        notes=notes,
        created_by=actor,
    )
    for ticket in tickets:
        FeedbackIssueGroupMember.objects.create(
            group=group, ticket=ticket, included=True, added_by=actor,
        )
    group.counts = compute_counts(group)
    group.save(update_fields=['counts', 'updated_at'])
    FeedbackIssueGroupEvent.objects.create(
        group=group,
        action=constants.ISSUE_GROUP_ACTION_CREATED,
        detail={'suggested_members': [str(ticket.feedback_id) for ticket in tickets]},
        actor=actor,
    )
    return group


@transaction.atomic
def add_member(group, ticket, *, actor, included=True, reason=''):
    if group.status in (constants.ISSUE_GROUP_CONFIRMED, constants.ISSUE_GROUP_SUPERSEDED):
        raise IssueGroupError('已确认的问题组不能直接改成员；请新建版本或拆组。')
    if ticket.duplicate_of_id:
        raise IssueGroupError('重复记录不能作为独立成员；请使用主记录。')
    if ticket.status not in constants.CANDIDATE_SOURCE_STATUSES:
        raise IssueGroupError('该反馈尚未完成事实确认，不能进入问题组。')
    if ticket.category != group.category or ticket.issue_type != group.issue_type:
        raise IssueGroupError('反馈类别或问题类型与问题组不一致。')
    if group.task_id and ticket.task_id != group.task_id:
        raise IssueGroupError('反馈不属于该问题组的任务。')
    member, created = FeedbackIssueGroupMember.objects.update_or_create(
        group=group,
        ticket=ticket,
        defaults={'included': included, 'exclusion_reason': reason, 'added_by': actor},
    )
    group.counts = compute_counts(group)
    group.save(update_fields=['counts', 'updated_at'])
    FeedbackIssueGroupEvent.objects.create(
        group=group,
        action=(
            constants.ISSUE_GROUP_ACTION_MEMBER_ADDED if included
            else constants.ISSUE_GROUP_ACTION_MEMBER_REMOVED
        ),
        detail={'feedback_id': str(ticket.feedback_id), 'reason': reason},
        actor=actor,
    )
    return member, created


@transaction.atomic
def confirm_group(group, *, reviewer, notes=''):
    if group.status == constants.ISSUE_GROUP_CONFIRMED:
        return group
    if group.status not in (
        constants.ISSUE_GROUP_DRAFT, constants.ISSUE_GROUP_PENDING_CONFIRMATION,
    ):
        raise IssueGroupError('该问题组当前不可确认。')
    members = list(group.members.select_related('ticket'))
    if not members:
        raise IssueGroupError('问题组没有成员，不能确认。')
    undecided = [
        member for member in members
        if not member.included and not member.exclusion_reason.strip()
    ]
    if undecided:
        raise IssueGroupError('排除成员必须写明理由。')
    included = [member for member in members if member.included]
    if not included:
        raise IssueGroupError('问题组没有纳入任何反馈，不能确认。')
    unconfirmed = [
        member.ticket.feedback_id for member in included
        if member.ticket.status not in constants.CANDIDATE_SOURCE_STATUSES
    ]
    if unconfirmed:
        raise IssueGroupError(
            f'存在未完成事实确认的反馈：{", ".join(str(item) for item in unconfirmed[:5])}'
        )

    counts = compute_counts(group)
    group.counts = counts
    group.status = constants.ISSUE_GROUP_CONFIRMED
    group.reviewed_by = reviewer
    group.reviewed_at = timezone.now()
    if notes:
        group.notes = notes
    group.save()
    FeedbackIssueGroupEvent.objects.create(
        group=group,
        action=constants.ISSUE_GROUP_ACTION_CONFIRMED,
        detail={'counts': counts},
        actor=reviewer,
    )
    return group


@transaction.atomic
def reject_group(group, *, reviewer, reason):
    if not reason.strip():
        raise IssueGroupError('驳回必须写明理由。')
    group.status = constants.ISSUE_GROUP_REJECTED
    group.reviewed_by = reviewer
    group.reviewed_at = timezone.now()
    group.notes = reason.strip()
    group.save()
    FeedbackIssueGroupEvent.objects.create(
        group=group,
        action=constants.ISSUE_GROUP_ACTION_REJECTED,
        detail={'reason': reason.strip()},
        actor=reviewer,
    )
    return group


@transaction.atomic
def split_group(group, *, feedback_ids, actor, title):
    """Split selected members into a new group version; the old one is kept."""

    if group.status != constants.ISSUE_GROUP_CONFIRMED:
        raise IssueGroupError('只有已确认的问题组可以拆分。')
    selected = set(str(item) for item in feedback_ids)
    members = list(group.members.select_related('ticket'))
    moving = [member for member in members if str(member.ticket.feedback_id) in selected]
    if not moving:
        raise IssueGroupError('没有匹配的成员可拆分。')
    if len(moving) == len([member for member in members if member.included]):
        raise IssueGroupError('不能把全部纳入成员拆出去。')

    new_group = FeedbackIssueGroup.objects.create(
        title=title.strip() or f'{group.title}（拆分）',
        category=group.category,
        issue_type=group.issue_type,
        catalog=group.catalog,
        task=group.task,
        task_version=group.task_version,
        knowledge_point_ids=group.knowledge_point_ids,
        window_start=group.window_start,
        window_end=group.window_end,
        status=constants.ISSUE_GROUP_CONFIRMED,
        reviewed_by=actor,
        reviewed_at=timezone.now(),
        version=group.version + 1,
        supersedes=group,
        created_by=actor,
    )
    for member in moving:
        FeedbackIssueGroupMember.objects.create(
            group=new_group,
            ticket=member.ticket,
            included=True,
            added_by=actor,
        )
        member.delete()
    group.status = constants.ISSUE_GROUP_SUPERSEDED
    group.save(update_fields=['status', 'updated_at'])
    new_group.counts = compute_counts(new_group)
    new_group.save(update_fields=['counts', 'updated_at'])
    group.counts = compute_counts(group)
    group.save(update_fields=['counts', 'updated_at'])
    FeedbackIssueGroupEvent.objects.create(
        group=group,
        action=constants.ISSUE_GROUP_ACTION_SPLIT,
        detail={'new_group_id': str(new_group.group_id), 'moved': sorted(selected)},
        actor=actor,
    )
    return new_group


@transaction.atomic
def merge_groups(groups, *, actor, title):
    groups = list(groups)
    if len(groups) < 2:
        raise IssueGroupError('并组至少需要两个已确认问题组。')
    if any(group.status != constants.ISSUE_GROUP_CONFIRMED for group in groups):
        raise IssueGroupError('只有已确认的问题组可以并组。')
    if len({(group.category, group.issue_type) for group in groups}) != 1:
        raise IssueGroupError('类别或问题类型不同的组不能直接合并，需先审核可比性。')
    if len({(group.task_id, group.task_version) for group in groups}) != 1:
        raise IssueGroupError('任务或任务版本不同的组不能直接合并。')

    base = groups[0]
    merged = FeedbackIssueGroup.objects.create(
        title=title.strip() or f'{base.title}（并组）',
        category=base.category,
        issue_type=base.issue_type,
        catalog=base.catalog,
        task=base.task,
        task_version=base.task_version,
        knowledge_point_ids=sorted(
            {point for group in groups for point in group.knowledge_point_ids}
        ),
        window_start=min(group.window_start for group in groups),
        window_end=max(group.window_end for group in groups),
        status=constants.ISSUE_GROUP_CONFIRMED,
        reviewed_by=actor,
        reviewed_at=timezone.now(),
        version=max(group.version for group in groups) + 1,
        supersedes=base,
        created_by=actor,
    )
    seen = set()
    for group in groups:
        for member in group.members.select_related('ticket'):
            if member.ticket_id in seen:
                continue
            seen.add(member.ticket_id)
            FeedbackIssueGroupMember.objects.create(
                group=merged,
                ticket=member.ticket,
                included=member.included,
                exclusion_reason=member.exclusion_reason,
                added_by=actor,
            )
        group.status = constants.ISSUE_GROUP_SUPERSEDED
        group.save(update_fields=['status', 'updated_at'])
    merged.counts = compute_counts(merged)
    merged.save(update_fields=['counts', 'updated_at'])
    FeedbackIssueGroupEvent.objects.create(
        group=merged,
        action=constants.ISSUE_GROUP_ACTION_MERGED,
        detail={'source_group_ids': [str(group.group_id) for group in groups]},
        actor=actor,
    )
    return merged


def group_payload(group, *, include_members=True):
    payload = {
        'group_id': str(group.group_id),
        'title': group.title,
        'category': group.category,
        'category_label': constants.CATEGORY_LABELS.get(group.category, group.category),
        'issue_type': group.issue_type,
        'issue_type_label': constants.ISSUE_TYPE_LABELS.get(group.issue_type, group.issue_type),
        'task_key': group.task.task_key if group.task else '',
        'task_version': group.task_version,
        'catalog_version': group.catalog.version if group.catalog else '',
        'knowledge_point_ids': group.knowledge_point_ids,
        'window_start': group.window_start.isoformat(),
        'window_end': group.window_end.isoformat(),
        'status': group.status,
        'status_label': constants.ISSUE_GROUP_STATUS_LABELS.get(group.status, group.status),
        'counts': group.counts,
        'version': group.version,
        'supersedes': str(group.supersedes.group_id) if group.supersedes else None,
        'reviewed_by': group.reviewed_by_id,
        'reviewed_at': group.reviewed_at.isoformat() if group.reviewed_at else None,
        'notes': group.notes,
        'created_at': group.created_at.isoformat(),
    }
    if include_members:
        payload['members'] = [
            {
                'feedback_id': str(member.ticket.feedback_id),
                'student': member.ticket.student.username,
                'included': member.included,
                'exclusion_reason': member.exclusion_reason,
                'ticket_status': member.ticket.status,
            }
            for member in group.members.select_related('ticket__student').order_by('created_at')
        ]
        payload['history'] = [
            {
                'action': event.action,
                'detail': event.detail,
                'actor': event.actor_id,
                'created_at': event.created_at.isoformat(),
            }
            for event in group.events.order_by('-created_at')[:50]
        ]
    return payload
