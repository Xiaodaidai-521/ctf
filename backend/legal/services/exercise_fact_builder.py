"""Build minimal, traceable facts from an authorized CTF exercise session."""

from dataclasses import asdict, dataclass
from datetime import timedelta
from typing import Optional

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from audit.models import AuditEvent, AuditLedgerEntry
from audit.services import canonical_json, sha256_hex
from challenges.models import ChallengeContainer
from submissions.models import Submission

from .fact_redactor import REDACTION_VERSION, safe_container_event

EXTRACTION_VERSION = 'v1'
TERMINAL_ACTIONS = {'stop_succeeded', 'expired_cleanup'}


@dataclass(frozen=True)
class ExerciseFactScope:
    container_id: int
    started_at: Optional[object] = None
    ended_at: Optional[object] = None


@dataclass(frozen=True)
class ExerciseFactPreview:
    scope: dict
    facts: dict
    warnings: list
    evidence_refs: list
    preview_hash: str
    extraction_version: str = EXTRACTION_VERSION
    redaction_version: str = REDACTION_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


class ExerciseFactBuilder:
    """Aggregate application audit data without reading raw commands or traffic."""

    def build(self, *, scope: ExerciseFactScope, actor) -> ExerciseFactPreview:
        container = self._validate_scope(scope=scope, actor=actor)
        window_start, window_end = self._resolve_window(container=container, scope=scope)
        events = self._load_events(container, window_start, window_end)
        submissions = self._load_submissions(container, window_start, window_end)
        facts = self._aggregate(container, events, submissions, window_start, window_end)
        warnings = self._derive_warnings(facts, events)
        evidence_refs = self._build_evidence_refs(events, window_start, window_end)
        scope_payload = {
            'container_id': container.id,
            'challenge_id': container.challenge_id,
            'subject_user_id': container.user_id,
            'started_at': window_start.isoformat(),
            'ended_at': window_end.isoformat(),
        }
        preview_hash = sha256_hex(canonical_json({
            'scope': scope_payload,
            'facts': facts,
            'warnings': warnings,
            'evidence_refs': evidence_refs,
            'extraction_version': EXTRACTION_VERSION,
            'redaction_version': REDACTION_VERSION,
        }))
        return ExerciseFactPreview(
            scope=scope_payload,
            facts=facts,
            warnings=warnings,
            evidence_refs=evidence_refs,
            preview_hash=preview_hash,
        )

    def _validate_scope(self, *, scope, actor):
        if not actor or not actor.is_authenticated:
            raise PermissionDenied('Authentication is required.')
        if not (actor.is_staff or getattr(actor, 'role', '') == 'admin'):
            raise PermissionDenied('Only administrators can extract exercise facts.')
        try:
            return ChallengeContainer.objects.select_related('challenge', 'user').get(pk=scope.container_id)
        except ChallengeContainer.DoesNotExist as exc:
            raise ValidationError('The selected container does not exist.') from exc

    def _resolve_window(self, container, scope):
        start = scope.started_at or container.started_at or container.created_at
        if scope.ended_at:
            end = scope.ended_at
        elif container.destroyed_at:
            end = min(container.destroyed_at + timedelta(seconds=5), timezone.now())
        elif container.expires_at:
            end = container.expires_at
        else:
            end = timezone.now().replace(second=0, microsecond=0) + timedelta(minutes=1)
        if end < start:
            raise ValidationError('The fact time window is invalid.')
        max_hours = int(getattr(settings, 'LEGAL_FACT_MAX_WINDOW_HOURS', 24))
        if end - start > timedelta(hours=max_hours):
            raise ValidationError(f'The fact time window cannot exceed {max_hours} hours.')
        return start, end

    def _load_events(self, container, window_start, window_end):
        limit = int(getattr(settings, 'LEGAL_FACT_MAX_EVENTS', 500))
        candidates = AuditEvent.objects.filter(
            category__in=['container', 'flag_submit'],
            user_id=container.user_id,
            created_at__gte=window_start,
            created_at__lte=window_end,
        ).order_by('created_at', 'id')[:limit * 4]
        events = []
        for event in candidates:
            safe = safe_container_event(event.detail)
            if str(safe.get('container_instance_id') or '') != str(container.id):
                continue
            events.append({'id': event.id, 'created_at': event.created_at, 'safe': safe})
            if len(events) >= limit:
                break
        return events

    def _load_submissions(self, container, window_start, window_end):
        return list(Submission.objects.filter(
            user_id=container.user_id,
            challenge_id=container.challenge_id,
            created_at__gte=window_start,
            created_at__lte=window_end,
        ).only('id', 'is_correct', 'created_at').order_by('created_at', 'id'))

    def _aggregate(self, container, events, submissions, window_start, window_end):
        actions = [item['safe'].get('action') for item in events]
        starts = [
            item['created_at'] for item in events
            if item['safe'].get('action') == 'start_succeeded'
        ]
        terminals = [
            item['created_at'] for item in events
            if item['safe'].get('action') in TERMINAL_ACTIONS
            and item['safe'].get('result') == 'success'
        ]
        runtime_seconds = None
        if starts and terminals:
            runtime_seconds = max(0, int((terminals[-1] - starts[0]).total_seconds()))
        config = next((
            item['safe'] for item in reversed(events)
            if item['safe'].get('action') == 'start_succeeded'
        ), {})
        return {
            'container_id': container.id,
            'challenge_id': container.challenge_id,
            'challenge_title': container.challenge.title,
            'container_status': container.status,
            'window_started_at': window_start.isoformat(),
            'window_ended_at': window_end.isoformat(),
            'event_count': len(events),
            'start_success_count': actions.count('start_succeeded'),
            'start_failure_count': actions.count('start_failed'),
            'stop_success_count': actions.count('stop_succeeded'),
            'stop_failure_count': actions.count('stop_failed'),
            'cleanup_observed': 'expired_cleanup' in actions,
            'runtime_seconds': runtime_seconds,
            'image': config.get('image') or container.challenge.docker_image or '',
            'network': config.get('network') or '',
            'has_cpu_limit': config.get('cpu_limit') not in (None, '', 0, '0'),
            'has_memory_limit': bool(config.get('memory_limit')),
            'flag_submission_count': len(submissions),
            'correct_submission_count': sum(1 for item in submissions if item.is_correct),
            'evidence_complete': bool(starts and terminals),
        }

    def _derive_warnings(self, facts, events):
        warnings = []
        if not facts['start_success_count']:
            warnings.append('missing_start_event')
        if facts['start_success_count'] and not facts['stop_success_count'] and not facts['cleanup_observed']:
            warnings.append('missing_terminal_event')
        if not facts['has_cpu_limit'] or not facts['has_memory_limit']:
            warnings.append('missing_resource_limit')
        if facts['start_failure_count'] or facts['stop_failure_count']:
            warnings.append('container_operation_failure')
        if any(item['safe'].get('event_schema_version') != '2' for item in events):
            warnings.append('legacy_event_schema')
        return warnings

    def _build_evidence_refs(self, events, window_start, window_end):
        event_ids = [item['id'] for item in events]
        ledger_by_event = {}
        ledgers = AuditLedgerEntry.objects.filter(
            event_category__in=['container', 'flag_submit'],
            created_at__gte=window_start,
            created_at__lte=window_end,
        ).only('id', 'payload', 'current_hash')
        for ledger in ledgers:
            event_id = (ledger.payload or {}).get('audit_event_id')
            if event_id in event_ids:
                ledger_by_event[event_id] = ledger
        return [
            {
                'audit_event_id': event_id,
                'ledger_entry_id': getattr(ledger_by_event.get(event_id), 'id', None),
                'ledger_hash': getattr(ledger_by_event.get(event_id), 'current_hash', ''),
            }
            for event_id in event_ids
        ]
