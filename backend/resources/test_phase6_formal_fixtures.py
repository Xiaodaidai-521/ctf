"""Real isolated owners shared by source tests and the ordinary-startup matrix."""
from dataclasses import replace
from datetime import timedelta
import hashlib
import json
import os
import subprocess
import sys
import time

from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.utils import timezone

from ctf_backend.security_bootstrap import assemble
from data_security.contracts import (
    Algorithm, AlgorithmSpec, Approval, Category, Environment, FrozenJSON, Location,
    LocationKind, Outlet, PolicyBinding, PolicyRule, PolicySnapshot, PolicyStatus,
    ProtectionContext, ProtectionError, Purpose, Replacement, ResolvedAction, Role,
    SheetScope, SourceDocument, SourceFormat, TableScope, content_hash,
)
from data_security.tests.phase3_fixtures import configuration
from export_risk.policies.catalog import policy_hash, resolve_policy
from tools.data_security import isolation
from users.models import CTFUser

from .serializers import ResourceUploadSerializer


CONTENT = b'Notes,Email\n=1+1,first@example.invalid\nrecord,second@example.invalid\n'


def source_inputs(**changes):
    algorithm = AlgorithmSpec(schema_version=AlgorithmSpec.SCHEMA,
        algorithm=Algorithm.REPLACE, version='v1', replacement=Replacement.EMAIL,
        keep_prefix=None, keep_suffix=None, mask_symbol=None, max_length=None,
        ipv4_prefix=None, pseudonym_bits=None, key_ref=None)
    values = dict(
        source=SourceDocument(schema_version=SourceDocument.SCHEMA,
            source_format=SourceFormat.COLUMN_V1, source_version='1', document=FrozenJSON({
                'version': '1', 'format': 'csv', 'scope': {'columns': ['Notes', 'Email']},
                'operations': [{'type': 'mask_columns', 'columns': ['Email'], 'value': '[EMAIL]'},
                               {'type': 'sanitize_formulas'}]})),
        scope=TableScope(schema_version=TableScope.SCHEMA,
            coordinate_version='source-codepoint-half-open.v1', sheets=(SheetScope(
                schema_version=SheetScope.SCHEMA, sheet_id='csv:0', column_ids=('c1', 'c2'),
                row_ranges=((1, 3),), includes_header=True),)),
        actions=tuple(ResolvedAction(schema_version=ResolvedAction.SCHEMA,
            action_id='email/' + str(row), source_operation_ref='operations/0',
            location=Location(schema_version=Location.SCHEMA, kind=LocationKind.CELL,
                sheet_id='csv:0', source_row=row, column_id='c2', start=None, end=None, json_path=()),
            category=Category.EMAIL, algorithm=algorithm, finding_refs=(), requirement_refs=())
            for row in (2, 3)),
        request_fields=FrozenJSON({'revision': '1', 'operation': 'export',
            'recipient_id': 'recipient/isolated', 'purpose': 'isolated delivery',
            'business_task_id': 'task/column-export', 'trace_id': 'trace/column-export'}),
        risk_inputs=FrozenJSON({}), expires_at=timezone.now() + timedelta(minutes=30))
    values.update(changes)
    return values


def create_original(entry, user):
    serializer = ResourceUploadSerializer(data={
        'title': '合成资料', 'description': '隔离测试资料', 'resource_type': 'document',
        'category': 'security',
        'file': SimpleUploadedFile('synthetic.txt', CONTENT, content_type='text/plain')})
    serializer.is_valid(raise_exception=True)
    return entry.uploads.create(serializer.validated_data, user=user)


