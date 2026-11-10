"""Database-free executor retained-key/gate wiring; no publication or restore claim."""
import asyncio
from contextlib import nullcontext
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
from uuid import uuid4
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import AsyncMock, Mock, patch

from django.test import override_settings
from controlled_export_service.security_bootstrap import (
    assemble_recovery, guard_private_upload_asgi, private_upload_middleware, start_application,
)
from data_security.adapters.django.recovery_ingress import bind_recovery_admission
from controlled_export.errors import ArtifactIntegrityError
from controlled_export.models import ExecutionAttempt, ExportExecution, OutboxEvent, ProtectedArtifact
from controlled_export.services import inspect_private_preparation
from data_security.adapters.persistence.backup import PostgresAgeBackup
from data_security.adapters.persistence.executor_recovery import DjangoExecutorRecoveryVerifier
from data_security.adapters.persistence.models import PrivateFileOperation, PrivateObject
from data_security.contracts import (
    BASELINE_LIMITS, ContractViolation, Environment, KeyPurpose, KeyReference, KeyStatus, ObjectContext,
    ProtectionContext, Purpose, ReasonCode, SecretMaterial, StoredObject,
)
from data_security.tests.fixtures import examples


class ExecutorRecoveryWiringTests(TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix='b3-executor-recovery-')
        self.addCleanup(temporary.cleanup)
        self.addCleanup(bind_recovery_admission)
        self.root = Path(temporary.name)
        self.path = self.root / 'config.json'
        self.active = KeyReference(schema_version=KeyReference.SCHEMA, key_ref='enc-data/v2',
            version='v2', purpose=KeyPurpose.DATA, status=KeyStatus.ACTIVE)
        self.old = replace(self.active, key_ref='enc-data/v1', version='v1', status=KeyStatus.READ_ONLY)
        self.config = {'schema_version': 'ds.executor-preparation.v2', 'environment': 'evaluation',
            'key_manifest': str(self.root / 'manifest.json'), 'data_key': self.active.to_wire(),
            'retained_data_keys': [self.old.to_wire()], 'recovery_target_identity': 'a' * 64,
            'private_root': str(self.root), 'project_ref': 'ctf', 'limits': BASELINE_LIMITS.to_wire()}
        self.enterContext(override_settings(CONTROLLED_EXPORT_PRIVATE_CONFIG=str(self.path),
            CONTROLLED_EXPORT_ENVIRONMENT='evaluation', SECRET_KEY='b3-synthetic-framework-key',
            CONTROLLED_EXPORT_INTERNAL_KEY='b3-synthetic-internal', EXECUTION_AUTHORITY_HMAC_SECRET='b3-synthetic-authority',
            CONTROLLED_EXPORT_PRIVATE_PREPARATION=None, CONTROLLED_EXPORT_PRIVATE_MODE=True))
        self.keys = self.enterContext(patch('data_security.adapters.keys.FileKeyResolver')).return_value
        self.keys.resolve.side_effect = lambda ref, purpose, identity: SecretMaterial(
            b'a' * 32 if ref == self.active else b'b' * 32, purpose)
        self.crypto = self.enterContext(patch('data_security.application.crypto_service.CryptoService'))
        self.prepare = self.enterContext(patch('controlled_export_service.security_bootstrap.assemble_private_preparation',
            return_value={'limits': BASELINE_LIMITS}))

    def configure(self):
        self.path.write_text(json.dumps(self.config))
        self.path.chmod(0o600)
        start_application()

    def test_explicit_retained_keys_are_injected_without_changing_active_write_key(self):
        self.configure()
        self.assertEqual(self.crypto.call_args.kwargs['retained_data_keys'], (self.old,))
        self.assertEqual(self.prepare.call_args.kwargs['data_key'], self.active)
        self.assertEqual(self.keys.resolve.call_args_list[1].args, (self.old, KeyPurpose.DATA, 'service/security'))

    def test_v1_configuration_still_has_no_retained_keys_or_recovery_opt_in(self):
        self.config['schema_version'] = 'ds.executor-preparation.v1'
        del self.config['retained_data_keys'], self.config['recovery_target_identity']
        self.configure()
        self.assertEqual(self.crypto.call_args.kwargs['retained_data_keys'], ())
        self.assertEqual(self.keys.resolve.call_count, 1)

    def test_active_old_key_is_rejected_before_preparation_binding(self):
        self.config['retained_data_keys'] = [replace(self.old, status=KeyStatus.ACTIVE).to_wire()]
        with self.assertRaises(ContractViolation):
            self.configure()
        self.prepare.assert_not_called()

    def test_deployment_gate_blocks_all_asgi_routes_before_body_or_owner(self):
        bind_recovery_admission(lambda: False)
        downstream, receive = AsyncMock(), AsyncMock(side_effect=AssertionError('body was read'))
        gate = guard_private_upload_asgi(downstream)
        for path in ('/health/', '/api/controlled-export/executions/', '/api/controlled-export/shares/1', '/anything'):
            sent = []
            async def send(message):
                sent.append(message)
            asyncio.run(gate({'type': 'http', 'path': path, 'method': 'POST'}, receive, send))
            self.assertEqual(sent[0]['status'], 503)
        receive.assert_not_called()
        downstream.assert_not_called()

    def test_wsgi_gate_precedes_legacy_and_preparation_owners(self):
        bind_recovery_admission(lambda: False)
        downstream = Mock()
        response = private_upload_middleware(downstream)(SimpleNamespace(path='/health/'))
        self.assertEqual(response.status_code, 503)
        downstream.assert_not_called()


