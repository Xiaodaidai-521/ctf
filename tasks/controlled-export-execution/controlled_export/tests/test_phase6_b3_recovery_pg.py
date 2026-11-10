"""Dispatch-only PostgreSQL executor inspection; not a backup or delivery acceptance claim."""
from dataclasses import replace
import hashlib
import json
import secrets
from pathlib import Path
from unittest.mock import patch

from django.db import DatabaseError, connection
from django.test import TransactionTestCase
from django.test.utils import CaptureQueriesContext

from controlled_export.models import DeliveryAttempt, ExecutionAttempt, ExportExecution, OutboxEvent, ProtectedArtifact, ShareGrant
from controlled_export.services import inspect_private_preparation
from data_security.adapters.keys import FileKeyResolver
from data_security.adapters.persistence.backup import PostgresAgeBackup
from data_security.adapters.persistence.executor_recovery import DjangoExecutorRecoveryVerifier
from data_security.adapters.persistence.models import PrivateFileOperation, PrivateObject
from data_security.adapters.persistence.private_store import DjangoPrivateStore
from data_security.application.crypto_service import CryptoService
from data_security.contracts import BASELINE_LIMITS, Environment, ProtectionContext, ProtectionError, Purpose, KeyReference
from data_security.tests.fixtures import examples
from . import test_phase6_b2_http as b2


class ExecutorRestoredPreparationTests(TransactionTestCase):
    execute = b2.ExecutorPrivateHTTPTests.execute
    assert_no_delivery = b2.ExecutorPrivateHTTPTests.assert_no_delivery

    def setUp(self):
        b2.ExecutorPrivateHTTPTests.setUp(self)
        key = KeyReference.from_wire(self.config['data_key'])
        resolver = FileKeyResolver(manifest_path=self.config['key_manifest'], environment=Environment.EVALUATION,
            repository_root=Path(__file__).resolve().parents[4])
        crypto = CryptoService(keys=resolver, service_identity='service/security', random_bytes=secrets.token_bytes,
            environment=Environment.EVALUATION, limits=BASELINE_LIMITS)
        self.store = DjangoPrivateStore(root=self.root, crypto=crypto, environment=Environment.EVALUATION)
        # No backup is performed here; use the original adapter's scope check and selected DB identity.
        backup = object.__new__(PostgresAgeBackup)
        backup.service_identity, backup.environment, backup.domain = 'service/security', Environment.EVALUATION, 'ctf'
        settings = connection.settings_dict
        backup.database = {'dbname': settings['NAME'], 'host': settings['HOST'], 'port': settings['PORT'] or 5432}
        from django.utils import timezone
        self.verifier = DjangoExecutorRecoveryVerifier(store=self.store, inspect_attempt=inspect_private_preparation,
            backup=backup, project_ref=self.config['project_ref'], limits=BASELINE_LIMITS, clock=timezone.now)
        self.context = replace(examples()[ProtectionContext], actor_ref='service/security', environment=Environment.EVALUATION,
            domain='ctf', purpose=Purpose.STORAGE)
        self.assertEqual(crypto.keys.resolve(key, key.purpose, 'service/security').borrow(key.purpose).nbytes, 32)

    def fingerprint(self):
        rows = {model._meta.label: list(model.objects.order_by('pk').values()) for model in (
            ExportExecution, ExecutionAttempt, PrivateFileOperation, PrivateObject, ProtectedArtifact,
            ShareGrant, DeliveryAttempt, OutboxEvent)}
        return hashlib.sha256(json.dumps(rows, default=str, sort_keys=True).encode()).hexdigest()

    def test_prepared_ciphertext_and_original_intention_are_inspected_without_writes(self):
        self.assertEqual(self.execute().status_code, 201)
        before = self.fingerprint()
        with CaptureQueriesContext(connection) as queries:
            result = self.verifier(self.context)
        self.assertNotIsInstance(result, ProtectionError)
        self.assertEqual(result['private_objects_opened'], 1)
        self.assertEqual(result['attempts'], {'prepared': 1})
        self.assertEqual(result['scope'], 'executor-preparation-only')
        self.assertFalse(result['outbox_authenticated_as_v2'])
        self.assertEqual(before, self.fingerprint())
        statements = [item['sql'].strip().upper() for item in queries]
        self.assertTrue(any('REPEATABLE READ, READ ONLY' in value for value in statements))
        self.assertFalse(any(value.startswith(('INSERT ', 'UPDATE ', 'DELETE ')) or 'FOR UPDATE' in value for value in statements))
        self.assert_no_delivery()

    def test_unknown_registration_loss_remains_unknown_without_adoption(self):
        with patch.object(PrivateObject.objects, 'get_or_create', side_effect=DatabaseError('synthetic registration loss')):
            response = self.execute()
        self.assertEqual(response.status_code, 409)
        before = self.fingerprint()
        files = {path.name: path.read_bytes() for path in self.root.glob('*.sealed')}
        result = self.verifier(self.context)
        self.assertNotIsInstance(result, ProtectionError)
        self.assertEqual(result['attempts'], {'unknown': 1})
        self.assertGreater(result['pending_records'], 0)
        self.assertEqual(before, self.fingerprint())
        self.assertEqual(files, {path.name: path.read_bytes() for path in self.root.glob('*.sealed')})
        self.assertFalse(PrivateObject.objects.exists())
        self.assert_no_delivery()

    def test_damaged_ciphertext_fails_without_reconciliation_or_cleanup(self):
        self.assertEqual(self.execute().status_code, 201)
        path = next(self.root.glob('*.sealed'))
        path.write_bytes(path.read_bytes()[:-1])
        before = self.fingerprint()
        self.assertIsInstance(self.verifier(self.context), ProtectionError)
        self.assertEqual(before, self.fingerprint())
        self.assertTrue(path.exists())
        self.assert_no_delivery()

    def test_changed_owner_context_fails_without_rebinding_the_attempt(self):
        self.assertEqual(self.execute().status_code, 201)
        attempt = ExecutionAttempt.objects.get()
        attempt.private_candidate['context']['authorization_ref'] = 'execution/other'
        attempt.save(update_fields=['private_candidate'])
        before = self.fingerprint()
        self.assertIsInstance(self.verifier(self.context), ProtectionError)
        self.assertEqual(before, self.fingerprint())
        self.assert_no_delivery()