class FormalResourceFixture:
    install_delivery_policy = False

    def setUp(self):
        self.assertEqual(connection.vendor, 'postgresql', 'requires isolated PostgreSQL')
        self.assertEqual(connection.settings_dict['NAME'], 'test_ds_phase1_main')
        files = configuration(providers=())
        self.config_path, self.config, _, _, binding = files.__enter__()
        self.addCleanup(files.__exit__, None, None, None)
        checkpoints = self.config_path.parent / 'checkpoints'
        checkpoints.mkdir(mode=0o700)
        self.root = self.config_path.parent / 'private'
        self.root.mkdir(mode=0o700)
        binding = replace(binding, risk_version='policy-m0', risk_hash=policy_hash(resolve_policy('policy-m0')))
        self.config.update(schema_version='ds.bootstrap.v2', policy_binding=binding.to_wire(),
            policy_repository={'kind': 'file', 'writable': self.install_delivery_policy},
            audit_chain={'chain_version': 'ds.audit.v2', 'project_ref': 'formal-column/synthetic',
                'object_uuid': '00000000-0000-0000-0000-000000000001', 'object_version': '1',
                'authorization_ref': 'authorization/synthetic-audit-owner', 'retained_keys': [],
                'checkpoint_root': str(checkpoints), 'checkpoint_ref': None},
            export_delivery={'private_root': str(self.root), 'project_ref': 'formal-column/synthetic',
                'window_key': 'formal-column', 'limit': 20, 'ttl_seconds': 300})
        self.write_config()
        self.teacher = CTFUser.objects.create_user(username='formal-column-requester', role='teacher')
        self.reviewer = CTFUser.objects.create_user(username='formal-column-reviewer', role='teacher', is_staff=True)
        self.policy_admin = CTFUser.objects.create_user(username='formal-column-policy-admin', role='admin')
        self.teacher.user_permissions.add(*Permission.objects.filter(content_type__app_label='resources',
            codename__in=('add_exportsource', 'view_exportsource')))
        self.teacher.user_permissions.add(Permission.objects.get(content_type__app_label='export_risk',
            codename='use_columnriskpermission'))
        for app, names in (
            ('resources', ('view_exportsource', 'change_exportsource', 'add_exportsourcepermission',
                           'change_exportsourcepermission')),
            ('export_risk', ('add_columnriskpermission', 'change_columnriskpermission')),
            ('security_policies', ('add_exportplanapproval', 'change_exportplanapproval')),
        ):
            self.reviewer.user_permissions.add(*Permission.objects.filter(
                content_type__app_label=app, codename__in=names))
        components = assemble(config_path=self.config_path)
        if self.install_delivery_policy:
            self._delivery_policy(components)
            components = assemble(config_path=self.config_path)
        self.entry = components['export_delivery']
        self.sources, self.risks = self.entry.sources, self.entry.risks
        self.binding = components['binding']
        self.gateway = components['audit']

    def write_config(self):
        self.config_path.write_text(json.dumps(self.config))
        self.config_path.chmod(0o600)

    def _delivery_policy(self, components):
        now = timezone.now()
        effective = now + timedelta(seconds=1)
        rule = PolicyRule(schema_version=PolicyRule.SCHEMA, category=Category.EMAIL,
            outlet=Outlet.EXPORT, role=Role.TEACHER, purpose=Purpose.DELIVERY,
            action=source_inputs()['actions'][0].algorithm)
        fields = dict(schema_version=PolicySnapshot.SCHEMA, version='formal-column/isolated-v1',
            rules=(rule,), teaching_exceptions=(), effective_at=effective,
            expires_at=now + timedelta(hours=1))
        draft = PolicySnapshot(**fields, status=PolicyStatus.DRAFT, approval=None, content_hash=content_hash(fields))
        principal = ProtectionContext(schema_version=ProtectionContext.SCHEMA,
            actor_ref='user/' + str(self.policy_admin.pk), authorization_ref='authorization/isolated-policy-manager',
            scope_refs=('policy/manage',), environment=Environment.EVALUATION, domain='ctf',
            outlet=Outlet.API, purpose=Purpose.SECURITY_AUDIT, role=Role(self.policy_admin.role),
            object_ref='policy/isolated', object_version=draft.version, source_ref=None,
            source_version=None, source_hash=None, trace_id='policy/isolated-draft')
        self.ok(components['catalog'].save_draft(draft, components['binding'].protection_version, principal))
        approval = Approval(schema_version=Approval.SCHEMA, approval_ref='policy/isolated-approval',
            requested_by='user/' + str(self.teacher.pk), approved_by=principal.actor_ref,
            approved_at=timezone.now(), content_hash=draft.content_hash)
        approved = self.ok(components['catalog'].approve(draft, approval,
            replace(principal, trace_id='policy/isolated-approve')))
        self.config['policy_binding'] = replace(components['binding'],
            protection_version=approved.version, protection_hash=approved.content_hash).to_wire()
        self.write_config()
        while timezone.now() < effective:
            time.sleep(0.01)

    def ok(self, value):
        self.assertNotIsInstance(value, ProtectionError)
        return value

    def original(self):
        return self.ok(create_original(self.entry, self.teacher))

    def register(self, resource=None, **changes):
        resource = resource or self.original()
        return self.sources.register(user=self.teacher, resource_id=resource.pk, **source_inputs(**changes))

    def approved_source(self, *, expires_at=None, **changes):
        source_ref, _ = self.ok(self.register(**changes))
        self.ok(self.sources.approve(user=self.reviewer, source_ref=source_ref))
        permission_ref, _ = self.ok(self.sources.grant(user=self.reviewer, source_ref=source_ref,
            grantee_id=self.teacher.pk, expires_at=expires_at or timezone.now() + timedelta(minutes=20)))
        return source_ref, permission_ref

    def ready(self):
        source_ref, permission_ref = self.approved_source()
        risk_ref, _ = self.ok(self.entry.grant_risk(user=self.reviewer, source_ref=source_ref,
            expires_at=timezone.now() + timedelta(minutes=20)))
        _, decision_id, blocker = self.ok(self.entry.admit(user=self.teacher, source_ref=source_ref,
            permission_ref=permission_ref, risk_permission_ref=risk_ref))
        self.assertIsNotNone(blocker)
        self.ok(self.risks.approve(user=self.reviewer, permission_ref=risk_ref, decision_id=decision_id))
        binding = self.ok(self.entry.bind(user=self.teacher, source_ref=source_ref,
            permission_ref=permission_ref, risk_permission_ref=risk_ref))
        self.ok(self.entry.approve_target(user=self.reviewer, source_ref=source_ref, requester=self.teacher))
        return source_ref, permission_ref, risk_ref, binding


