"""Django/PostgreSQL atomic repository; reuses the existing ORM/row-lock mechanism."""
import json
from dataclasses import asdict
from uuid import uuid4

from django.db import connections, transaction

from data_security.adapters.tabular.parsed_artifacts import govern_parse_result
from data_security.contracts.enums import ReasonCode
from data_security.contracts.payloads import BASELINE_LIMITS
from data_security.contracts.schema import ContractViolation

from .models import ParseAttempt, ParsedArtifact, ParseRun
from .parsing import InputError, fingerprint
from .tasks import ParseTasks, dump_run, restore_run


class DjangoRunRepository:
    def __init__(self, using='default', *, artifact_limits=BASELINE_LIMITS):
        self.using = using
        self.artifact_limits = artifact_limits
        if connections[using].vendor != 'postgresql':
            raise RuntimeError('POSTGRESQL_REQUIRED')

    def _rows(self):
        return ParseRun.objects.using(self.using)

    @staticmethod
    def _state(run):
        data = json.loads(dump_run(run))
        del data['attempts']
        return data

    def _restore(self, row):
        data = dict(row.state)
        data['attempts'] = list(ParseAttempt.objects.using(self.using)
                                .filter(run_id=row.pk).order_by('number').values_list('state', flat=True))
        return restore_run(json.dumps(data))

    def create_unique(self, candidate):
        fields = dict(zip(('domain', 'environment', 'evaluation', 'principal', 'idempotency_key'), candidate.key))
        with transaction.atomic(using=self.using):
            row, _ = self._rows().get_or_create(**fields, defaults=dict(
                id=candidate.run_id, revision=candidate.revision,
                status=candidate.status, state=self._state(candidate)))
            row = self._rows().select_for_update().get(pk=row.pk)
            return self._restore(row)

    def get(self, run_id):
        # Hold parent lock across both queries for a consistent run/attempt snapshot.
        with transaction.atomic(using=self.using):
            try:
                row = self._rows().select_for_update().get(pk=run_id)
            except ParseRun.DoesNotExist:
                raise InputError('OBJECT_NOT_FOUND') from None
            return self._restore(row)

    def compare_and_swap(self, expected_revision, replacement):
        with transaction.atomic(using=self.using):
            row = self._rows().select_for_update().get(pk=replacement.run_id)
            if row.revision != expected_revision:
                return False
            old = self._restore(row)
            # Defense in depth: repository callers cannot replace frozen identity/snapshot/history.
            immutable = ('run_id', 'key', 'request_hash', 'snapshot_json', 'max_attempts',
                         'result_kind', 'detection_status', 'scan_quality')
            if (replacement.revision != expected_revision + 1
                    or any(getattr(old, k) != getattr(replacement, k) for k in immutable)
                    or len(replacement.attempts) not in (len(old.attempts), len(old.attempts) + 1)):
                raise InputError('TASK_INPUT_INVALID')
            for prior, current in zip(old.attempts, replacement.attempts):
                if (prior.attempt_id, prior.number, prior.token) != (current.attempt_id, current.number, current.token):
                    raise InputError('STALE_ATTEMPT')
                if prior.status != 'running' and prior != current:
                    raise InputError('STALE_ATTEMPT')
            for attempt in replacement.attempts:
                ParseAttempt.objects.using(self.using).update_or_create(
                    pk=attempt.attempt_id, defaults=dict(run_id=row.pk, number=attempt.number, state=asdict(attempt)))
            row.state = self._state(replacement)
            row.status, row.revision = replacement.status, replacement.revision
            row.save(using=self.using, update_fields=['state', 'status', 'revision'])
            return True

    def pending(self, limit=100):
        return list(self._rows().filter(status='queued').order_by('id').values_list('id', flat=True)[:limit])

    def recover_expired(self, *, now, limit=100):
        ids = list(self._rows().filter(status='running').order_by('id').values_list('id', flat=True)[:limit])
        recovered = []
        for run_id in ids:
            try:
                recovered.append(ParseTasks(self).expire(str(run_id), now=now).run_id)
            except InputError as exc:
                if exc.code not in ('TASK_NOT_EXPIRED', 'TASK_VERSION_CONFLICT'):
                    raise
        return recovered  # Failed runs require explicit bounded retry; never restart a cancelled run.

    def publish(self, run_id, *, token, now, result):
        with transaction.atomic(using=self.using):
            run = self.get(run_id)
            snapshot = json.loads(run.snapshot_json)
            if (result.asset_version_id != snapshot['asset']['version_id']
                    or result.input_content_hash != snapshot['asset']['content_hash']):
                raise InputError('ASSET_VERSION_MISMATCH')
            if (result.parser_version != snapshot['parser_version']
                    or result.config_hash != fingerprint(dict(parser=snapshot['config'], limits=snapshot['limits'],
                                                              unicode_version=snapshot['unicode_version']))
                    or snapshot['scope'] is not None and result.scope_hash != fingerprint(snapshot['scope'])):
                raise InputError('CONFIG_INVALID')
            artifact_id = uuid4()
            final = ParseTasks(self).finish(run_id, token=token, now=now, parsed_ref=f'private:{artifact_id}')
            if final.status == 'succeeded':
                if snapshot['asset']['byte_size'] > self.artifact_limits.max_bytes:
                    raise InputError('RESOURCE_LIMIT')
                try:
                    payload = govern_parse_result(result, limits=self.artifact_limits).tree.to_value()
                except ContractViolation as exc:
                    code = {ReasonCode.LIMIT_EXCEEDED: 'RESOURCE_LIMIT',
                            ReasonCode.UNKNOWN_SCHEMA: 'CONFIG_UNSUPPORTED',
                            ReasonCode.INVALID_COORDINATE: 'LOCATION_MISMATCH',
                            ReasonCode.UNSUPPORTED_FORMAT: 'UNSUPPORTED_FORMAT'}.get(exc.code, 'PARSE_FAILED')
                    raise InputError(code) from None
                ParsedArtifact.objects.using(self.using).create(
                    id=artifact_id, run_id=run_id, attempt_id=final.attempts[-1].attempt_id, payload=payload)
            return final  # Artifact creation failure rolls back success, revision and attempt together.
