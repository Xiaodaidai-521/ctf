"""Database-free inspection checks; PostgreSQL snapshot semantics need separate execution."""
from contextlib import ExitStack, nullcontext
from dataclasses import replace
import hashlib
from uuid import UUID
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from audit.legacy_archives import LegacyArchiveOwner
from ctf_backend.security_bootstrap import assemble_recovery
from data_security.adapters.persistence.models import PrivateFileOperation, PrivateObject
from data_security.adapters.persistence.private_store import DjangoPrivateStore
from feedback_center.models import FeedbackAttachment
from resources.models import Resource
from users.models import CTFUser
from data_security.adapters.persistence.recovery_verifier import DjangoRecoveryVerifier
from data_security.contracts import (
    BASELINE_LIMITS, ContractViolation, Environment, KeyPurpose, KeyReference, KeyStatus, ObjectContext,
    ProtectionContext, Purpose, ReasonCode, StoredObject, content_hash,
)
from data_security.tests.fixtures import examples


class PrivateRecoveryInspectionTests(TestCase):
    def setUp(self):
        directory = TemporaryDirectory(prefix='b3-inspection-')
        self.addCleanup(directory.cleanup)
        self.context = examples()[ObjectContext]
        self.store = DjangoPrivateStore(root=Path(directory.name), crypto=Mock(), environment=Environment.TEST)
        self.stored = StoredObject(schema_version=StoredObject.SCHEMA, object_ref='private/' + '1' * 64,
            version=self.context.object_version, ciphertext_hash='2' * 64, size_bytes=40, state='verified')
        self.row = Mock(version=self.stored.version, ciphertext_hash=self.stored.ciphertext_hash, size_bytes=40,
            object_ref=self.stored.object_ref, state='verified', context_hash=content_hash(dict(
                project=self.context.project_ref, environment=self.context.environment, object_uuid=self.context.object_uuid,
                version=self.context.object_version, field=self.context.field_ref)))
        stack = self.enterContext(ExitStack())
        stack.enter_context(patch('data_security.adapters.persistence.private_store.transaction.atomic', side_effect=nullcontext))
        self.manager = stack.enter_context(patch('data_security.adapters.persistence.private_store.PrivateObject.objects'))
        self.manager.get.return_value = self.row
        self.read_file = stack.enter_context(patch.object(self.store, '_read_file'))

    def test_live_inspection_never_verifies_publishes_or_registers(self):
        for state in ('candidate', 'verified', 'published'):
            with self.subTest(state=state):
                self.row.state = state
                self.assertIs(self.store.inspect_recovery(self.stored, self.context), self.read_file.return_value)
                self.assertEqual(self.row.state, state)
        self.row.save.assert_not_called()
        self.manager.get_or_create.assert_not_called()
        self.manager.select_for_update.assert_not_called()
        self.store.crypto.open.assert_not_called()

    def test_retired_identity_is_checked_without_requiring_deleted_bytes(self):
        self.row.state = 'retired'
        self.assertIsNone(self.store.inspect_recovery(self.stored, self.context))
        self.row.context_hash = '3' * 64
        self.assertEqual(self.store.inspect_recovery(self.stored, self.context).code, ReasonCode.HASH_MISMATCH)
        self.read_file.assert_not_called()
        self.row.save.assert_not_called()

    def test_retired_inspection_does_not_enable_online_reads(self):
        self.row.state = 'retired'
        self.assertEqual(self.store.read(self.stored, self.context).code, ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(self.store.open_verified_source(self.stored, self.context).code, ReasonCode.AUTHORIZATION_DENIED)
        self.read_file.assert_not_called()


class RecoveryVerifierBoundaryTests(TestCase):
    def setUp(self):
        self.context = replace(examples()[ProtectionContext], actor_ref='service/security', domain='ctf', purpose=Purpose.STORAGE)
        self.verifier = DjangoRecoveryVerifier(store=Mock(environment=Environment.TEST), owners={}, audit=Mock(),
            reports=Mock(), verify_report=Mock(), field_storage=None, field_models=(), inspect_share=Mock(),
            limits=BASELINE_LIMITS, clock=Mock(), database={'host': '127.0.0.1', 'port': 5432, 'dbname': 'b3_target'})
        stack = self.enterContext(ExitStack())
        self.connection = stack.enter_context(patch('data_security.adapters.persistence.recovery_verifier.connection'))
        self.connection.vendor, self.connection.in_atomic_block = 'postgresql', False
        self.connection.get_autocommit.return_value = True
        self.connection.settings_dict = {'HOST': '127.0.0.1', 'PORT': '5432', 'NAME': 'b3_target'}
        self.atomic = stack.enter_context(patch('data_security.adapters.persistence.recovery_verifier.transaction.atomic',
                                               side_effect=nullcontext))
        self.inspect = stack.enter_context(patch.object(self.verifier, '_inspect', return_value={'complete': True}))

    def test_read_only_repeatable_read_precedes_owner_inspection(self):
        self.assertEqual(self.verifier(self.context), {'complete': True})
        self.connection.cursor.return_value.__enter__.return_value.execute.assert_called_once_with(
            'SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        self.inspect.assert_called_once_with(self.context)

    def test_wrong_database_outer_transaction_and_non_pg_fail_before_inspection(self):
        for target in ('different_database', 'outer_transaction', 'sqlite'):
            with self.subTest(target=target):
                self.connection.settings_dict['NAME'] = 'other' if target == 'different_database' else 'b3_target'
                self.connection.in_atomic_block = target == 'outer_transaction'
                self.connection.vendor = 'sqlite' if target == 'sqlite' else 'postgresql'
                self.assertEqual(self.verifier(self.context).code, ReasonCode.SOURCE_NOT_APPROVED)
        self.inspect.assert_not_called()
        self.atomic.assert_not_called()

    def test_scope_limits_are_enforced_before_iteration(self):
        query = Mock()
        query.count.return_value = BASELINE_LIMITS.max_actions + 1
        with self.assertRaises(ValueError):
            self.verifier._rows(query)
        query.iterator.assert_not_called()


class RetainedOwnerLifecycleTests(TestCase):
    """Unsaved ORM rows exercise verifier logic, not PostgreSQL or owner authentication."""
    def setUp(self):
        self.context = replace(examples()[ProtectionContext], domain='ctf')
        self.object_context = replace(examples()[ObjectContext], project_ref='ctf', field_ref='resources/file')
        self.stored = StoredObject(schema_version=StoredObject.SCHEMA, object_ref='private/' + '1' * 64,
            version=self.object_context.object_version, ciphertext_hash='2' * 64, size_bytes=40, state='verified')
        self.operation = PrivateFileOperation(operation_ref='resource-upload/test', state='cleaned', result_ref='7',
            object_uuid=UUID(self.object_context.object_uuid), field_refs=['resources/file'], legacy_sources={})
        self.resource = Resource(pk=7, private_files={'operation_ref': self.operation.operation_ref})
        self.object = PrivateObject(object_ref=self.stored.object_ref, state='retired')
        self.store = Mock(environment=Environment.TEST)
        self.store.inspect_recovery.return_value = None
        self.owners = {'resources': Mock(project_ref='ctf'), 'feedback': Mock(project_ref='ctf')}
        self.audit = Mock(checkpoint_ref='selected')
        self.audit.inspect_recovery.return_value = {'events': {}, 'key_refs': ['audit/v1'], 'tail': Mock(sequence=1),
            'checkpoint': SimpleNamespace(receipt=SimpleNamespace(sequence=1))}
        self.verifier = DjangoRecoveryVerifier(store=self.store, owners=self.owners, audit=self.audit,
            reports=Mock(), verify_report=Mock(), field_storage=None, field_models=(), inspect_share=Mock(),
            limits=BASELINE_LIMITS, clock=Mock(), database={})
        self.rows = {PrivateObject: [self.object], PrivateFileOperation: [self.operation], Resource: [self.resource]}
        self.enterContext(patch.object(self.verifier, '_rows', side_effect=lambda query: iter(self.rows.get(query.model, ()))))
        self.enterContext(patch.object(self.verifier, '_legacy_audit', return_value={'state': 'historical-v1'}))
        self.bind_references()

    def bind_references(self):
        self.operation.field_refs = [self.object_context.field_ref]
        self.operation.files = {self.object_context.field_ref: {'context': self.object_context.to_wire(),
            'stored': replace(self.stored, state='candidate').to_wire(), 'input_hash': hashlib.sha256(b'file').hexdigest()}}
        self.owners['resources'].inspect_recovery.return_value = (('file', self.object_context, self.stored),)
        self.owners['feedback'].inspect_recovery.return_value = self.object_context, self.stored

    def test_cleaned_resource_keeps_authenticated_reference_without_deleted_bytes(self):
        result = self.verifier._inspect(self.context)
        self.assertEqual((result['terminal_operations'], result['pending_records'], result['retired_objects']), (1, 0, 1))
        self.assertEqual(result['private_objects_opened'], 0)
        self.assertEqual(result['governance'], {})
        self.store.crypto.open.assert_not_called()

    def test_cleaned_feedback_keeps_authenticated_reference_without_deleted_bytes(self):
        self.object_context = replace(self.object_context, field_ref='feedback/attachment')
        self.operation.result_ref = self.object_context.object_uuid
        self.rows[Resource] = []
        self.rows[FeedbackAttachment] = [FeedbackAttachment(attachment_id=UUID(self.object_context.object_uuid),
            private_file={'operation_ref': self.operation.operation_ref})]
        self.bind_references()
        self.assertEqual(self.verifier._inspect(self.context)['terminal_operations'], 1)
        self.store.crypto.open.assert_not_called()

    def test_live_operation_accepts_uuid_field_and_opens_original_bytes(self):
        self.operation.state, self.object.state = 'committed', 'published'
        self.store.inspect_recovery.return_value = SimpleNamespace(key=SimpleNamespace(key_ref='data-key/v1'))
        self.store.crypto.open.return_value = SimpleNamespace(binary=b'file')
        result = self.verifier._inspect(self.context)
        self.assertEqual(result['private_objects_opened'], 1)
        self.assertEqual(result['data_key_refs'], ['data-key/v1'])
        self.assertEqual(result['terminal_operations'], 0)

    def test_field_read_checks_index_minimization_and_ciphertext_only_storage(self):
        field = SimpleNamespace(security_state='sealed-v1', encrypted_fields=('email',), minimized_fields={'raw': ''},
            raw='', email='', email_index='v1:synthetic', email_index_previous='',
            security_envelopes={'email': {'envelope': {'key': {'key_ref': 'enc-data/v1'}}}})
        storage = Mock(index_keys=(SimpleNamespace(key_ref='query-index/v1'),))
        storage.read.return_value = 'synthetic@example.invalid'
        storage.email_indexes.return_value = ('v1:synthetic', '')
        self.verifier.field_models, self.verifier.field_storage = (CTFUser,), storage
        self.rows[CTFUser] = [field]
        result = self.verifier._inspect(self.context)
        self.assertEqual(result['index_key_refs'], ['query-index/v1'])
        self.assertEqual(result['encrypted_fields_opened'], 1)
        for name in ('raw', 'email', 'email_index'):
            with self.subTest(name=name):
                old = getattr(field, name)
                setattr(field, name, 'changed')
                with self.assertRaises(ContractViolation):
                    self.verifier._inspect(self.context)
                setattr(field, name, old)

    def test_original_project_namespace_is_not_replaced_with_deployment_domain(self):
        self.object_context = replace(self.object_context, project_ref='ctf/evaluation')
        self.owners['resources'].project_ref = 'ctf/evaluation'
        self.bind_references()
        self.assertTrue(self.verifier._inspect(self.context)['complete'])
        self.owners['resources'].project_ref = 'different-project'
        with self.assertRaises(ContractViolation):
            self.verifier._inspect(self.context)

    def test_missing_bytes_require_exact_terminal_owner_binding(self):
        for defect in ('committed', 'aborted', 'wrong_result', 'missing_operation'):
            with self.subTest(defect=defect):
                self.operation.state = defect if defect in ('committed', 'aborted') else 'cleaned'
                self.operation.result_ref = '8' if defect == 'wrong_result' else '7'
                self.resource.private_files = {} if defect == 'missing_operation' else {
                    'operation_ref': self.operation.operation_ref}
                if defect == 'missing_operation':
                    self.resource.private_files = {'schema_version': 'resource.private-upload.v1'}
                with self.assertRaises(ContractViolation):
                    self.verifier._inspect(self.context)

    def test_another_retained_object_does_not_satisfy_cleaned_owner_binding(self):
        different = replace(self.stored, object_ref='private/' + '3' * 64)
        self.owners['resources'].inspect_recovery.return_value = (('file', self.object_context, different),)
        with self.assertRaises(ContractViolation) as error:
            self.verifier._inspect(self.context)
        self.assertEqual(error.exception.code, ReasonCode.REPORT_MISMATCH)


class RecoveryCompositionTests(TestCase):
    def test_offline_factory_does_not_assemble_online_owners_or_touch_tables(self):
        identity = KeyReference(schema_version=KeyReference.SCHEMA, key_ref='backup-identity/v1',
            purpose=KeyPurpose.BACKUP_PRIVATE, version='v1', status=KeyStatus.READ_ONLY)
        with TemporaryDirectory(prefix='b3-offline-factory-') as directory:
            backup = Mock(full_inventory=True, private_root=Path(directory), source_identity='1' * 64, code_version='b3')
            with patch('ctf_backend.security_bootstrap._configuration', return_value=({}, object())), \
                 patch('ctf_backend.security_bootstrap._backup_adapter', return_value=backup) as adapter, \
                 patch('ctf_backend.security_bootstrap.assemble', side_effect=AssertionError('online assembly before restore')):
                flow = assemble_recovery(config_path='/synthetic/target.json', identity=identity)
                self.assertIs(flow.backups, backup)
                self.assertEqual(adapter.call_args.kwargs['identity_ref'], identity)
                self.assertFalse(any(Path(directory).iterdir()))

    def test_maintenance_factory_preserves_explicit_project_namespace(self):
        from ctf_backend.security_bootstrap import assemble_private_maintenance

        components = {'audit': Mock()}
        with patch('ctf_backend.security_bootstrap.assemble', return_value=components), \
             patch('ctf_backend.security_bootstrap._private_upload_owners') as owners:
            result = assemble_private_maintenance(config_path='/synthetic/source.json',
                private_root='/synthetic/private', project_ref='ctf/evaluation', legacy_root='/synthetic/legacy')
        self.assertIs(result, owners.return_value)
        owners.assert_called_once_with(components, private_root='/synthetic/private', project_ref='ctf/evaluation',
            legacy_root='/synthetic/legacy', verify_recovery=None)

    def test_audit_quarantine_and_delete_dispatch_to_original_governance_owner(self):
        actor = Mock(pk=7, role='admin', is_authenticated=True)
        actor.has_perm.return_value = True
        govern, reconcile = Mock(), Mock()
        owner = LegacyArchiveOwner(capture=Mock(), reconcile=reconcile, govern=govern, identity=Mock(),
            environment=Environment.TEST, domain='ctf')
        with patch('audit.legacy_archives.CTFUser.objects.filter') as users, \
             patch('audit.legacy_archives.connection') as connection:
            users.return_value.first.return_value = actor
            connection.in_atomic_block = False
            connection.get_autocommit.return_value = True
            for operation in ('quarantine', 'delete'):
                self.assertIs(owner.run(user=actor, operation=operation, archive_ref='audit/archive/' + 'a' * 32),
                              govern.return_value)
                self.assertEqual(govern.call_args.kwargs['operation'], operation)
        reconcile.assert_not_called()
