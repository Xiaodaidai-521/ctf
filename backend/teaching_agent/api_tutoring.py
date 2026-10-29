from __future__ import annotations

import asyncio
import hashlib
import json
import time
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from skill_review import constants as review_constants
from skill_review.services import submissions as assistance_service

from .events import bounded_event_id, canonical_hash, record_teaching_event
from .models import HintCard, ModelCallRecord, ProviderCircuit, TeachingRun, TutorRequest, TutorResponseCache
from .permissions import require_tool_permission


class TutorRequestConflict(ValueError):
    pass


class UnauthorizedToolSuggestion(ValueError):
    pass


class ProviderRateLimited(Exception):
    pass


class ProviderQuotaExhausted(Exception):
    pass


def _material_hash(context):
    cards = list(
        HintCard.objects.filter(task=context.task, is_active=True)
        .order_by('level', 'version')
        .values('level', 'version', 'material_ref', 'updated_at')
    )
    from learning_knowledge.policy import task_policy_stamp
    from learning_knowledge.models import CourseGrant
    return canonical_hash({
        'material_acl': task_policy_stamp(context.task),
        'course_grants': list(CourseGrant.objects.filter(user_id=context.student_id, catalog=context.catalog).values_list('active', flat=True)),
        'materials': context.task.materials,
        'cards': cards,
        'student_solution_ref': context.task.student_solution_ref,
    })