def formal_call(test, operation, **fields):
    """Only django.setup binds delivery in the child; all authority is re-fetched there."""
    env = isolation.clean_env()
    env.update(DATA_SECURITY_CONFIG=str(test.config_path), DATA_SECURITY_ISOLATED_TEST='1',
        DJANGO_SETTINGS_MODULE='tools.data_security.test_settings',
        DS_TEST_PG_PORT=os.environ['DS_TEST_PG_PORT'], DS_TEST_PG_SOCKET=os.environ['DS_TEST_PG_SOCKET'],
        ALLOWED_HOSTS='testserver,localhost', DEBUG='false')
    test.assertEqual(connection.settings_dict['NAME'], 'test_ds_phase1_main')
    code = '''
import json,sys
from pathlib import Path
sys.path[:0] = [str(Path.cwd()), str(Path.cwd() / 'backend')]
from django.conf import settings
assert sys.argv[1] == 'test_ds_phase1_main'
settings.DATABASES['default']['NAME'] = sys.argv[1]
import django
django.setup()
from django.db import connection
assert connection.settings_dict['NAME'] == 'test_ds_phase1_main'
from resources.test_phase6_formal_delivery import invoke_formal
value = invoke_formal(sys.argv[2], json.loads(sys.argv[3]))
print(json.dumps(value))
connection.close()
'''
    result = subprocess.run([sys.executable, '-I', '-B', '-c', code, 'test_ds_phase1_main',
        operation, json.dumps({'user': test.teacher.pk, 'reviewer': test.reviewer.pk, **fields})],
        cwd=isolation.ROOT, env=env, capture_output=True, timeout=90)
    test.assertEqual(result.returncode, 0, 'ordinary delivery startup failed: ' +
        result.stderr.decode(errors='replace')[-3000:])
    return json.loads(result.stdout)
