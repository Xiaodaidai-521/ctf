from __future__ import annotations

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from learning_map import constants as map_constants
from skill_review import constants as review_constants
from skill_review.services import submissions as assistance_service

from .events import bounded_event_id, canonical_hash, record_teaching_event
from .models import HintCard, HintDelivery, ResumeReceipt, StudentAnalysis, TeacherTicket, TeachingRun


class StateVersionConflict(ValueError):
    pass


class IdempotencyConflict(ValueError):
    pass


def _active_run(context):
    run = TeachingRun.objects.select_for_update().select_related('attempt__task', 'attempt__catalog').get(pk=context.run.pk)
    if run.student_id != context.student_id:
        raise PermissionDenied('This teaching run belongs to another student.')
    return run


def _require_mutable(run):
    if run.state == TeachingRun.STATE_ENDED:
        raise ValidationError({'state': 'The teaching run has ended.'})
    if run.state == TeachingRun.STATE_PAUSED:
        raise ValidationError({'state': 'Resume the teaching run first.'})


def _hint_unlocked(run, card):
    rule = card.unlock_rule if isinstance(card.unlock_rule, dict) else {}
    if card.level > 1 and rule.get('previous_level_shown', True):
        if not run.hint_deliveries.filter(card__level=card.level - 1, displayed_at__isnull=False).exists():
            return False, 'previous_hint_not_shown'
    minimum_failures = int(rule.get('min_failed_submissions', 0) or 0)
    if minimum_failures:
        failures = run.attempt.verification_results.filter(
            is_current=True,
            overall_status__in=[review_constants.OVERALL_FAILED, review_constants.OVERALL_VERIFICATION_FAILED],
        ).count()
        if failures < minimum_failures:
            return False, 'insufficient_failed_submissions'
    statuses = rule.get('attempt_statuses') or []
    if statuses and run.attempt.status not in statuses:
        return False, 'attempt_status_locked'
    return True, 'unlocked'


def request_hint(*, context, request_id, level, source='card'):
    if context.task.purpose == map_constants.PURPOSE_RETEST:
        raise PermissionDenied('Hints are not available during an independent retest.')
    payload = {'level': int(level), 'source': source}
    payload_hash = canonical_hash(payload)
    with transaction.atomic():
        existing = HintDelivery.objects.select_related('card', 'assistance_record').filter(request_id=request_id).first()
        if existing:
            if existing.student_id != context.student_id or existing.run_id != context.run.pk or existing.payload_hash != payload_hash:
                raise IdempotencyConflict('The hint request ID already exists with different content.')
            return existing, False
        run = _active_run(context)
        _require_mutable(run)
        try:
            card = HintCard.objects.get(task=run.attempt.task, level=level, is_active=True)
        except HintCard.DoesNotExist:
            raise ValidationError({'level': 'No active reviewed hint card is available at this level.'})
        except HintCard.MultipleObjectsReturned:
            card = HintCard.objects.filter(task=run.attempt.task, level=level, is_active=True).order_by('-version', '-id').first()
        from learning_knowledge.policy import require_card
        require_card(context, card.material_ref, 'hint', card.level)
        unlocked, reason = _hint_unlocked(run, card)
        if not unlocked:
            raise PermissionDenied(f'Hint level is locked: {reason}.')
        record = assistance_service.request_hint(
            student=run.student,
            attempt=run.attempt,
            level=level,
            source=review_constants.ASSISTANCE_SOURCE_CARD,
            content_ref=card.material_ref or f'hint-card:{card.pk}@{card.version}',
        )
        delivery = HintDelivery.objects.create(
            request_id=request_id,
            student=run.student,
            run=run,
            attempt=run.attempt,
            card=card,
            assistance_record=record,
            source=source,
            payload_hash=payload_hash,
            permission_version=run.permission_version,
        )
        record_teaching_event(
            student=run.student,
            event_id=bounded_event_id('m2-hint-req', request_id),
            event_type='hint_requested',
            attempt=run.attempt,
            run=run,
            payload={'request_id': request_id, 'level': level, 'source': source, 'shown': False, 'material_version': card.version},
        )
        return delivery, True


