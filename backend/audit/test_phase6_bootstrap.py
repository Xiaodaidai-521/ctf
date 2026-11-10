"""Explicit evaluation-only B wiring, with real file keys and PostgreSQL audit."""
from dataclasses import replace
import json
from pathlib import Path
import secrets

from django.db import connection
from django.test import TransactionTestCase

from ctf_backend.security_bootstrap import assemble
from data_security.contracts import (
    AuditReceipt, ContractViolation, Durability, KeyStatus, ObjectContext, ProtectionError,
    QuotaRecoveryEvent, ReasonCode, SecurityEvent, SecurityEventV2,
)
from data_security.tests.fixtures import examples
from data_security.tests.phase3_fixtures import configuration

from .models import AuditLedgerEntry, AuthenticatedAuditEntry, SecurityAuditRecord


class AuthenticatedBootstrapTests(TransactionTestCase):
    def setUp(self):
        self.assertEqual(connection.vendor, 'postgresql')
        files = configuration(providers=())
        self.path, self.config, self.refs, _, self.binding = files.__enter__()
        self.addCleanup(files.__exit__, None, None, None)
        root = self.path.parent / 'checkpoints'
        root.mkdir(mode=0o700)
        root.chmod(0o700)
        context = examples()[ObjectContext]
        self.options = dict(chain_version='ds.audit.v2', project_ref=context.project_ref,
            object_uuid=context.object_uuid, object_version=context.object_version,
            authorization_ref='authorization/synthetic-audit-owner', retained_keys=[],
            checkpoint_root=str(root), checkpoint_ref=None)
        self.config.update(schema_version='ds.bootstrap.v2',
            policy_repository={'kind': 'file', 'writable': False}, audit_chain=self.options)
        self.event = examples()[SecurityEventV2]

    def build(self):
        self.path.write_text(json.dumps(self.config))
        return assemble(config_path=self.path)

    def test_explicit_configuration_shares_one_gateway_and_accepts_both_new_schemas(self):
        components = self.build()
        gateway = components['audit']
        self.assertIs(components['catalog'].audit, gateway)
        self.assertIs(components['protection'].audit, gateway)
        first = gateway.record(self.event, Durability.LEDGER_CONFIRMED)
        second = gateway.record(examples()[QuotaRecoveryEvent], Durability.LEDGER_CONFIRMED)
        self.assertIsInstance(first, AuditReceipt)
        self.assertEqual((second.chain_version, second.sequence), ('ds.audit.v2', 2))
        self.assertEqual(gateway.sink.verify('ds.audit.v2'), second)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 2)
        self.assertEqual(AuditLedgerEntry.objects.count(), 0)

    def test_absent_opt_in_preserves_legacy_and_rejects_new_events(self):
        del self.config['audit_chain']
        for version in ('ds.bootstrap.v1', 'ds.bootstrap.v2'):
            with self.subTest(version=version):
                self.config['schema_version'] = version
                if version == 'ds.bootstrap.v1':
                    self.config.pop('policy_repository')
                else:
                    self.config['policy_repository'] = {'kind': 'file', 'writable': False}
                gateway = self.build()['audit']
                for event in (self.event, examples()[QuotaRecoveryEvent]):
                    refused = gateway.record(event, Durability.LEDGER_CONFIRMED)
                    self.assertIsInstance(refused, ProtectionError)
                    self.assertEqual(refused.code, ReasonCode.AUDIT_UNAVAILABLE)
                old = gateway.record(replace(examples()[SecurityEvent], event_id=version),
                                     Durability.LEDGER_CONFIRMED)
                self.assertEqual(old.chain_version, 'v1')
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 0)
        self.assertEqual(SecurityAuditRecord.objects.count(), 2)

    def test_invalid_configuration_and_unapproved_environment_fail_before_writes(self):
        for options in (None, [], {**self.options, 'chain_version': 'v1'},
                        {**self.options, 'implementation': 'arbitrary.Sink'},
                        {**self.options, 'object_uuid': 'not-a-uuid'},
                        {**self.options, 'retained_keys': {}},
                        {**self.options, 'checkpoint_root': 1},
                        {**self.options, 'checkpoint_ref': []}):
            with self.subTest(options=options), self.assertRaises(ContractViolation):
                self.config['audit_chain'] = options
                self.build()
        self.config['audit_chain'] = self.options
        self.config['environment'] = 'production'
        with self.assertRaises(ContractViolation):
            self.build()
        self.config['environment'] = 'evaluation'
        root = Path(self.options['checkpoint_root'])
        root.chmod(0o755)
        with self.assertRaises(ContractViolation):
            self.build()
        root.chmod(0o700)
        self.assertEqual(SecurityAuditRecord.objects.count(), 0)

    def test_explicit_checkpoint_is_verified_at_startup_without_database_fallback(self):
        gateway = self.build()['audit']
        self.assertIsInstance(gateway.record(self.event, Durability.LEDGER_CONFIRMED), AuditReceipt)
        anchored = gateway.sink.checkpoint('ds.audit.v2')
        self.assertIsInstance(anchored, AuditReceipt)
        self.options['checkpoint_ref'] = anchored.checkpoint_ref
        self.assertEqual(self.build()['audit'].sink.verify('ds.audit.v2'), anchored)
        root = Path(self.options['checkpoint_root'])
        path = root / (anchored.checkpoint_ref.removeprefix('audit/checkpoint/') + '.json')
        encoded = path.read_bytes()
        path.write_bytes(encoded[:-1])
        with self.assertRaises(ContractViolation):
            self.build()
        path.unlink()
        with self.assertRaises(ContractViolation):
            self.build()
        self.assertEqual(SecurityAuditRecord.objects.count(), 1)

    def test_explicit_retained_readonly_key_verifies_prefix_before_new_key_append(self):
        gateway = self.build()['audit']
        first = gateway.record(self.event, Durability.LEDGER_CONFIRMED)
        anchored = gateway.sink.checkpoint('ds.audit.v2')
        self.assertIsInstance(anchored, AuditReceipt)
        manifest_path = Path(self.config['key_manifest'])
        manifest = json.loads(manifest_path.read_bytes())
        old = replace(self.refs['audit_key'], status=KeyStatus.READ_ONLY)
        for entry in manifest['entries']:
            if entry['reference']['key_ref'] == old.key_ref:
                entry['reference'] = old.to_wire()
        current = replace(self.refs['audit_key'], key_ref='audit-auth/v2', version='v2')
        key_path = self.path.parent / 'synthetic-audit-v2.key'
        key_path.write_bytes(secrets.token_bytes(32))
        key_path.chmod(0o600)
        manifest['entries'].append({'reference': current.to_wire(), 'file': key_path.name,
                                    'identities': ['service/security']})
        manifest_path.write_text(json.dumps(manifest))
        self.config['audit_key'] = current.to_wire()
        self.options.update(retained_keys=[old.to_wire()], checkpoint_ref=anchored.checkpoint_ref)
        rotated = self.build()['audit']
        self.assertEqual(rotated.sink.keys[old.key_ref].status, KeyStatus.READ_ONLY)
        second = rotated.record(replace(self.event, event_id='synthetic/rotated'), Durability.LEDGER_CONFIRMED)
        self.assertEqual(second.sequence, first.sequence + 1)
        self.assertEqual(rotated.sink.verify('ds.audit.v2'), replace(second, checkpoint_ref=anchored.checkpoint_ref))
        self.options['retained_keys'] = []
        with self.assertRaises(ContractViolation):
            self.build()

    def test_unavailable_or_reused_retained_material_fails_readiness(self):
        old = replace(self.refs['audit_key'], key_ref='audit-auth/v0', version='v0', status=KeyStatus.READ_ONLY)
        self.options['retained_keys'] = [old.to_wire()]
        with self.assertRaises(ContractViolation):
            self.build()
        manifest_path = Path(self.config['key_manifest'])
        manifest = json.loads(manifest_path.read_bytes())
        key_path = self.path.parent / 'synthetic-audit-v0.key'
        key_path.write_bytes((self.path.parent / 'data_key.key').read_bytes())
        key_path.chmod(0o600)
        manifest['entries'].append({'reference': old.to_wire(), 'file': key_path.name,
                                    'identities': ['service/security']})
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaises(ContractViolation):
            self.build()
        self.assertEqual(SecurityAuditRecord.objects.count(), 0)

    def test_actual_startup_binds_one_authenticated_gateway_and_bad_anchor_stops_startup(self):
        import subprocess
        import sys
        from tools.data_security import isolation

        self.path.write_text(json.dumps(self.config))
        env = isolation.environment()
        env.update(DATA_SECURITY_CONFIG=str(self.path), DJANGO_SETTINGS_MODULE='tools.data_security.test_settings')
        code = '''
import json,sys
from pathlib import Path
sys.path[:0] = [str(Path.cwd()), str(Path.cwd() / 'backend')]
import tools.data_security.test_settings as settings
settings.DATABASES['default']['NAME'] = sys.argv[1]
import django
django.setup()
from audit import bridge
from export_risk.decisions import outbox
from data_security.contracts import AuditReceipt, Durability, QuotaRecoveryEvent
from data_security.tests.fixtures import examples
gateway = bridge._binding[0]
assert gateway is outbox._binding[0]
receipt = gateway.record(examples()[QuotaRecoveryEvent], Durability.LEDGER_CONFIRMED)
assert isinstance(receipt, AuditReceipt) and receipt.chain_version == 'ds.audit.v2'
assert gateway.sink.verify('ds.audit.v2') == receipt
print(json.dumps({'authenticated_startup': True, 'shared_gateway': True}))
'''
        args = [sys.executable, '-I', '-B', '-c', code, connection.settings_dict['NAME']]
        result = subprocess.run(args, cwd=isolation.ROOT, env=env, capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout), {'authenticated_startup': True, 'shared_gateway': True})
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)
        self.options['checkpoint_ref'] = 'audit/checkpoint/' + '0' * 64
        self.path.write_text(json.dumps(self.config))
        refused = subprocess.run(args, cwd=isolation.ROOT, env=env, capture_output=True, timeout=60)
        self.assertNotEqual(refused.returncode, 0)
        self.assertNotIn(b'authenticated_startup', refused.stdout)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)

    def test_live_key_revocation_does_not_fall_back_to_legacy(self):
        gateway = self.build()['audit']
        self.assertIsInstance(gateway.record(self.event, Durability.LEDGER_CONFIRMED), AuditReceipt)
        manifest_path = Path(self.config['key_manifest'])
        manifest = json.loads(manifest_path.read_bytes())
        for entry in manifest['entries']:
            if entry['reference']['key_ref'] == self.refs['audit_key'].key_ref:
                entry['reference']['status'] = KeyStatus.RETIRED.value
        manifest_path.write_text(json.dumps(manifest))
        refused = gateway.record(replace(self.event, event_id='synthetic/after-revoke'), Durability.LEDGER_CONFIRMED)
        self.assertIsInstance(refused, ProtectionError)
        self.assertEqual(refused.code, ReasonCode.AUDIT_UNAVAILABLE)
        self.assertEqual(SecurityAuditRecord.objects.count(), 1)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)
        self.assertEqual(AuditLedgerEntry.objects.count(), 0)