class ExecutorRecoveryInspectionTests(TestCase):
    """Unsaved ORM rows; no assertion here claims a database restore or durable receipt."""
    def setUp(self):
        self.now = datetime(2026, 11, 8, tzinfo=timezone.utc)
        self.execution = ExportExecution(execution_id=uuid4(), state='prepared', environment='evaluation',
            valid_until=self.now - timedelta(seconds=1), scope_hash='a' * 64, plan_hash='b' * 64)
        self.attempt = ExecutionAttempt(attempt_id=uuid4(), execution=self.execution, status='prepared')
        self.context = ObjectContext(schema_version=ObjectContext.SCHEMA, project_ref='ctf', environment=Environment.EVALUATION,
            object_uuid=str(self.attempt.attempt_id), object_version='1', field_ref='controlled-export/output',
            authorization_ref='execution/' + str(self.execution.execution_id))
        self.stored = StoredObject(schema_version=StoredObject.SCHEMA, object_ref='private/' + '1' * 64,
            version='1', ciphertext_hash='2' * 64, size_bytes=40, state='verified')
        self.input_hash = hashlib.sha256(b'output').hexdigest()
        self.operation = PrivateFileOperation(operation_ref='executor-preparation/' + str(self.attempt.attempt_id),
            actor_ref='service/controlled-export', scope_ref='controlled-export/preparations', state='prepared',
            object_uuid=self.attempt.attempt_id, field_refs=['controlled-export/output'], request_hash=self.input_hash,
            files={'controlled-export/output': {'context': self.context.to_wire(), 'stored': self.stored.to_wire(),
                'input_hash': self.input_hash}}, legacy_sources={})
        self.attempt.private_candidate = {'schema_version': 'controlled-export.private-candidate.v1',
            'context': self.context.to_wire(), 'stored': self.stored.to_wire(), 'output_content_hash': self.input_hash,
            'scope_hash': self.execution.scope_hash, 'plan_hash': self.execution.plan_hash}
        self.store = Mock(environment=Environment.EVALUATION)
        self.store.inspect_recovery.return_value = SimpleNamespace(key=SimpleNamespace(key_ref='enc-data/v1'))
        self.store.crypto.open.return_value = SimpleNamespace(binary=b'output')
        self.backup = Mock(database={'host': '127.0.0.1', 'dbname': 'b3_executor', 'port': 5432})
        self.verifier = DjangoExecutorRecoveryVerifier(store=self.store, inspect_attempt=inspect_private_preparation,
            backup=self.backup, project_ref='ctf', limits=BASELINE_LIMITS, clock=lambda: self.now)
        self.rows = {PrivateObject: [PrivateObject(object_ref=self.stored.object_ref, state='verified')],
            PrivateFileOperation: [self.operation], ExportExecution: [self.execution], ExecutionAttempt: [self.attempt],
            OutboxEvent: [OutboxEvent(event_type='synthetic')]}
        self.enterContext(patch.object(self.verifier, '_rows', side_effect=lambda query: iter(self.rows.get(query.model, ()))))

    def test_original_owner_context_and_uuid_field_are_inspected_without_promotion(self):
        document = json.dumps(self.attempt.private_candidate, sort_keys=True)
        result = self.verifier._inspect()
        self.assertTrue(result['opening_allowed'])
        self.assertEqual(result['private_objects_opened'], 1)
        self.assertEqual(result['expired_executions'], 1)
        self.assertEqual(result['historical_outbox_records'], 1)
        self.assertFalse(result['outbox_authenticated_as_v2'])
        self.assertEqual((self.execution.state, self.attempt.status, self.operation.state), ('prepared',) * 3)
        self.assertEqual(json.dumps(self.attempt.private_candidate, sort_keys=True), document)
        self.store.recover_candidate.assert_not_called()
        self.store.publish.assert_not_called()

    def test_unknown_partial_intention_remains_pending_and_unregistered(self):
        self.operation.state = 'preparing'
        self.attempt.status = 'unknown'
        del self.attempt.private_candidate['stored']
        self.rows[PrivateObject] = []
        result = self.verifier._inspect()
        self.assertGreater(result['pending_records'], 0)
        self.assertEqual(result['attempts'], {'unknown': 1})
        self.store.inspect_recovery.assert_not_called()
        self.store.recover_candidate.assert_not_called()

    def test_prepared_missing_ciphertext_and_changed_output_are_rejected(self):
        for defect in ('missing_registration', 'changed_output'):
            with self.subTest(defect=defect):
                self.rows[PrivateObject] = [] if defect == 'missing_registration' else [
                    PrivateObject(object_ref=self.stored.object_ref, state='verified')]
                self.store.crypto.open.return_value = SimpleNamespace(binary=b'changed')
                with self.assertRaises(ContractViolation):
                    self.verifier._inspect()

    def test_legacy_artifact_stays_closed_without_claiming_file_recovery(self):
        self.rows[ProtectedArtifact] = [ProtectedArtifact(private_storage_ref='old/output.csv')]
        result = self.verifier._inspect()
        self.assertFalse(result['opening_allowed'])
        self.assertEqual(result['legacy_files_not_in_private_bundle'], 1)
        self.assertFalse(result['key_retirement_allowed'])

    def test_original_owner_rejects_other_execution_and_changed_context(self):
        for defect in ('other_execution', 'changed_context'):
            with self.subTest(defect=defect):
                self.attempt.execution_id = uuid4() if defect == 'other_execution' else self.execution.execution_id
                self.attempt.private_candidate['context']['authorization_ref'] = 'execution/other'
                with self.assertRaises(ArtifactIntegrityError):
                    inspect_private_preparation(execution=self.execution, attempt=self.attempt, private_project_ref='ctf')

    def test_read_only_transaction_is_required_before_owner_inspection(self):
        context = replace(examples()[ProtectionContext], environment=Environment.EVALUATION, purpose=Purpose.STORAGE)
        with patch('data_security.adapters.persistence.executor_recovery.connection') as connection, \
             patch('data_security.adapters.persistence.executor_recovery.transaction.atomic', side_effect=nullcontext), \
             patch.object(self.verifier, '_inspect', return_value={'complete': True}) as inspect:
            connection.vendor, connection.in_atomic_block = 'postgresql', False
            connection.get_autocommit.return_value = True
            connection.settings_dict = {'HOST': '127.0.0.1', 'NAME': 'b3_executor', 'PORT': 5432}
            self.assertEqual(self.verifier(context), {'complete': True})
            connection.cursor.return_value.__enter__.return_value.execute.assert_called_once_with(
                'SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
            inspect.reset_mock()
            connection.settings_dict['NAME'] = 'other'
            self.assertEqual(self.verifier(context).code, ReasonCode.SOURCE_NOT_APPROVED)
            inspect.assert_not_called()

    def test_offline_factory_does_not_inspect_tables_or_enable_preparation(self):
        # Constructor validation belongs to BackupPort tests; this isolates lazy B wiring.
        backup = object.__new__(PostgresAgeBackup)
        with TemporaryDirectory(prefix='b3-executor-offline-') as directory:
            backup.full_inventory, backup.identity_ref, backup.environment = True, object(), Environment.EVALUATION
            backup.limits, backup.private_root, backup.source_identity = BASELINE_LIMITS, Path(directory), 'a' * 64
            backup.code_version, backup.domain, backup.service_identity = 'b3', 'ctf', 'service/security'
            backup.clock = lambda: self.now
            with override_settings(CONTROLLED_EXPORT_ENVIRONMENT='evaluation'), \
                 patch.object(DjangoExecutorRecoveryVerifier, '__call__', side_effect=AssertionError('eager inspection')):
                flow = assemble_recovery(backups=backup, crypto=self.store.crypto, project_ref='ctf', limits=BASELINE_LIMITS)
            self.assertIs(flow.backups, backup)
            self.assertFalse(any(Path(directory).iterdir()))