def display_hint(*, context, request_id):
    with transaction.atomic():
        run = _active_run(context)
        _require_mutable(run)
        try:
            delivery = HintDelivery.objects.select_for_update().select_related('card', 'assistance_record').get(request_id=request_id)
        except HintDelivery.DoesNotExist:
            raise ValidationError({'request_id': 'Hint request not found.'})
        if delivery.student_id != context.student_id or delivery.run_id != run.pk:
            raise PermissionDenied('This hint request belongs to another student.')
        if run.attempt.task.purpose == map_constants.PURPOSE_RETEST:
            raise PermissionDenied('Hints are not available during an independent retest.')
        if run.attempt.task.materials_withdrawn or not delivery.card.is_active:
            raise PermissionDenied('The hint material has been withdrawn.')
        from learning_knowledge.policy import require_card
        revision = require_card(context, delivery.card.material_ref, 'hint', delivery.card.level)
        if revision:
            delivery.card.content = revision.source_snapshot
            delivery.card.title = revision.title
        if delivery.permission_version != run.permission_version:
            raise PermissionDenied('Hint authorization is stale; request it again.')
        if not delivery.displayed_at:
            record, _ = assistance_service.show_hint(record=delivery.assistance_record, actor=run.student)
            delivery.displayed_at = record.shown_at or timezone.now()
            delivery.save(update_fields=['displayed_at'])
            run.hint_level = max(run.hint_level, delivery.card.level)
            run.state = TeachingRun.STATE_SHOWING_HELP
            run.state_version += 1
            run.save(update_fields=['hint_level', 'state', 'state_version', 'updated_at'])
            record_teaching_event(
                student=run.student,
                event_id=bounded_event_id('m2-hint-show', request_id),
                event_type='hint_displayed',
                attempt=run.attempt,
                run=run,
                payload={
                    'request_id': request_id,
                    'record_id': str(record.record_id),
                    'level': delivery.card.level,
                    'source': delivery.source,
                    'shown': True,
                    'material_version': delivery.card.version,
                },
            )
        return delivery, run


def pause_run(*, context, expected_state_version):
    with transaction.atomic():
        run = _active_run(context)
        if run.state_version != expected_state_version:
            raise StateVersionConflict('Teaching run state version changed; refresh and retry.')
        if run.state == TeachingRun.STATE_ENDED:
            raise ValidationError({'state': 'The teaching run has ended.'})
        if run.state != TeachingRun.STATE_PAUSED:
            run.state = TeachingRun.STATE_PAUSED
            run.state_version += 1
            run.paused_at = timezone.now()
            run.save(update_fields=['state', 'state_version', 'paused_at', 'updated_at'])
            record_teaching_event(
                student=run.student,
                event_id=bounded_event_id('m2-pause', run.run_id, run.state_version),
                event_type='teaching_run_paused',
                attempt=run.attempt,
                run=run,
                payload={'expected_state_version': expected_state_version},
            )
        return run


def resume_run(*, context, request_id, expected_state_version):
    payload = {'run_id': str(context.run.run_id), 'expected_state_version': expected_state_version}
    payload_hash = canonical_hash(payload)
    with transaction.atomic():
        receipt = ResumeReceipt.objects.select_for_update().filter(request_id=request_id).first()
        if receipt:
            if receipt.student_id != context.student_id or receipt.run_id != context.run.pk or receipt.payload_hash != payload_hash:
                raise IdempotencyConflict('The resume request ID already exists with different content.')
            return receipt.result, False
        run = _active_run(context)
        if run.state_version != expected_state_version:
            raise StateVersionConflict('Teaching run state version changed; refresh and retry.')
        if run.state != TeachingRun.STATE_PAUSED:
            raise ValidationError({'state': 'Only a paused teaching run can be resumed.'})
        run.state = TeachingRun.STATE_READY
        run.state_version += 1
        run.paused_at = None
        run.save(update_fields=['state', 'state_version', 'paused_at', 'updated_at'])
        result = {
            'run_id': str(run.run_id),
            'state': run.state,
            'state_version': run.state_version,
            'context_version': run.context_version,
            'resumed': True,
        }
        ResumeReceipt.objects.create(
            request_id=request_id,
            student=run.student,
            run=run,
            expected_state_version=expected_state_version,
            payload_hash=payload_hash,
            result=result,
        )
        record_teaching_event(
            student=run.student,
            event_id=bounded_event_id('m2-resume', request_id),
            event_type='teaching_run_resumed',
            attempt=run.attempt,
            run=run,
            payload={'request_id': request_id, 'expected_state_version': expected_state_version},
        )
        return result, True


