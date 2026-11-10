"""Phase-six additions do not expand the frozen dependency matrix."""
from pathlib import Path
import tempfile
import unittest

from tools.data_security.dependencies import (
    ALLOWED, PHASE5_MODULES, PHASE6_MODULES, PHASE6_EXTERNAL, check_source, scan,
)


class Phase6DependencyTests(unittest.TestCase):
    def test_declared_source_grants_are_valid_and_narrow(self):
        for module, targets in PHASE6_EXTERNAL.items():
            source = 'backend/' + module.replace('.', '/') + '.py'
            for target in targets:
                with self.subTest(module=module, target=target):
                    self.assertFalse(check_source(source, 'import ' + target, phase=6))
        for name in ('quota', 'uow', 'risk', 'private_store', 'report_records', 'recovery'):
            source = 'backend/data_security/adapters/persistence/' + name + '.py'
            for target in ('export_quota.models', 'export_risk.models', 'requests', 'django.http',
                           'data_security.core.crypto', 'data_security.adapters.keys'):
                self.assertTrue(check_source(source, 'import ' + target, phase=6))

    def test_flow_and_http_cannot_import_persistence_or_quota_domain(self):
        self.assertEqual(ALLOWED['M4'], {'M0', 'M1', 'M2', 'M3', 'M4'})
        self.assertEqual(ALLOWED['M6'], {'M0', 'M6'})
        for source in ('backend/data_security/application/export_flow.py',
                       'backend/data_security/adapters/django/delivery.py'):
            for target in ('data_security.adapters.persistence.quota', 'export_quota.services',
                           'export_risk.decisions.service', 'django.db.transaction'):
                self.assertTrue(check_source(source, 'import ' + target, phase=6))

    def test_recovery_http_only_consumes_injected_flow_and_risk_grant_is_exact(self):
        source = 'backend/data_security/adapters/django/export_recovery.py'
        self.assertFalse(check_source(source, 'from rest_framework.response import Response', phase=6))
        for target in ('django.db', 'data_security.adapters.persistence.report_records',
                       'data_security.application.export_flow', 'export_quota.services', 'audit.models'):
            self.assertTrue(check_source(source, 'import ' + target, phase=6))
        statement = 'from export_risk.decisions.service import recheck_delivered'
        self.assertFalse(check_source('backend/data_security/adapters/persistence/risk.py', statement, phase=6))
        for module in ('quota', 'report_records', 'private_store', 'recovery'):
            self.assertTrue(check_source('backend/data_security/adapters/persistence/' + module + '.py',
                                         statement, phase=6))

    def test_canary_runtime_uses_only_injected_contracts(self):
        source = 'backend/data_security/adapters/django/canary_tools.py'
        self.assertFalse(check_source(source, 'from data_security.contracts import CanaryCheckPort', phase=6))
        for target in ('data_security.application.canary', 'data_security.adapters.persistence.models',
                       'agent_runtime.models', 'django.db.transaction', 'threading', 'subprocess'):
            self.assertTrue(check_source(source, 'import ' + target, phase=6))

    def test_upload_boundary_has_only_parser_and_memory_capabilities(self):
        source = 'backend/data_security/adapters/django/uploads.py'
        self.assertFalse(check_source(source, 'from io import BytesIO', phase=6))
        for target in ('tempfile', 'os', 'pathlib', 'subprocess', 'threading',
                       'django.core.files.storage', 'django.db.transaction',
                       'data_security.adapters.persistence.private_store',
                       'data_security.application.export_flow'):
            self.assertTrue(check_source(source, 'import ' + target, phase=6))
        self.assertTrue(check_source('backend/data_security/application/export_flow.py',
                                    'from io import BytesIO', phase=6))

    def test_private_file_preparation_has_no_storage_or_business_imports(self):
        source = 'backend/data_security/application/private_files.py'
        self.assertFalse(check_source(source, 'from data_security.contracts import StoredObject', phase=6))
        for target in ('django.db', 'resources.private_uploads', 'data_security.adapters.persistence.private_store',
                       'export_quota.services', 'export_risk.decisions.service', 'os', 'io', 'tempfile'):
            self.assertTrue(check_source(source, 'import ' + target, phase=6))

    def test_resource_upload_owner_and_serializer_only_consume_contracts(self):
        for source in ('backend/resources/private_uploads.py', 'backend/resources/serializers.py'):
            self.assertFalse(check_source(source, 'from data_security.contracts import ProtectionError', phase=6))
            for target in ('data_security.application.private_files', 'data_security.adapters.persistence.private_store',
                           'data_security.core.crypto', 'ctf_backend.security_bootstrap'):
                self.assertTrue(check_source(source, 'import ' + target, phase=6))
        self.assertTrue(check_source('backend/ctf_backend/security_bootstrap.py',
            'from resources.private_uploads import UnapprovedOwner', phase=6))
        self.assertTrue(check_source('backend/data_security/adapters/django/uploads.py',
            'from resources.private_uploads import ResourcePrivateUploads', phase=6))

    def test_feedback_owner_and_view_only_consume_contracts(self):
        for source in ('backend/feedback_center/private_uploads.py', 'backend/feedback_center/views.py'):
            self.assertFalse(check_source(source, 'from data_security.contracts import ProtectionError', phase=6))
            for target in ('data_security.application.private_files', 'data_security.adapters.persistence.private_store',
                           'data_security.core.crypto', 'ctf_backend.security_bootstrap'):
                self.assertTrue(check_source(source, 'import ' + target, phase=6))
        self.assertTrue(check_source('backend/ctf_backend/security_bootstrap.py',
            'from feedback_center.private_uploads import UnapprovedOwner', phase=6))
        self.assertTrue(check_source('backend/data_security/adapters/django/uploads.py',
            'from feedback_center.private_uploads import FeedbackPrivateUploads', phase=6))
        self.assertTrue(check_source('backend/data_security/application/private_files.py',
            'from feedback_center.private_uploads import FeedbackPrivateUploads', phase=6))

    def test_recovery_permission_owner_does_not_reach_quota_or_storage(self):
        source = 'backend/audit/recovery_permissions.py'
        self.assertFalse(check_source(source, 'from data_security.contracts import ProtectionContext', phase=6))
        for target in ('data_security.adapters.persistence.recovery', 'data_security.application.export_flow',
                       'data_security.core.crypto', 'ctf_backend.security_bootstrap'):
            self.assertTrue(check_source(source, 'import ' + target, phase=6))
        self.assertTrue(check_source('backend/data_security/adapters/persistence/recovery.py',
            'from users.models import CTFUser', phase=6))
        self.assertTrue(check_source('backend/ctf_backend/security_bootstrap.py',
            'from audit.recovery_permissions import UnapprovedOwner', phase=6))

    def test_legacy_archive_grants_are_exact_and_do_not_add_a_chain_writer(self):
        source = 'backend/data_security/adapters/persistence/legacy_archive.py'
        for statement in ('from django.db.models import Q', 'from audit.services import AuditLedgerService',
                          'from contextlib import suppress', 'import subprocess'):
            self.assertFalse(check_source(source, statement, phase=6))
        for target in ('audit.models.AuthenticatedAuditEntry', 'audit.models.AuditEvent',
                       'django.http', 'requests', 'data_security.application.audit_gateway',
                       'data_security.adapters.keys', 'threading', 'tempfile'):
            self.assertTrue(check_source(source, 'import ' + target, phase=6))
        for phase in (3, 4, 5):
            self.assertTrue(check_source(source, 'from audit.services import AuditLedgerService', phase=phase))

    def test_legacy_archive_owner_and_flow_keep_storage_and_chain_writers_in_m6(self):
        owner = 'backend/audit/legacy_archives.py'
        self.assertFalse(check_source(owner, 'from data_security.contracts import ProtectionContext', phase=6))
        for target in ('data_security.adapters.persistence.legacy_archive', 'data_security.application.legacy_archive',
                       'ctf_backend.security_bootstrap'):
            self.assertTrue(check_source(owner, 'import ' + target, phase=6))
        flow = 'backend/data_security/application/legacy_archive.py'
        for target in ('django.db', 'audit.models', 'data_security.adapters.persistence.legacy_archive',
                       'os', 'pathlib', 'subprocess'):
            self.assertTrue(check_source(flow, 'import ' + target, phase=6))
        self.assertTrue(check_source('backend/ctf_backend/security_bootstrap.py',
            'from audit.legacy_archives import UnapprovedOwner', phase=6))

    def test_target_approval_owner_and_storage_cannot_own_execution_or_sources(self):
        owner = 'backend/audit/export_plans.py'
        self.assertFalse(check_source(owner, 'from data_security.contracts import Approval', phase=6))
        for target in ('data_security.application.export_flow', 'data_security.adapters.persistence.export_plans',
                       'ctf_backend.security_bootstrap'):
            self.assertTrue(check_source(owner, 'import ' + target, phase=6))
        source = 'backend/data_security/adapters/persistence/export_plans.py'
        for target in ('export_quota.services', 'export_risk.models', 'users.models',
                       'data_security.application.export_flow', 'django.http', 'os', 'pathlib'):
            self.assertTrue(check_source(source, 'import ' + target, phase=6))
        self.assertTrue(check_source('backend/ctf_backend/security_bootstrap.py',
            'from audit.export_plans import UnapprovedOwner', phase=6))

    def test_formal_source_and_conditional_risk_owners_keep_only_contract_edges(self):
        for source in ('backend/resources/export_sources.py', 'backend/export_risk/column_authority.py'):
            self.assertFalse(check_source(source, 'from data_security.contracts import SourceDocument', phase=6))
            for target in ('data_security.application.export_flow', 'data_security.adapters.persistence.risk',
                           'data_security.adapters.tabular.source_plans', 'data_security.core.crypto',
                           'ctf_backend.security_bootstrap'):
                self.assertTrue(check_source(source, 'import ' + target, phase=6))
            for phase in (3, 4, 5):
                self.assertTrue(check_source(source, 'from data_security.contracts import SourceDocument', phase=phase))
        bootstrap = 'backend/ctf_backend/security_bootstrap.py'
        for target in ('resources.export_sources.UnapprovedOwner', 'export_risk.column_authority.UnapprovedOwner',
                       'export_risk.models.RiskDecision'):
            self.assertTrue(check_source(bootstrap, 'import ' + target, phase=6))

    def test_formal_supplier_cannot_import_flow_or_business_writers(self):
        source = 'backend/data_security/adapters/persistence/export_delivery.py'
        self.assertFalse(check_source(source, 'from export_risk.column_authority import decode_request', phase=6))
        for target in ('data_security.application.export_flow', 'data_security.adapters.tabular.source_plans',
                       'export_quota.services', 'export_risk.decisions.service', 'export_risk.models',
                       'django.http', 'requests', 'data_security.adapters.keys'):
            self.assertTrue(check_source(source, 'import ' + target, phase=6))
        for module in ('quota', 'report_records', 'private_store', 'recovery'):
            self.assertTrue(check_source('backend/data_security/adapters/persistence/' + module + '.py',
                'from export_risk.column_authority import decode_request', phase=6))
        boundary = 'backend/data_security/adapters/django/export_delivery.py'
        self.assertFalse(check_source(boundary, 'from data_security.contracts import ProtectionError', phase=6))
        for target in ('data_security.adapters.persistence.export_delivery', 'resources.export_sources',
                       'export_risk.column_authority', 'data_security.application.export_flow', 'django.db'):
            self.assertTrue(check_source(boundary, 'import ' + target, phase=6))

    def test_closed_ingress_has_only_http_and_script_prefix_capabilities(self):
        source = 'backend/data_security/adapters/django/private_ingress.py'
        for target in ('tempfile', 'io', 'os', 'pathlib', 'threading', 'django.db',
                       'data_security.application.private_files', 'resources.private_uploads',
                       'data_security.adapters.persistence.private_store'):
            self.assertTrue(check_source(source, 'import ' + target, phase=6))

    def test_asgi_bootstrap_grant_is_exact_and_only_phase_six(self):
        source = 'backend/ctf_backend/asgi.py'
        statement = 'from .security_bootstrap import guard_private_upload_asgi'
        self.assertFalse(check_source(source, statement, phase=6))
        for phase in (1, 2, 3, 4, 5):
            self.assertTrue(check_source(source, statement, phase=phase))
        for target in ('assemble', 'start_application', 'private_upload_middleware'):
            self.assertTrue(check_source(source, 'from .security_bootstrap import ' + target, phase=6))
        self.assertTrue(check_source('backend/resources/views.py',
            'from ctf_backend.security_bootstrap import guard_private_upload_asgi', phase=6))

    def test_executor_preparation_owner_only_consumes_contracts(self):
        source = 'tasks/controlled-export-execution/controlled_export/services.py'
        self.assertFalse(check_source(source, 'from data_security.contracts import BoundedPayload, ObjectContext', phase=6))
        for target in ('data_security.application.private_files', 'data_security.adapters.persistence.private_store',
                       'data_security.adapters.persistence.models', 'data_security.adapters.keys',
                       'data_security.application.export_flow', 'ctf_backend.security_bootstrap'):
            self.assertTrue(check_source(source, 'import ' + target, phase=6))

    def test_sixth_phase_modules_are_not_backported(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for module in PHASE6_MODULES - PHASE5_MODULES:
                path = root / ('backend/' + module.replace('.', '/') + '.py')
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('from data_security.contracts import ProtectionError\n')
            self.assertEqual(scan(root, phase=6)[1], [])
            self.assertIn('PHASE5_FUTURE_IMPLEMENTATION', {v.code for v in scan(root, phase=5)[1]})

    def test_future_modules_and_indirect_imports_remain_closed(self):
        source = 'backend/ctf_backend/security_bootstrap.py'
        for statement in ('from data_security.adapters.persistence import future',
                          'from data_security.adapters.persistence.quota.future import Port',
                          'import importlib\nimportlib.import_module("export_quota.models")'):
            self.assertTrue(check_source(source, statement, phase=6))
