"""The same policy repository contract runs against files and isolated PostgreSQL."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.db import DatabaseError, connection, connections
from django.test import TransactionTestCase

from data_security.adapters.persistence.models import PolicyVersion
from data_security.adapters.persistence.orm_policies import ORMPolicyRepository
from data_security.adapters.persistence.policies import FilePolicyRepository
from data_security.application.policy_catalog import PolicyCatalog
from data_security.contracts import (Environment, PolicyStatus, ProtectionError, Purpose,
    ReasonCode, Role, content_hash)
from data_security.tests.fixtures import AT, approval
from data_security.tests.phase2_fixtures import MemoryAudit, context, policy
from data_security.tests.phase3_fixtures import configuration


def next_policy(snapshot, version):
    content = {**snapshot.content(), 'version': version}
    return replace(snapshot, version=version, content_hash=content_hash(content),
                   status=PolicyStatus.DRAFT, approval=None)


class RepositoryContract:
    def setUp(self):
        super().setUp()
        self.approved, self.binding = policy()
        self.draft = replace(self.approved, status=PolicyStatus.DRAFT, approval=None)
        self.repo = self.make_repository()
        self.catalog = PolicyCatalog(repository=self.repo, clock=lambda: AT)

    def test_missing_and_unapproved_are_closed(self):
        self.assertIsInstance(self.repo.read(self.binding), ProtectionError)
        self.assertIs(self.repo.put(self.draft, None), True)
        self.assertEqual(self.repo.read(self.binding), self.draft)
        self.assertEqual(self.catalog.snapshot(self.binding).code, ReasonCode.POLICY_NOT_APPROVED)

    def test_pinned_versions_survive_append(self):
        self.assertIs(self.repo.put(self.approved, None), True)
        newer = next_policy(self.draft, 'policy-v2')
        self.assertIs(self.repo.put(newer, self.draft.version), True)
        self.assertEqual(self.catalog.snapshot(self.binding), self.approved)
        wrong_hash = replace(self.binding, protection_hash='0' * 64)
        self.assertIsInstance(self.repo.read(wrong_hash), ProtectionError)

    def test_content_cannot_change_under_same_version(self):
        self.assertIs(self.repo.put(self.draft, None), True)
        content = {**self.draft.content(), 'expires_at': self.draft.expires_at + timedelta(hours=1)}
        changed = replace(self.draft, expires_at=content['expires_at'], content_hash=content_hash(content))
        self.assertEqual(self.repo.put(changed, self.draft.version).code, ReasonCode.IDEMPOTENCY_CONFLICT)
        self.assertEqual(self.repo.read(self.binding), self.draft)

    def test_lifecycle_and_idempotency(self):
        self.assertIs(self.repo.put(self.draft, None), True)
        self.assertIs(self.repo.put(self.draft, self.draft.version), True)
        self.assertIs(self.repo.put(self.approved, self.draft.version), True)
        retired = replace(self.approved, status=PolicyStatus.RETIRED)
        self.assertIs(self.repo.put(retired, self.draft.version), True)
        self.assertEqual(self.catalog.snapshot(self.binding).code, ReasonCode.POLICY_NOT_APPROVED)
        self.assertEqual(self.repo.put(self.approved, self.draft.version).code, ReasonCode.IDEMPOTENCY_CONFLICT)

    def test_expiry_is_checked_on_each_request(self):
        self.assertIs(self.repo.put(self.approved, None), True)
        self.assertEqual(self.catalog.snapshot(self.binding), self.approved)
        self.catalog.clock = lambda: self.approved.expires_at
        self.assertEqual(self.catalog.snapshot(self.binding).code, ReasonCode.AUTHORIZATION_EXPIRED)

    def test_two_writers_cannot_both_advance_same_version(self):
        self.assertIs(self.repo.put(self.draft, None), True)
        def write(version):
            try:
                return self.repo.put(next_policy(self.draft, version), self.draft.version)
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(write, ('policy-v2', 'policy-v3')))
        self.assertEqual(sum(result is True for result in results), 1)
        self.assertEqual([result.code for result in results if type(result) is ProtectionError],
                         [ReasonCode.IDEMPOTENCY_CONFLICT])

    def test_management_authorization_and_durable_intent(self):
        admin = replace(context(), environment=Environment.EVALUATION, role=Role.ADMIN,
            purpose=Purpose.SECURITY_AUDIT, scope_refs=('policy/manage',), actor_ref='user/approver')
        audit = MemoryAudit()
        catalog = PolicyCatalog(repository=self.repo, clock=lambda: AT, management=True, audit=audit)
        self.assertEqual(catalog.save_draft(self.draft, None, admin), self.draft)
        granted = approval(self.draft.content_hash)
        granted = replace(granted, approved_by=admin.actor_ref)
        self.assertIsInstance(catalog.approve(self.draft, granted, replace(admin, role=Role.TEACHER)), ProtectionError)
        approved = catalog.approve(self.draft, granted, admin)
        self.assertEqual(approved.status, PolicyStatus.APPROVED)
        self.assertEqual(len(audit.events), 4)
        self.assertEqual(catalog.retire(self.binding, admin).status, PolicyStatus.RETIRED)
        self.assertIsInstance(catalog.snapshot(self.binding), ProtectionError)

    def test_audit_failure_does_not_store(self):
        admin = replace(context(), environment=Environment.EVALUATION, role=Role.ADMIN,
            purpose=Purpose.SECURITY_AUDIT, scope_refs=('policy/manage',))
        catalog = PolicyCatalog(repository=self.repo, clock=lambda: AT, management=True, audit=MemoryAudit(reject=True))
        self.assertEqual(catalog.save_draft(self.draft, None, admin).code, ReasonCode.AUDIT_UNAVAILABLE)
        self.assertIsInstance(self.repo.read(self.binding), ProtectionError)


class FileRepositoryTests(RepositoryContract, TransactionTestCase):
    def make_repository(self):
        temporary = TemporaryDirectory(prefix='ds-phase4-policy-', dir='/tmp')
        self.addCleanup(temporary.cleanup)
        return FilePolicyRepository(path=Path(temporary.name) / 'policies.json', writable=True)

    def test_legacy_file_remains_readonly_by_default(self):
        self.repo.path.write_text(json.dumps(self.approved.to_wire()))
        self.repo.path.chmod(0o600)
        readonly = FilePolicyRepository(path=self.repo.path)
        self.assertEqual(readonly.read(self.binding), self.approved)
        self.assertEqual(readonly.put(self.draft, self.approved.version).code, ReasonCode.AUTHORIZATION_DENIED)


class ORMRepositoryTests(RepositoryContract, TransactionTestCase):
    def make_repository(self):
        self.assertEqual(connection.vendor, 'postgresql')
        return ORMPolicyRepository(writable=True)

    def test_database_failure_never_reads_file(self):
        from ctf_backend.security_bootstrap import assemble
        with configuration(providers=()) as (path, config, refs, values, binding):
            config.update(schema_version='ds.bootstrap.v2', policy_file=None,
                          policy_repository={'kind': 'orm', 'writable': True})
            path.write_text(json.dumps(config))
            with patch.object(PolicyVersion.objects, 'filter', side_effect=DatabaseError('synthetic-failure')):
                with patch.object(FilePolicyRepository, 'read') as fallback:
                    with self.assertRaisesRegex(Exception, 'POLICY_NOT_APPROVED'):
                        assemble(config_path=path)
                    fallback.assert_not_called()

    def test_composition_selects_orm_without_changing_application(self):
        from ctf_backend.security_bootstrap import assemble
        from data_security.contracts import PolicySnapshot
        with configuration(providers=()) as (path, config, refs, values, binding):
            snapshot = PolicySnapshot.from_json(Path(config['policy_file']).read_bytes())
            self.assertIs(self.repo.put(snapshot, None), True)
            config.update(schema_version='ds.bootstrap.v2', policy_file=None,
                          policy_repository={'kind': 'orm', 'writable': True})
            path.write_text(json.dumps(config))
            components = assemble(config_path=path)
            self.assertIsInstance(components['catalog'].repository, ORMPolicyRepository)
            self.assertEqual(components['catalog'].snapshot(binding), snapshot)