def open_teacher_ticket(*, context, question_summary):
    with transaction.atomic():
        run = _active_run(context)
        _require_mutable(run)
        ticket = TeacherTicket.objects.create(
            run=run,
            attempt=run.attempt,
            student=run.student,
            question_summary=question_summary,
        )
        run.state = TeachingRun.STATE_WAITING_TEACHER
        run.state_version += 1
        run.save(update_fields=['state', 'state_version', 'updated_at'])
        record_teaching_event(
            student=run.student,
            event_id=bounded_event_id('m2-ticket', ticket.ticket_id),
            event_type='teacher_ticket_opened',
            attempt=run.attempt,
            run=run,
            payload={'ticket_id': str(ticket.ticket_id)},
        )
        return ticket


def record_ticket_help(*, ticket, teacher, summary):
    if getattr(teacher, 'role', None) not in ('teacher', 'admin') and not getattr(teacher, 'is_superuser', False):
        raise PermissionDenied('Teacher role is required.')
    with transaction.atomic():
        ticket = TeacherTicket.objects.select_for_update().select_related('run', 'attempt__task', 'attempt__catalog', 'student').get(pk=ticket.pk)
        if ticket.status in (TeacherTicket.STATUS_HELPED, TeacherTicket.STATUS_CLOSED):
            return ticket, False
        now = timezone.now()
        assistance_service.record_teacher_help(teacher=teacher, attempt=ticket.attempt, summary=summary)
        ticket.status = TeacherTicket.STATUS_HELPED
        ticket.claimed_by = teacher
        ticket.claimed_at = ticket.claimed_at or now
        ticket.helped_at = now
        ticket.actual_help_summary = summary
        ticket.save(update_fields=['status', 'claimed_by', 'claimed_at', 'helped_at', 'actual_help_summary', 'updated_at'])
        run = ticket.run
        if run.state != TeachingRun.STATE_ENDED:
            run.state = TeachingRun.STATE_SHOWING_HELP
            run.state_version += 1
            run.save(update_fields=['state', 'state_version', 'updated_at'])
        record_teaching_event(
            student=ticket.student,
            event_id=bounded_event_id('m2-teacher-help', ticket.ticket_id),
            event_type='teacher_help_displayed',
            attempt=ticket.attempt,
            run=run,
            payload={'ticket_id': str(ticket.ticket_id), 'shown': True},
        )
        return ticket, True


def authorized_analysis(*, context):
    if context.attempt.status != map_constants.ATTEMPT_VERIFIED:
        raise PermissionDenied('Student analysis is locked until verification is complete.')
    passed = context.attempt.verification_results.filter(
        is_current=True,
        overall_status=review_constants.OVERALL_PASSED,
    ).exists()
    if not passed:
        raise PermissionDenied('Student analysis is locked until the task is passed.')
    analysis = StudentAnalysis.objects.filter(task=context.task, is_active=True).order_by('-version', '-id').first()
    if not analysis:
        raise ValidationError({'analysis': 'No active student analysis is available.'})
    from learning_knowledge.policy import require_card
    revision = require_card(context, analysis.content_ref, 'student_analysis')
    if revision:
        analysis.content = revision.source_snapshot
        analysis.title = revision.title
    record = assistance_service.record_analysis_view(
        student=context.attempt.student,
        task=context.task,
        attempt=context.attempt,
        content_ref=analysis.content_ref or f'student-analysis:{analysis.pk}@{analysis.version}',
    )
    record_teaching_event(
        student=context.attempt.student,
        event_id=bounded_event_id('m2-analysis', record.record_id),
        event_type='student_analysis_viewed',
        attempt=context.attempt,
        run=context.run,
        payload={'analysis_id': analysis.pk, 'version': analysis.version, 'content_ref': analysis.content_ref or None},
    )
    return analysis
