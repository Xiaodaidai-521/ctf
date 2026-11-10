"""Database-free B4 boundaries; real persistence/ACL/ledger tests are separately dispatched."""
from contextlib import ExitStack, nullcontext
from dataclasses import replace
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, Mock, patch

from challenges.models import Challenge
from challenges.serializers import ChallengeListSerializer, ChallengeSerializer
from ctf_backend.security_bootstrap import _canary_components, _resource_exports, assemble_canary_runtime, assemble_recovery
from data_security.adapters.persistence.canary_catalog import CanaryRegistration
from data_security.adapters.persistence.canary_targets import DjangoCanaryTargets
from data_security.application.canary import CanaryTools
from data_security.contracts import (
    BASELINE_LIMITS, CanarySeed, ContractViolation, Environment, KeyPurpose, KeyStatus,
    ObjectContext, Outlet, PolicyBinding, ProtectionContext, ProtectionError, ReasonCode,
    Role, SecurityEventV2, canonical_bytes,
)
from data_security.tests.fixtures import AT, examples
from data_security.tests.phase2_fixtures import reference_key
from data_security.tests.test_phase2_services import crypto_service
from data_security.tests.test_phase6_canary_outputs import CanaryTableTests
from legal_kb.models import LegalDocument
from legal_kb.serializers import LegalDocumentSerializer
from resources.models import ResourceCache