def _cache_key(*, context, message, hint_level, material_hash):
    subject = f'{context.task.track}:{context.task.task_key}'
    payload = {
        'student_id': context.student_id,
        'attempt_id': str(context.attempt.attempt_id),
        'run_id': str(context.run.run_id),
        'subject': subject,
        'message': message.strip(),
        'hint_level': hint_level,
        'context_version': context.run.context_version,
        'permission_version': context.run.permission_version,
        'material_hash': material_hash,
        'template_version': 'module2-tutor-v1',
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest(), subject


def _reauthorize(context, *, permission_version, material_hash):
    context.run.refresh_from_db()
    context.task.refresh_from_db()
    if context.run.student_id != context.student_id or context.run.attempt_id != context.attempt.pk:
        raise PermissionDenied('Teaching authorization changed.')
    if context.task.materials_withdrawn:
        raise PermissionDenied('Task materials have been withdrawn.')
    from learning_knowledge.models import TaskMaterial
    from learning_knowledge.policy import Scope, live_attempt
    if TaskMaterial.objects.filter(task=context.task).exists():
        live_attempt(Scope(context.attempt.student, context.attempt.attempt_id))
    if context.run.permission_version != permission_version:
        raise PermissionDenied('Teaching permission version changed.')
    if _material_hash(context) != material_hash:
        raise PermissionDenied('Teaching materials changed; request fresh tutoring.')


def _validate_result(context, result, requested_level):
    if not isinstance(result, dict):
        raise ValueError('Provider response must be an object.')
    from learning_knowledge.models import TaskMaterial
    if TaskMaterial.objects.filter(task=context.task).exists():
        # A citation ID alone cannot certify an inference. Use reviewed static cards in phase 1.
        raise ValueError('Evidence-backed explanations require review before display.')
    content = str(result.get('content') or '').strip()
    if not content:
        raise ValueError('Provider response has no content.')
    response_level = int(result.get('hint_level', requested_level) or requested_level)
    if response_level > requested_level or response_level < 1 or response_level > 4:
        raise ValueError('Provider response exceeds the authorized hint level.')
    for suggestion in result.get('tool_suggestions') or []:
        name = suggestion.get('name') if isinstance(suggestion, dict) else str(suggestion)
        try:
            require_tool_permission(context, name)
        except PermissionDenied as exc:
            raise UnauthorizedToolSuggestion(str(exc))
    return {
        'content': content,
        'hint_level': response_level,
        'sources': result.get('sources') if isinstance(result.get('sources'), list) else [],
        'tool_suggestions': result.get('tool_suggestions') if isinstance(result.get('tool_suggestions'), list) else [],
        'provider': str(result.get('provider') or ''),
        'model': str(result.get('model') or ''),
        'template_version': str(result.get('template_version') or 'module2-tutor-v1'),
        'input_tokens': result.get('input_tokens'),
        'output_tokens': result.get('output_tokens'),
        'provider_request_id': str(result.get('provider_request_id') or ''),
        'cost_amount': result.get('cost_amount'),
        'cost_currency': str(result.get('cost_currency') or ''),
        'cost_basis': str(result.get('cost_basis') or 'unknown'),
    }


def _classify_error(exc):
    status_code = getattr(exc, 'status_code', None)
    text = str(exc).lower()
    if isinstance(exc, asyncio.TimeoutError):
        return 'timeout'
    if isinstance(exc, ProviderQuotaExhausted) or any(token in text for token in ('quota exhausted', 'insufficient quota', '余额不足')):
        return 'quota_exhausted'
    if isinstance(exc, ProviderRateLimited) or status_code == 429:
        return 'rate_limited'
    if isinstance(exc, UnauthorizedToolSuggestion):
        return 'unauthorized_tool'
    if isinstance(exc, (ConnectionError, OSError)):
        return 'provider_unavailable'
    return 'provider_error'


def _circuit_allows(provider, now):
    circuit, _ = ProviderCircuit.objects.get_or_create(provider=provider)
    if circuit.state == 'closed':
        return circuit, True
    if circuit.state == 'open' and circuit.next_probe_at and circuit.next_probe_at <= now:
        circuit.state = 'half_open'
        circuit.last_probe_status = 'running'
        circuit.save(update_fields=['state', 'last_probe_status', 'updated_at'])
        return circuit, True
    if circuit.state == 'half_open' and circuit.last_probe_status != 'running':
        circuit.last_probe_status = 'running'
        circuit.save(update_fields=['last_probe_status', 'updated_at'])
        return circuit, True
    return circuit, False


def _record_circuit_success(circuit):
    circuit.state = 'closed'
    circuit.failure_count = 0
    circuit.opened_at = None
    circuit.next_probe_at = None
    circuit.last_probe_status = 'success'
    circuit.save(update_fields=['state', 'failure_count', 'opened_at', 'next_probe_at', 'last_probe_status', 'updated_at'])


def _record_circuit_failure(circuit, category):
    circuit.failure_count += 1
    circuit.last_probe_status = category
    threshold = max(1, int(getattr(settings, 'TUTORING_CIRCUIT_FAILURE_THRESHOLD', 3)))
    if category == 'quota_exhausted' or circuit.state == 'half_open' or circuit.failure_count >= threshold:
        circuit.state = 'open'
        circuit.opened_at = timezone.now()
        if category == 'quota_exhausted':
            circuit.next_probe_at = None
        else:
            seconds = max(1, int(getattr(settings, 'TUTORING_CIRCUIT_PROBE_SECONDS', 60)))
            circuit.next_probe_at = circuit.opened_at + timedelta(seconds=seconds)
    circuit.save(update_fields=['state', 'failure_count', 'opened_at', 'next_probe_at', 'last_probe_status', 'updated_at'])


async def _default_provider_call(*, message, model_context, hint_level):
    from ai_assistant.service import get_multi_agent_service

    result = await get_multi_agent_service().chat_with_agent(
        'tutor',
        message,
        {**model_context, 'authorized_hint_level': hint_level},
        [],
    )
    return result


def _run_with_budget(provider_call, *, message, model_context, hint_level, timeout):
    async def invoke():
        return await asyncio.wait_for(
            provider_call(message=message, model_context=model_context, hint_level=hint_level),
            timeout=timeout,
        )

    return asyncio.run(invoke())


def _record_assistance_display(*, context, request, level, source_ref):
    record = assistance_service.request_hint(
        student=context.attempt.student,
        attempt=context.attempt,
        level=level,
        source=review_constants.ASSISTANCE_SOURCE_AI,
        content_ref=source_ref,
    )
    assistance_service.show_hint(record=record, actor=context.attempt.student)
    run = TeachingRun.objects.select_for_update().get(pk=context.run.pk)
    run.hint_level = max(run.hint_level, level)
    run.state = TeachingRun.STATE_SHOWING_HELP
    run.state_version += 1
    run.save(update_fields=['hint_level', 'state', 'state_version', 'updated_at'])
    record_teaching_event(
        student=run.student,
        event_id=bounded_event_id('m2-ai-show', request.request_id),
        event_type='hint_displayed',
        attempt=run.attempt,
        run=run,
        payload={'request_id': request.request_id, 'level': level, 'source': 'ai', 'shown': True, 'content_ref': source_ref},
    )


def _fallback_response(*, context, request, category):
    from rest_framework.exceptions import NotFound
    from learning_map.constants import PURPOSE_RETEST
    card = None
    try:
        _reauthorize(context, permission_version=request.permission_version, material_hash=request.material_hash)
        if context.task.purpose != PURPOSE_RETEST:
            card = HintCard.objects.filter(task=context.task, level=1, is_active=True).order_by('-version', '-id').first()
    except (NotFound, PermissionDenied):
        pass
    if card:
        from learning_knowledge.policy import require_card
        from rest_framework.exceptions import NotFound
        try:
            revision = require_card(context, card.material_ref, 'hint', card.level)
            if revision:
                card.content = revision.source_snapshot
        except NotFound:
            card = None
    if card and not context.task.materials_withdrawn:
        response = {
            'content': card.content,
            'hint_level': card.level,
            'sources': [card.material_ref] if card.material_ref else [],
            'fallback': True,
            'fallback_reason': category,
            'material_version': card.version,
        }
        record = assistance_service.request_hint(
            student=context.attempt.student,
            attempt=context.attempt,
            level=card.level,
            source=review_constants.ASSISTANCE_SOURCE_CARD,
            content_ref=card.material_ref or f'hint-card:{card.pk}@{card.version}',
        )
        assistance_service.show_hint(record=record, actor=context.attempt.student)
        request.fallback_card = card
    else:
        response = {
            'content': 'AI tutoring is temporarily unavailable. Practice and deterministic submission remain available.',
            'hint_level': 0,
            'sources': [],
            'fallback': True,
            'fallback_reason': category,
        }
    run = TeachingRun.objects.select_for_update().get(pk=context.run.pk)
    run.state = TeachingRun.STATE_DEGRADED
    run.state_version += 1
    run.save(update_fields=['state', 'state_version', 'updated_at'])
    request.status = TutorRequest.STATUS_DEGRADED
    request.response = response
    request.save(update_fields=['status', 'response', 'fallback_card', 'updated_at'])
    record_teaching_event(
        student=run.student,
        event_id=bounded_event_id('m2-degraded', request.request_id),
        event_type='tutoring_degraded',
        attempt=run.attempt,
        run=run,
        payload={'request_id': request.request_id, 'category': category, 'fallback_card_id': card.pk if card else None},
    )
    return response


def accept_provider_result(*, request, context, result, latency_ms):
    """Commit only a still-current response; late or stale output is isolated."""
    with transaction.atomic():
        request = TutorRequest.objects.select_for_update().get(pk=request.pk)
        run = TeachingRun.objects.select_for_update().get(pk=context.run.pk)
        if (
            request.status != TutorRequest.STATUS_PENDING
            or run.context_version != request.context_version
            or run.permission_version != request.permission_version
            or run.state != TeachingRun.STATE_WAITING_AI
        ):
            request.late_response_discarded = True
            request.save(update_fields=['late_response_discarded', 'updated_at'])
            return None
        _reauthorize(context, permission_version=request.permission_version, material_hash=request.material_hash)
        validated = _validate_result(context, result, request.hint_level)
        request.status = TutorRequest.STATUS_SUCCEEDED
        request.response = {key: value for key, value in validated.items() if key not in ('input_tokens', 'output_tokens', 'cost_amount', 'cost_currency', 'cost_basis', 'provider_request_id')}
        request.save(update_fields=['status', 'response', 'updated_at'])
        call = ModelCallRecord.objects.filter(request=request).order_by('-created_at').first()
        if call:
            call.provider = validated['provider'] or call.provider
            call.model = validated['model']
            call.template_version = validated['template_version']
            call.input_tokens = validated['input_tokens']
            call.output_tokens = validated['output_tokens']
            call.latency_ms = latency_ms
            call.status = 'succeeded'
            call.cost_amount = validated['cost_amount']
            call.cost_currency = validated['cost_currency']
            call.cost_basis = validated['cost_basis']
            call.provider_request_id = validated['provider_request_id']
            call.save()
        _record_assistance_display(
            context=context,
            request=request,
            level=validated['hint_level'],
            source_ref=f'model-call:{call.call_id}' if call else f'tutor-request:{request.request_id}',
        )
        if call:
            record_teaching_event(
                student=context.attempt.student,
                event_id=bounded_event_id('m2-call-end', call.call_id),
                event_type='model_call_finished',
                attempt=context.attempt,
                run=TeachingRun.objects.get(pk=context.run.pk),
                payload={
                    'call_id': call.call_id,
                    'provider': call.provider or None,
                    'model': call.model or None,
                    'template_version': call.template_version or None,
                    'input_tokens': call.input_tokens,
                    'output_tokens': call.output_tokens,
                    'latency_ms': call.latency_ms,
                    'status': call.status,
                    'error_category': None,
                    'cost_basis': call.cost_basis,
                },
            )
        return request.response


def tutor(*, context, request_id, message, hint_level, provider='default', provider_call=None):
    started = time.monotonic()
    if context.run is None:
        raise ValidationError({'run_id': 'A teaching run is required.'})
    if context.run.state in (TeachingRun.STATE_PAUSED, TeachingRun.STATE_ENDED):
        raise ValidationError({'state': 'The teaching run is not available for tutoring.'})
    if hint_level < 1 or hint_level > 4:
        raise ValidationError({'hint_level': 'Must be between 1 and 4.'})
    from learning_map.constants import PURPOSE_RETEST
    if context.task.purpose == PURPOSE_RETEST:
        raise PermissionDenied('Hints are not available during an independent retest.')
    material_hash = _material_hash(context)
    _reauthorize(context, permission_version=context.run.permission_version, material_hash=material_hash)
    payload_hash = canonical_hash({'message': message, 'hint_level': hint_level, 'provider': provider})

    with transaction.atomic():
        existing = TutorRequest.objects.select_for_update().filter(request_id=request_id).first()
        if existing:
            if existing.student_id != context.student_id or existing.run_id != context.run.pk or existing.payload_hash != payload_hash:
                raise TutorRequestConflict('The tutoring request ID already exists with different content.')
            _reauthorize(context, permission_version=existing.permission_version, material_hash=existing.material_hash)
            if existing.status == TutorRequest.STATUS_PENDING:
                raise TutorRequestConflict('The tutoring request is still pending.')
            from learning_knowledge.models import TaskMaterial
            if TaskMaterial.objects.filter(task=context.task).exists():
                response = {'content': 'AI explanation requires review. Static evidence and submission remain available.',
                            'hint_level': 0, 'sources': [], 'fallback': True}
                if existing.fallback_card_id:
                    from learning_knowledge.policy import require_card
                    card = HintCard.objects.get(pk=existing.fallback_card_id, task=context.task, is_active=True)
                    revision = require_card(context, card.material_ref, 'hint', card.level)
                    response.update(content=revision.source_snapshot, hint_level=card.level,
                                    sources=[card.material_ref], material_version=card.version)
                return response, existing, False, False
            return existing.response, existing, False, False
        request = TutorRequest.objects.create(
            request_id=request_id,
            idempotency_key=request_id,
            payload_hash=payload_hash,
            student_id=context.student_id,
            run=context.run,
            attempt=context.attempt,
            hint_level=hint_level,
            context_version=context.run.context_version,
            permission_version=context.run.permission_version,
            material_hash=material_hash,
        )

        cache_key, subject = _cache_key(
            context=context,
            message=message,
            hint_level=hint_level,
            material_hash=material_hash,
        )
        from learning_knowledge.models import TaskMaterial
        cache_entry = None if TaskMaterial.objects.filter(task=context.task).exists() else TutorResponseCache.objects.filter(cache_key=cache_key, expires_at__gt=timezone.now()).first()
        if cache_entry:
            _reauthorize(context, permission_version=cache_entry.permission_version, material_hash=cache_entry.material_hash)
            request.status = TutorRequest.STATUS_SUCCEEDED
            request.response = cache_entry.response
            request.save(update_fields=['status', 'response', 'updated_at'])
            _record_assistance_display(
                context=context,
                request=request,
                level=hint_level,
                source_ref=f'tutor-cache:{cache_entry.cache_key}',
            )
            return request.response, request, True, True

        circuit, allowed = _circuit_allows(provider, timezone.now())
        if not allowed:
            return _fallback_response(context=context, request=request, category='circuit_open'), request, True, False
        run = TeachingRun.objects.select_for_update().get(pk=context.run.pk)
        run.state = TeachingRun.STATE_WAITING_AI
        run.state_version += 1
        run.save(update_fields=['state', 'state_version', 'updated_at'])
        call = ModelCallRecord.objects.create(
            request=request,
            call_id=bounded_event_id('m2-call', request_id),
            provider=provider,
            status='pending',
            cost_basis='unknown',
        )

    configured_budget = float(getattr(settings, 'TUTORING_TOTAL_WAIT_SECONDS', 10.0))
    total_budget = min(10.0, max(0.1, configured_budget))
    remaining = total_budget - (time.monotonic() - started)
    try:
        if remaining <= 0:
            raise asyncio.TimeoutError()
        result = _run_with_budget(
            provider_call or _default_provider_call,
            message=message,
            model_context=context.model_context(),
            hint_level=hint_level,
            timeout=remaining,
        )
        latency_ms = int((time.monotonic() - started) * 1000)
        response = accept_provider_result(request=request, context=context, result=result, latency_ms=latency_ms)
        if response is None:
            return request.response, request, False, False
        with transaction.atomic():
            _record_circuit_success(ProviderCircuit.objects.select_for_update().get(pk=circuit.pk))
            TutorResponseCache.objects.update_or_create(
                cache_key=cache_key,
                defaults={
                    'student_id': context.student_id,
                    'run': context.run,
                    'attempt': context.attempt,
                    'subject': subject,
                    'hint_level': hint_level,
                    'context_version': context.run.context_version,
                    'permission_version': context.run.permission_version,
                    'material_hash': material_hash,
                    'response': response,
                    'expires_at': timezone.now() + timedelta(seconds=max(1, int(getattr(settings, 'TUTORING_CACHE_TTL_SECONDS', 300)))),
                },
            )
        return response, request, True, False
    except Exception as exc:
        category = _classify_error(exc)
        latency_ms = int((time.monotonic() - started) * 1000)
        with transaction.atomic():
            call = ModelCallRecord.objects.select_for_update().get(pk=call.pk)
            call.latency_ms = latency_ms
            call.status = 'failed'
            call.error_category = category
            call.cancellation_status = 'requested' if category == 'timeout' else 'not_applicable'
            call.save(update_fields=['latency_ms', 'status', 'error_category', 'cancellation_status'])
            _record_circuit_failure(ProviderCircuit.objects.select_for_update().get(pk=circuit.pk), category)
            response = _fallback_response(context=context, request=request, category=category)
            record_teaching_event(
                student=context.attempt.student,
                event_id=bounded_event_id('m2-call-end', call.call_id),
                event_type='model_call_finished',
                attempt=context.attempt,
                run=TeachingRun.objects.get(pk=context.run.pk),
                payload={
                    'call_id': call.call_id,
                    'provider': call.provider or None,
                    'model': None,
                    'template_version': None,
                    'input_tokens': None,
                    'output_tokens': None,
                    'latency_ms': latency_ms,
                    'status': call.status,
                    'error_category': category,
                    'cost_basis': 'unknown',
                },
            )
        return response, request, True, False
