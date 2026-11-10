"""B4 real business rows, current Django permissions, B and authenticated ledger.

Opt-in isolated PostgreSQL only. The writing session collects but never executes
this module; independent test sessions own persistence and integration results.
"""
from copy import deepcopy
from dataclasses import replace
import io
import json
import logging
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.db import DatabaseError, connection, transaction
from django.test import TransactionTestCase

from agent_runtime.models import AgentRun
from audit.models import AuthenticatedAuditEntry, SecurityAuditRecord
from challenges.models import Category, Challenge
from ctf_backend.security_bootstrap import assemble
from data_security.adapters.django.logging import SafeLogFormatter
from data_security.adapters.llm.official import OfficialAI
from data_security.adapters.persistence.canary_catalog import CanaryRegistration
from data_security.contracts import (
    BASELINE_LIMITS, CanarySeed, CipherEnvelope, ContractViolation, Environment, KeyStatus,
    Outlet, ProtectionError, ReasonCode, SecurityEventV2, canonical_bytes,
)
from data_security.tests.fixtures import examples
from data_security.tests.phase3_fixtures import configuration
from legal_kb.models import LegalDocument
from resources.models import ResourceCache
from users.models import CTFUser


class B4CanaryPostgresTests(TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.assertEqual(connection.vendor, 'postgresql', 'B4 requires isolated PostgreSQL, never SQLite')
        files = configuration(providers=('deepseek',))
        self.path, self.config, _, _, _ = files.__enter__()
        self.addCleanup(files.__exit__, None, None, None)
        self.actor = CTFUser.objects.create_user(username='b4-synthetic-owner', role='teacher', is_staff=True)
        permissions = Permission.objects.filter(codename__in=(
            'add_canaryregistration', 'view_canaryregistration', 'change_canaryregistration',
            'change_legaldocument', 'view_legaldocument', 'change_resourcecache', 'view_resourcecache',
            'change_challenge', 'view_challenge'))
        self.assertEqual(permissions.count(), 9)
        self.actor.user_permissions.add(*permissions)
        self.targets = {
            'knowledge': LegalDocument.objects.create(title='合成资料', document_type='other',
                full_text='', source_hash='a' * 64, status='draft', created_by=self.actor),
            'database': ResourceCache.objects.create(studentId=self.actor.pk, knowledgePoint='合成资料', resourceList=[]),
            'challenge': Challenge.objects.create(title='合成题目', description='',
                category=Category.objects.create(name='合成分类'), difficulty='easy', score=1, flag='', is_active=False),
        }
        self.seeds = tuple(replace(examples()[CanarySeed], seed_id='a' * 31 + str(number),
            target_kind=kind, target_ref=kind + '/' + str(self.targets[kind].pk),
            environment=Environment.EVALUATION, domain='ctf')
            for number, kind in enumerate(self.targets, start=1))
        root = self.path.parent
        for name in ('checkpoints', 'private', 'backups'):
            (root / name).mkdir(mode=0o700)
        db = connection.settings_dict
        self.config.update(schema_version='ds.bootstrap.v2', policy_repository={'kind': 'file', 'writable': False},
            audit_chain={'chain_version': 'ds.audit.v2', 'project_ref': 'b4/synthetic',
                'object_uuid': '00000000-0000-0000-0000-000000000001', 'object_version': '1',
                'authorization_ref': 'authorization/b4-synthetic', 'retained_keys': [],
                'checkpoint_root': str(root / 'checkpoints'), 'checkpoint_ref': None},
            canary={'seeds': [seed.to_wire() for seed in self.seeds], 'project_ref': 'b4/synthetic',
                'provider_ref': 'deepseek'},
            backup={'database': {'host': db['HOST'], 'port': db['PORT'], 'dbname': db['NAME'], 'user': db['USER']},
                'directory': str(root / 'backups'), 'checks': [['check/b4', 'SELECT 1']],
                # No subprocess is invoked by this suite. Real backup tools belong to a separate dispatch.
                'age': '/synthetic/not-invoked/age', 'pg_dump': '/synthetic/not-invoked/pg_dump',
                'pg_restore': '/synthetic/not-invoked/pg_restore', 'private_root': str(root / 'private'),
                'code_version': 'b4/synthetic', 'required_keys': [self.config['data_key'], self.config['audit_key']],
                'full_inventory': True})
        self.path.write_text(json.dumps(self.config))
        self.components = assemble(config_path=self.path)
        self.owner = self.components['canary']['owner']
        self.registry = self.components['canary']['registry']
        self.tools = self.components['canary']['tools']
        self.sink = self.components['audit'].sink

    def plant(self, seed):
        result = self.registry.run('canary.plant', arguments={'seed_id': seed.seed_id}, user=self.actor)
        self.assertEqual(result, {'status': 'planted', 'seed_id': seed.seed_id})
        return result

    def anchor(self):
        receipt = self.sink.checkpoint('ds.audit.v2')
        self.assertNotIsInstance(receipt, ProtectionError)
        self.sink.checkpoint_ref = receipt.checkpoint_ref

    def test_three_real_targets_ciphertext_directory_and_v2_commit_together(self):
        for seed in self.seeds:
            self.plant(seed)
            target = self.targets[seed.target_kind]
            target.refresh_from_db()
            envelope = CipherEnvelope.from_wire(target.canary_payload)
            packet = self.components['crypto'].open(envelope, self.owner._object_context(seed), envelope.key)
            self.assertNotIsInstance(packet, ProtectionError)
            self.assertEqual(packet.tree.to_value()['seed'], seed.to_wire())
            self.assertTrue(packet.tree.to_value()['synthetic'])
            for literal in packet.tree.to_value()['values'].values():
                self.assertNotIn(literal.encode(), canonical_bytes(envelope))
                self.assertNotIn(literal, json.dumps(CanaryRegistration.objects.get(seed_id=seed.seed_id).seed_document))
            result = self.registry.run('canary.check', arguments={'artifact_ref': 'canary/' + seed.seed_id}, user=self.actor)
            self.assertEqual(result, {'status': 'alert', 'alert_count': 1})
            event = SecurityEventV2.from_wire(SecurityAuditRecord.objects.order_by('id').last().event)
            self.assertEqual(event.counts, (('hit', 3),))
            for literal in packet.tree.to_value()['values'].values():
                self.assertNotIn(literal.encode(), canonical_bytes(event))
        self.assertEqual(CanaryRegistration.objects.count(), 3)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 6)
        self.assertEqual(self.targets['knowledge'].full_text, '')
        self.assertEqual(self.targets['database'].resourceList, [])
        self.assertFalse(self.targets['challenge'].is_active)

    def test_configuration_cannot_disable_or_drop_retained_canary_directory(self):
        self.plant(self.seeds[0])
        self.config['canary']['seeds'] = [self.seeds[1].to_wire(), self.seeds[2].to_wire()]
        self.path.write_text(json.dumps(self.config))
        with self.assertRaises(ContractViolation):
            assemble(config_path=self.path)
        del self.config['canary']
        self.path.write_text(json.dumps(self.config))
        with self.assertRaises(ContractViolation):
            assemble(config_path=self.path)

    def test_retained_read_only_key_opens_original_ciphertext_without_resealing(self):
        import secrets
        seed = self.seeds[0]
        self.plant(seed)
        self.anchor()
        old = deepcopy(self.config['data_key'])
        retained = dict(old, status=KeyStatus.READ_ONLY.value)
        new = dict(old, key_ref='enc-data/v2', version='v2')
        key_path = self.path.parent / 'data-v2.key'
        key_path.write_bytes(secrets.token_bytes(32))
        key_path.chmod(0o600)
        manifest_path = Path(self.config['key_manifest'])
        manifest = json.loads(manifest_path.read_bytes())
        for entry in manifest['entries']:
            if entry['reference'] == old:
                entry['reference'] = retained
        manifest['entries'].append({'reference': new, 'file': key_path.name, 'identities': ['service/security']})
        manifest_path.write_text(json.dumps(manifest))
        self.config['data_key'] = new
        self.config['retained_data_keys'] = [retained]
        self.config['backup']['required_keys'] = [new, retained, self.config['audit_key']]
        self.config['audit_chain']['checkpoint_ref'] = self.sink.checkpoint_ref
        self.path.write_text(json.dumps(self.config))
        reader = assemble(config_path=self.path)['canary']['owner']
        original = deepcopy(LegalDocument.objects.get(pk=self.targets['knowledge'].pk).canary_payload)
        with patch.object(reader.crypto, 'seal') as seal:
            proof = reader.restore_catalog()
            self.assertNotIsInstance(proof, ProtectionError)
            self.assertEqual(proof['data_key_refs'], [old['key_ref']])
            seal.assert_not_called()
        self.assertEqual(LegalDocument.objects.get(pk=self.targets['knowledge'].pk).canary_payload, original)
        self.assertFalse(proof['key_retirement_allowed'])

    def test_current_permissions_disable_cached_user_and_do_not_grant_by_role(self):
        seed = self.seeds[0]
        permission = Permission.objects.get(codename='change_legaldocument')
        self.actor.user_permissions.remove(permission)
        self.assertEqual(self.registry.run('canary.plant', arguments={'seed_id': seed.seed_id},
            user=self.actor)['code'], 'AUTHORIZATION_DENIED')
        self.actor.user_permissions.add(permission)
        self.plant(seed)
        view = Permission.objects.get(codename='view_canaryregistration')
        self.actor.user_permissions.remove(view)
        self.assertEqual(self.registry.run('canary.check', arguments={'artifact_ref': 'canary/' + seed.seed_id},
            user=self.actor)['code'], 'AUTHORIZATION_DENIED')
        CTFUser.objects.filter(pk=self.actor.pk).update(is_active=False)
        self.assertEqual(self.registry.run('canary.plant', arguments={'seed_id': self.seeds[1].seed_id},
            user=self.actor)['code'], 'AUTHORIZATION_DENIED')
        self.assertEqual(CanaryRegistration.objects.count(), 1)

    def test_no_other_owner_existing_body_or_public_challenge_is_written(self):
        LegalDocument.objects.filter(pk=self.targets['knowledge'].pk).update(full_text='Existing body')
        ResourceCache.objects.filter(pk=self.targets['database'].pk).update(studentId=self.actor.pk + 1)
        Challenge.objects.filter(pk=self.targets['challenge'].pk).update(is_active=True)
        for seed in self.seeds:
            self.assertEqual(self.registry.run('canary.plant', arguments={'seed_id': seed.seed_id},
                user=self.actor)['status'], 'error')
        self.assertEqual(CanaryRegistration.objects.count(), 0)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 0)

    def test_audit_failure_rolls_back_target_and_directory_without_legacy_success(self):
        with patch.object(self.components['audit'], 'record', return_value=ProtectionError(
                schema_version=ProtectionError.SCHEMA, code=ReasonCode.AUDIT_UNAVAILABLE,
                retryable=False, trace_id='b4/audit-fault')):
            result = self.registry.run('canary.plant', arguments={'seed_id': self.seeds[0].seed_id}, user=self.actor)
        self.assertEqual(result['code'], 'AUDIT_UNAVAILABLE')
        self.targets['knowledge'].refresh_from_db()
        self.assertEqual(self.targets['knowledge'].canary_payload, {})
        self.assertEqual(CanaryRegistration.objects.count(), 0)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 0)

    def test_duplicate_plant_observes_original_and_unknown_after_commit_is_not_rewritten(self):
        seed = self.seeds[0]
        self.plant(seed)
        self.targets['knowledge'].refresh_from_db()
        original = deepcopy(self.targets['knowledge'].canary_payload)
        with patch.object(self.components['crypto'], 'seal') as seal:
            self.plant(seed)
            seal.assert_not_called()
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 1)
        real_atomic = transaction.atomic
        class LostCommitConfirmation:
            def __enter__(inner):
                inner.atomic = real_atomic()
                return inner.atomic.__enter__()
            def __exit__(inner, *args):
                result = inner.atomic.__exit__(*args)
                if args[0] is None:
                    raise DatabaseError('synthetic lost commit confirmation')
                return result
        with patch('data_security.adapters.persistence.canary_targets.transaction.atomic',
                   side_effect=lambda *args, **kwargs: real_atomic(*args, **kwargs)
                       if connection.in_atomic_block else LostCommitConfirmation()):
            result = self.registry.run('canary.plant', arguments={'seed_id': self.seeds[1].seed_id}, user=self.actor)
        self.assertEqual(result['code'], 'DELIVERY_UNKNOWN')
        self.plant(self.seeds[1])
        self.targets['knowledge'].refresh_from_db()
        self.assertEqual(self.targets['knowledge'].canary_payload, original)
        self.assertEqual(CanaryRegistration.objects.count(), 2)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 2)

    def test_retirement_preserves_ciphertext_historical_detection_and_refuses_replant(self):
        seed = self.seeds[0]
        self.plant(seed)
        self.targets['knowledge'].refresh_from_db()
        original = deepcopy(self.targets['knowledge'].canary_payload)
        self.assertEqual(self.owner.retire(seed_id=seed.seed_id, user=self.actor), {'status': 'retired'})
        self.assertEqual(self.owner.retire(seed_id=seed.seed_id, user=self.actor), {'status': 'retired'})
        self.assertEqual(self.registry.run('canary.plant', arguments={'seed_id': seed.seed_id},
            user=self.actor)['code'], 'AUTHORIZATION_DENIED')
        self.assertEqual(self.registry.run('canary.check', arguments={'artifact_ref': 'canary/' + seed.seed_id},
            user=self.actor)['code'], 'AUTHORIZATION_DENIED')
        self.targets['knowledge'].refresh_from_db()
        self.assertEqual(self.targets['knowledge'].canary_payload, original)
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), 2)
        packet = self.tools.catalog[seed.seed_id][1]
        service_context = self.components['canary']['log_context']
        alerts = self.tools.check(payload=packet, context=service_context)
        self.assertEqual(len(alerts), 1)
        self.anchor()
        proof = self.owner.restore_catalog()
        self.assertEqual((proof['planted'], proof['retired']), (0, 1))
        self.assertFalse(proof['traffic_opened'])
        self.assertFalse(proof['key_retirement_allowed'])
        self.assertEqual(proof['data_key_refs'], [self.config['data_key']['key_ref']])

    def test_restoration_is_read_only_and_rejects_ciphertext_metadata_and_orphan_catalog(self):
        for seed in self.seeds:
            self.plant(seed)
        self.anchor()
        before = list(SecurityAuditRecord.objects.values('event_id', 'event'))
        proof = self.owner.restore_catalog()
        self.assertNotIsInstance(proof, ProtectionError)
        self.assertEqual((proof['planted'], proof['retired']), (3, 0))
        self.assertEqual(list(SecurityAuditRecord.objects.values('event_id', 'event')), before)
        registration = CanaryRegistration.objects.get(seed_id=self.seeds[0].seed_id)
        original_hash = registration.packet_hash
        registration.packet_hash = '0' * 64
        registration.save(update_fields=['packet_hash'])
        self.assertEqual(self.owner.restore_catalog().code, ReasonCode.HASH_MISMATCH)
        registration.packet_hash = original_hash
        registration.save(update_fields=['packet_hash'])
        target = self.targets['knowledge']
        target.refresh_from_db()
        original = deepcopy(target.canary_payload)
        envelope = CipherEnvelope.from_wire(original)
        target.canary_payload = replace(envelope, ciphertext_and_tag=bytes(len(envelope.ciphertext_and_tag))).to_wire()
        target.save(update_fields=['canary_payload'])
        self.assertIsInstance(self.owner.restore_catalog(), ProtectionError)
        target.canary_payload = original
        target.save(update_fields=['canary_payload'])
        registration.delete()
        self.assertEqual(self.owner.restore_catalog().code, ReasonCode.REPORT_MISMATCH)
        self.assertEqual(list(SecurityAuditRecord.objects.values('event_id', 'event')), before)

    def test_missing_configuration_key_checkpoint_or_authenticated_event_is_closed(self):
        self.plant(self.seeds[0])
        self.assertIsInstance(self.owner.restore_catalog(), ProtectionError)  # No selected checkpoint.
        self.anchor()
        saved = dict(self.owner.seeds)
        self.owner.seeds = {}
        self.assertEqual(self.owner.restore_catalog().code, ReasonCode.SOURCE_NOT_APPROVED)
        self.owner.seeds = saved
        with patch.object(self.components['crypto'].keys, 'resolve', return_value=ProtectionError(
                schema_version=ProtectionError.SCHEMA, code=ReasonCode.KEY_UNAVAILABLE,
                retryable=False, trace_id='b4/missing-key')):
            self.assertIsInstance(self.owner.restore_catalog(), ProtectionError)
        row = SecurityAuditRecord.objects.get(event_id='canary/plant/' + self.seeds[0].seed_id)
        row.event = dict(row.event, actor_ref='user/forged')
        row.save(update_fields=['event'])
        self.assertIsInstance(self.owner.restore_catalog(), ProtectionError)

    def test_closed_recovery_journal_blocks_tools_and_model_transport(self):
        from data_security.adapters.persistence.recovery_state import RecoveryJournal
        from data_security.contracts import Purpose
        journal = RecoveryJournal(root=self.components['backup'].private_root,
            target_identity=self.components['backup'].source_identity, code_version='b4/synthetic',
            environment=Environment.EVALUATION, domain='ctf', service_identity='service/security',
            clock=self.components['clock'], limits=BASELINE_LIMITS)
        context = replace(self.components['canary']['log_context'], outlet=Outlet.AUDIT, purpose=Purpose.STORAGE)
        journal.start(context)
        result = self.registry.run('canary.plant', arguments={'seed_id': self.seeds[0].seed_id}, user=self.actor)
        self.assertEqual(result['status'], 'error')
        self.assertEqual(CanaryRegistration.objects.count(), 0)
        with patch.object(OfficialAI, '_http') as transport:
            result = self.components['security_runtime'].run_security_task(user=self.actor,
                message='Check an explicitly authorized synthetic artifact.')
            self.assertEqual(result['status'], 'error')
            transport.assert_not_called()
        self.assertEqual(journal.read(context)['state'], 'closed')

    def test_formal_b_model_selected_tools_use_actual_owner_without_agent_run_or_body_results(self):
        seed = self.seeds[0]
        def response(name=None, ref=None, number=0):
            calls = [] if name is None else [{'id': 'b4_call_' + str(number), 'type': 'function',
                'function': {'name': name, 'arguments': json.dumps({
                    'seed_id' if name == 'canary_plant' else 'artifact_ref': ref})}}]
            return json.dumps({'choices': [{'message': {'role': 'assistant', 'content': 'Done.' if not calls else None,
                'tool_calls': calls}, 'finish_reason': 'tool_calls' if calls else 'stop'}]}).encode()
        bodies = [response('canary_plant', seed.seed_id, 1),
                  response('canary_check', 'canary/' + seed.seed_id, 2), response()]
        with patch.object(OfficialAI, '_http', side_effect=bodies) as transport:
            result = self.components['security_runtime'].run_security_task(user=self.actor,
                message='Plant the explicitly authorized synthetic seed ' + seed.seed_id +
                    ' and check artifact canary/' + seed.seed_id + '.')
        self.assertEqual(result, {'status': 'completed', 'results': [
            {'status': 'planted', 'seed_id': seed.seed_id}, {'status': 'alert', 'alert_count': 1}]})
        self.assertEqual(transport.call_count, 3)
        self.assertEqual(CanaryRegistration.objects.count(), 1)
        self.assertEqual(AgentRun.objects.count(), 0)
        for literal in self.tools.catalog[seed.seed_id][1].tree.to_value()['values'].values():
            self.assertNotIn(literal, json.dumps(result))
            for call in transport.call_args_list:
                self.assertNotIn(literal, json.dumps(call.kwargs['body']))

    def test_formal_b_model_and_log_final_payload_hooks_block_and_confirm_v2(self):
        seed = self.seeds[0]
        self.plant(seed)
        values = self.tools.catalog[seed.seed_id][1].tree.to_value()['values']
        literal = ' '.join(values.values())
        runtime = self.components['security_runtime']
        adapter = runtime.security_provider._port
        handle = runtime.security_provider
        request = handle._request({'messages': [{'role': 'user', 'content': literal}]},
            temperature=0.7, max_tokens=64)
        context = handle._context(Outlet.MODEL)
        with patch.object(adapter, '_protect', side_effect=lambda payload, *_: payload), \
             patch.object(adapter.keys, 'resolve') as keys, patch.object(adapter, '_http') as transport:
            result = adapter.chat(request, context, self.components['binding'])
            self.assertEqual(result.code, ReasonCode.SCOPE_INCOMPLETE)
            keys.assert_not_called()
            transport.assert_not_called()
        output = io.StringIO()
        handler = logging.StreamHandler(output)
        handler.setFormatter(SafeLogFormatter(canary=self.tools, canary_context=self.components['canary']['log_context'],
            limits=BASELINE_LIMITS))
        handler.handle(logging.LogRecord('b4', 20, '', 0, literal, (), None))
        self.assertEqual(output.getvalue(), 'LOG_MESSAGE_OMITTED\n')
        before = AuthenticatedAuditEntry.objects.count()
        with patch.object(logging.Formatter, 'format', return_value=literal):
            handler.handle(logging.LogRecord('b4', 20, '', 0, 'safe', (), None))
        self.assertEqual(output.getvalue(), 'LOG_MESSAGE_OMITTED\nLOG_CANARY_BLOCKED\n')
        self.assertEqual(AuthenticatedAuditEntry.objects.count(), before + 1)
        verified = self.sink.verify('ds.audit.v2')
        self.assertNotIsInstance(verified, ProtectionError)