class BusinessOwnerBoundaryTests(TestCase):
    def setUp(self):
        self.seed = replace(examples()[CanarySeed], target_kind='knowledge', target_ref='knowledge/12')
        self.actor = SimpleNamespace(pk=7, role='teacher', is_staff=True, has_perm=Mock(return_value=True))
        self.target = SimpleNamespace(pk=12, created_by_id=7, status='draft', document_type='other',
            full_text='', source_url='', clauses=Mock(exists=Mock(return_value=False)), canary_payload={})
        self.owner = DjangoCanaryTargets(seeds=(self.seed,), crypto=crypto_service(),
            data_key=reference_key(KeyPurpose.DATA), project_ref='ctf/synthetic', environment=Environment.TEST,
            domain=self.seed.domain, audit=Mock(), read_event=Mock(), recovery_events=Mock(),
            policy_binding=examples()[PolicyBinding], clock=lambda: AT, limits=BASELINE_LIMITS)
        self.users = patch('data_security.adapters.persistence.canary_targets.CTFUser.objects.filter')
        self.query = self.users.start()
        self.addCleanup(self.users.stop)
        self.query.return_value.first.return_value = self.actor
        self.targets = patch.object(self.owner, '_target', return_value=self.target)
        self.targets.start()
        self.addCleanup(self.targets.stop)

    def test_current_user_and_both_explicit_permissions_not_cached_role(self):
        context = self.owner.resolve_context('canary.plant', self.seed.seed_id, SimpleNamespace(pk=7))
        self.query.assert_called_once_with(pk=7, is_active=True)
        self.assertEqual(context.actor_ref, 'user/7')
        self.assertEqual([call.args[0] for call in self.actor.has_perm.call_args_list],
            ['security_policies.add_canaryregistration', 'legal_kb.change_legaldocument'])
        for missing in ('security_policies.add_canaryregistration', 'legal_kb.change_legaldocument'):
            self.actor.has_perm.side_effect = lambda permission: permission != missing
            with self.assertRaises(ContractViolation):
                self.owner.resolve_context('canary.plant', self.seed.seed_id, SimpleNamespace(pk=7, role='admin'))
        self.query.return_value.first.return_value = None
        with self.assertRaises(ContractViolation):
            self.owner.resolve_context('canary.plant', self.seed.seed_id, self.actor)

    def test_only_empty_owned_knowledge_draft_can_be_selected(self):
        for changes in ({'created_by_id': 8}, {'status': 'active'}, {'document_type': 'law'},
                        {'full_text': 'Existing body'}, {'source_url': 'https://example.invalid/source'}):
            target = SimpleNamespace(**{**vars(self.target), **changes})
            with self.assertRaises(ContractViolation):
                self.owner._synthetic_scope(self.seed, target, self.actor)
        self.target.clauses.exists.return_value = True
        with self.assertRaises(ContractViolation):
            self.owner._synthetic_scope(self.seed, self.target, self.actor)

    def test_database_scope_is_current_user_empty_business_cache(self):
        seed = replace(self.seed, target_kind='database', target_ref='database/12')
        for target in (SimpleNamespace(studentId=8, resourceList=[]),
                       SimpleNamespace(studentId=7, resourceList=[{'resource': 'existing'}])):
            with self.assertRaises(ContractViolation):
                self.owner._synthetic_scope(seed, target, self.actor)
        self.owner._synthetic_scope(seed, SimpleNamespace(studentId=7, resourceList=[]), self.actor)

    def test_challenge_reads_real_protected_flag_not_empty_database_placeholder(self):
        seed = replace(self.seed, target_kind='challenge', target_ref='challenge/12')
        target = SimpleNamespace(is_active=False, description='', hint='', attachment=None,
            docker_image=None, security_envelopes={'flag': {}}, flag='')
        with self.assertRaises(ContractViolation):
            self.owner._synthetic_scope(seed, target, self.actor)
        self.owner.read_flag = Mock(return_value='actual nonempty flag')
        with self.assertRaises(ContractViolation):
            self.owner._synthetic_scope(seed, target, self.actor)
        self.owner.read_flag.return_value = ''
        self.owner._synthetic_scope(seed, target, self.actor)
        for changes in ({'is_active': True}, {'description': 'Existing question'}, {'docker_image': 'image'}):
            with self.assertRaises(ContractViolation):
                self.owner._synthetic_scope(seed, SimpleNamespace(**{**vars(target), **changes}), self.actor)
        self.actor.is_staff = False
        with self.assertRaises(ContractViolation):
            self.owner._synthetic_scope(seed, target, self.actor)

    def test_check_reference_is_not_a_path_and_requires_planted_actor_registration(self):
        for ref in ('/tmp/output', 'canary/' + self.seed.seed_id + '/body', 'output/12', 'canary/' + 'f' * 32):
            with self.assertRaises(ContractViolation):
                self.owner.resolve_context('canary.check', ref, self.actor)
        with patch.object(CanaryRegistration.objects, 'filter') as rows:
            rows.return_value.first.return_value = SimpleNamespace(actor_ref='user/8')
            with self.assertRaises(ContractViolation):
                self.owner.resolve_context('canary.check', 'canary/' + self.seed.seed_id, self.actor)
            rows.return_value.first.return_value = SimpleNamespace(actor_ref='user/7')
            context = self.owner.resolve_context('canary.check', 'canary/' + self.seed.seed_id, self.actor)
            self.assertIs(context.outlet, Outlet.EXPORT)
            rows.assert_called_with(seed_id=self.seed.seed_id, state='planted')

    def test_closed_recovery_admission_precedes_any_current_owner_read(self):
        self.owner.admission = Mock(return_value=False)
        with self.assertRaises(ContractViolation):
            self.owner.resolve_context('canary.plant', self.seed.seed_id, self.actor)
        self.query.assert_not_called()

    def test_only_exact_internal_service_checker_is_accepted(self):
        context = replace(examples()[ProtectionContext], actor_ref='service/security',
            authorization_ref='authorization/phase3-isolated', role=Role.SERVICE,
            environment=Environment.TEST, domain=self.seed.domain, outlet=Outlet.MODEL)
        self.assertEqual(self.owner.authorize('canary.check', context, None), context)
        for changes in ({'actor_ref': 'service/other'}, {'authorization_ref': 'arbitrary/grant'},
                        {'outlet': Outlet.EXPORT}, {'domain': 'other'}):
            with self.assertRaises(ContractViolation):
                self.owner.authorize('canary.check', replace(context, **changes), None)
        self.query.assert_not_called()

    def test_actual_ciphertext_packet_and_authenticated_metadata_are_required(self):
        tools = CanaryTools(seeds=(self.seed,), environment=Environment.TEST, domain=self.seed.domain,
            limits=BASELINE_LIMITS, policy_binding=self.owner.policy_binding, authorize=Mock(),
            plant_target=Mock(), audit=Mock(), clock=lambda: AT, event_id=Mock())
        packet = tools.catalog[self.seed.seed_id][1]
        envelope = self.owner.crypto.seal(packet, self.owner._object_context(self.seed), self.owner.data_key)
        self.target.canary_payload = envelope.to_wire()
        registration = SimpleNamespace(seed_id=self.seed.seed_id, seed_document=self.seed.to_wire(),
            target_pk='12', actor_ref='user/7', packet_hash=hashlib.sha256(
                canonical_bytes(packet, include_payload=True)).hexdigest(), state='planted',
            plant_event_id='canary/plant/' + self.seed.seed_id, retire_event_id='')
        event = replace(examples()[SecurityEventV2], event_id=registration.plant_event_id,
            actor_ref='user/7', object_ref=self.seed.target_ref, object_version=self.seed.target_version,
            algorithm_versions=('canary-target.v1', 'planted'), evidence_hashes=())
        from data_security.contracts import content_hash
        event = replace(event, evidence_hashes=(('ciphertext', content_hash(envelope)),
            ('report', content_hash(self.owner._metadata(registration)))))
        self.owner.read_event.return_value = event
        self.assertEqual(self.owner._verified(registration, self.seed, self.target), packet)
        for field, value in (('packet_hash', '0' * 64), ('target_pk', '13'), ('actor_ref', 'user/8')):
            changed = SimpleNamespace(**{**vars(registration), field: value})
            with self.assertRaises(ContractViolation):
                self.owner._verified(changed, self.seed, self.target)
        self.owner.read_event.return_value = True
        with self.assertRaises(ContractViolation):
            self.owner._verified(registration, self.seed, self.target)
        self.target.canary_payload = replace(envelope, ciphertext_and_tag=bytes(
            len(envelope.ciphertext_and_tag))).to_wire()
        with self.assertRaises(ContractViolation):
            self.owner._verified(registration, self.seed, self.target)

    def test_retained_catalog_cannot_be_removed_from_configuration_or_relabelled(self):
        registration = SimpleNamespace(seed_id=self.seed.seed_id, seed_document=self.seed.to_wire(), state='retired')
        with patch.object(CanaryRegistration.objects, 'all') as rows:
            rows.return_value.count.return_value = 1
            rows.return_value.iterator.return_value = iter([registration])
            self.owner.catalog_inventory()
            for changes in ({'seed_id': 'f' * 32}, {'state': 'unknown'}, {'seed_document': {}}):
                rows.return_value.iterator.return_value = iter([SimpleNamespace(**{**vars(registration), **changes})])
                with self.assertRaises(ContractViolation):
                    self.owner.catalog_inventory()

    def test_restore_checks_retained_orphans_and_reports_keys_without_writing(self):
        registration = SimpleNamespace(seed_id=self.seed.seed_id, state='retired')
        self.target.canary_payload = {'key': {'key_ref': 'enc-data/v1'}}
        db = MagicMock(vendor='postgresql', in_atomic_block=False)
        db.get_autocommit.return_value = True
        self.owner.recovery_events.return_value = {'events': {}}
        with ExitStack() as stack:
            stack.enter_context(patch('data_security.adapters.persistence.canary_targets.connection', db))
            stack.enter_context(patch('data_security.adapters.persistence.canary_targets.transaction.atomic',
                return_value=nullcontext()))
            stack.enter_context(patch.object(self.owner, '_verified'))
            rows = stack.enter_context(patch.object(CanaryRegistration.objects, 'all'))
            rows.return_value.count.return_value = 1
            rows.return_value.iterator.side_effect = lambda **kwargs: iter([registration])
            queries = {}
            for kind, (model, _, _) in self.owner.targets.items():
                queries[kind] = stack.enter_context(patch.object(model.objects, 'exclude'))
                queries[kind].return_value.count.return_value = 0
                queries[kind].return_value.iterator.side_effect = lambda **kwargs: iter([])
            queries['knowledge'].return_value.count.return_value = 1
            queries['knowledge'].return_value.iterator.side_effect = lambda **kwargs: iter([self.target])
            result = self.owner.restore_catalog()
            self.assertEqual(result['data_key_refs'], ['enc-data/v1'])
            self.assertEqual((result['planted'], result['retired']), (0, 1))
            self.assertFalse(result['traffic_opened'])
            db.cursor.return_value.__enter__.return_value.execute.assert_called_once_with(
                'SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
            queries['knowledge'].return_value.iterator.side_effect = lambda **kwargs: iter([SimpleNamespace(pk=13)])
            self.assertEqual(self.owner.restore_catalog().code, ReasonCode.REPORT_MISMATCH)
        self.owner.audit.record.assert_not_called()

    def test_three_dedicated_fields_are_not_normal_serializer_output(self):
        for model in (LegalDocument, ResourceCache, Challenge):
            field = model._meta.get_field('canary_payload')
            self.assertFalse(field.editable)
            self.assertEqual(field.get_default(), {})
        for serializer in (LegalDocumentSerializer, ChallengeSerializer, ChallengeListSerializer):
            self.assertNotIn('canary_payload', serializer.Meta.fields)

    def test_restore_refuses_dummy_database_before_transactions_or_ledger_reads(self):
        result = self.owner.restore_catalog()
        self.assertEqual(result.code, ReasonCode.SOURCE_NOT_APPROVED)
        self.owner.recovery_events.assert_not_called()


class CanaryCompositionTests(TestCase):
    def setUp(self):
        self.seed = replace(examples()[CanarySeed], target_ref='knowledge/12', target_kind='knowledge',
            domain='ctf', environment=Environment.EVALUATION)
        self.options = {'seeds': [self.seed.to_wire()], 'project_ref': 'ctf/synthetic', 'provider_ref': 'deepseek'}
        self.audit = Mock()
        self.backup = Mock(full_inventory=True, private_root=Path('/synthetic/private'), source_identity='1' * 64)
        self.kwargs = dict(crypto=Mock(), data_key=reference_key(KeyPurpose.DATA), audit=self.audit,
            binding=examples()[PolicyBinding], clock=lambda: AT, backup=self.backup)

    def test_explicit_config_binds_original_tools_to_actual_owner_and_directory(self):
        with patch.object(DjangoCanaryTargets, 'catalog_inventory') as inventory:
            result = _canary_components(self.options, **self.kwargs)
        self.assertIsInstance(result['owner'], DjangoCanaryTargets)
        self.assertIsInstance(result['tools'], CanaryTools)
        self.assertEqual(result['tools'].plant_target, result['owner'].plant_target)
        self.assertEqual(result['registry'].load_output, result['owner'].load_output)
        self.assertEqual(result['registry'].resolve_context, result['owner'].resolve_context)
        self.assertEqual(result['owner'].read_event, self.audit.sink.read_authenticated)
        inventory.assert_called_once()

    def test_missing_full_backup_provider_chain_or_unknown_config_is_rejected(self):
        cases = [(dict(self.options, body='not allowed'), self.kwargs),
                 (dict(self.options, provider_ref='spark'), self.kwargs),
                 (dict(self.options, seeds=[]), self.kwargs),
                 (self.options, {**self.kwargs, 'backup': None}),
                 (self.options, {**self.kwargs, 'backup': Mock(full_inventory=False)})]
        for options, kwargs in cases:
            with self.assertRaises(ContractViolation):
                _canary_components(options, **kwargs)
        self.audit.sink.crypto = None
        with self.assertRaises(ContractViolation):
            _canary_components(self.options, **self.kwargs)

    def test_formal_export_factory_reuses_current_source_target_owner_and_recovery_gate(self):
        with TemporaryDirectory(prefix='b4-export-compose-') as directory:
            owner = Mock()
            self.audit.sink.key = reference_key(KeyPurpose.AUDIT)
            components = {'audit': self.audit, 'clock': lambda: AT, 'binding': examples()[PolicyBinding],
                'crypto': crypto_service(), 'data_ref': reference_key(KeyPurpose.DATA), 'catalog': Mock(),
                'canary': {'seeds': (self.seed,), 'owner': owner}}
            options = {'private_root': directory, 'project_ref': 'ctf/synthetic', 'window_key': 'b4/synthetic',
                'limit': 10, 'ttl_seconds': 120}
            from resources.export_sources import ResourceExportSources
            from audit.export_plans import ExportPlanOwner
            with patch('data_security.adapters.persistence.risk.DjangoRiskPort'):
                entry = _resource_exports(components, options)
                owned = Mock(source_ref='source/1', permission_ref='permission/1', source_hash='a' * 64)
                flow = entry.flow_factory(SimpleNamespace(pk=7), owned)
            self.assertIsInstance(flow.executor.canary, CanaryTools)
            context = examples()[ProtectionContext]
            with patch.object(ResourceExportSources, 'authorize', return_value=context) as sources, \
                 patch.object(ExportPlanOwner, 'authorize', return_value=context) as targets:
                self.assertEqual(flow.executor.canary_context_factory(owned.plan, owned.binding, owned.context), context)
                self.assertEqual(flow.executor.canary.authorize('canary.check', context, None), context)
                self.assertEqual(sources.call_count, 2)
                self.assertEqual(targets.call_count, 2)
                self.assertEqual(owner._admitted.call_count, 2)
                owner._admitted.side_effect = ContractViolation(ReasonCode.SOURCE_NOT_APPROVED)
                with self.assertRaises(ContractViolation):
                    flow.executor.canary_context_factory(owned.plan, owned.binding, owned.context)
                self.assertEqual(sources.call_count, 2)

    def test_runtime_is_unavailable_without_explicit_component(self):
        with patch('ctf_backend.security_bootstrap.assemble', return_value={'security_runtime': None}):
            with self.assertRaises(ContractViolation):
                assemble_canary_runtime(config_path='/synthetic/config')

    def test_recovery_callback_composes_canary_keys_and_propagates_failure(self):
        identity = reference_key(KeyPurpose.BACKUP_PRIVATE, KeyStatus.READ_ONLY)
        with TemporaryDirectory(prefix='b4-recovery-compose-') as directory:
            self.backup.private_root = Path(directory)
            self.backup.code_version = 'b4'
            owner = Mock()
            owner.restore_catalog.return_value = {'data_key_refs': ['enc-data/v1'], 'traffic_opened': False}
            components = {'backup': self.backup, 'audit': self.audit, 'crypto': Mock(), 'fields': None,
                'canary': {'owner': owner}}
            self.audit.sink.checkpoint_ref = 'audit/checkpoint/' + '1' * 64
            original = {'complete': True, 'opening_allowed': True, 'data_key_refs': ['enc-data/v2'],
                'key_retirement_allowed': False}
            with patch('ctf_backend.security_bootstrap._configuration', return_value=({}, Mock())), \
                 patch('ctf_backend.security_bootstrap._backup_adapter', return_value=self.backup), \
                 patch('ctf_backend.security_bootstrap.assemble', return_value=components), \
                 patch('ctf_backend.security_bootstrap._private_upload_owners', return_value={}), \
                 patch('data_security.adapters.persistence.recovery_verifier.DjangoRecoveryVerifier') as verifier:
                verifier.return_value.return_value = original
                flow = assemble_recovery(config_path='/synthetic/config', identity=identity)
                result = flow.verify_owners(examples()[ProtectionContext])
                self.assertEqual(result['data_key_refs'], ['enc-data/v1', 'enc-data/v2'])
                self.assertFalse(result['key_retirement_allowed'])
                failure = ProtectionError(schema_version=ProtectionError.SCHEMA,
                    code=ReasonCode.REPORT_MISMATCH, retryable=False, trace_id='canary/restore')
                owner.restore_catalog.return_value = failure
                self.assertEqual(flow.verify_owners(examples()[ProtectionContext]), failure)
                components['canary'] = None
                self.assertEqual(flow.verify_owners(examples()[ProtectionContext]), original)
                self.assertFalse(any(Path(directory).iterdir()))


class CanaryTableFactoryTests(CanaryTableTests):
    def test_current_owner_factory_supplies_authority_and_error_precedes_codec(self):
        self.executor.canary_context_factory = Mock(return_value=self.check_context)
        result = self.executor.prepare(self.payload, self.plan, self.execution, self.context)
        from data_security.application.table_reports import ReportCandidate
        self.assertIsInstance(result, ReportCandidate)
        self.executor.canary_context_factory.assert_called_once_with(self.plan, self.execution, self.context)
        failure = ProtectionError(schema_version=ProtectionError.SCHEMA,
            code=ReasonCode.AUTHORIZATION_DENIED, retryable=False, trace_id='current/owner')
        self.executor.canary_context_factory.return_value = failure
        with patch.object(self.executor, 'codec_factory') as codec:
            self.assertEqual(self.executor.prepare(self.payload, self.plan, self.execution, self.context), failure)
            codec.assert_not_called()
