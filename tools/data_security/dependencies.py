"""Static import rules for the V2 module matrix; prints locations, never source text."""
import argparse
import ast
from dataclasses import dataclass
import json
from pathlib import Path
import sys
import warnings

PURE_STDLIB = frozenset({'base64', 'collections', 'dataclasses', 'datetime', 'enum', 'functools',
                        'hashlib', 'hmac', 'json', 'math', 're', 'types', 'typing', 'uuid'})
ALLOWED = {
    'M0': {'M0'}, 'M1': {'M0', 'M1', 'M3'}, 'M2': {'M0', 'M2'}, 'M3': {'M0', 'M3'},
    'M4': {'M0', 'M1', 'M2', 'M3', 'M4'}, 'M5': {'M0', 'M5'}, 'M6': {'M0', 'M6'},
    'M7': {'M0', 'M7'}, 'M8': {'M0', 'M8'}, 'M9': {'M0', 'M9'},
    'B': {'M0', 'M1', 'M2', 'M3', 'M4', 'M5', 'M6', 'M7', 'M8', 'M9', 'B'},
}
EXTERNAL = {
    'M0': set(), 'M1': set(), 'M2': set(), 'M3': {'cryptography'}, 'M4': set(),
    'M5': set(),
    'M6': {'django', 'audit', 'export_risk', 'export_quota', 'users', 'resources', 'feedback_center',
           'legal', 'legal_kb', 'rag_ingestion', 'learning_map', 'skill_review'},
    'M7': {'httpx', 'requests', 'openai', 'anthropic'},
    'M8': {'openpyxl', 'defusedxml'}, 'M9': {'django', 'rest_framework', 'httpx', 'requests'},
    'B': {'django', 'cryptography', 'openpyxl', 'httpx', 'requests', 'openai', 'anthropic'},
}
LEGACY_PORTS = ('mainline1.parsing', 'mainline1.planning', 'controlled_export.transformations')
BOOTSTRAP_MODULES = ('ctf_backend.security_bootstrap', 'controlled_export_service.security_bootstrap',
                     'tasks.controlled-export-execution.controlled_export_service.security_bootstrap')
PHASE2_MODULES = frozenset({
    'data_security.core', 'data_security.core.crypto', 'data_security.core.redaction', 'data_security.core.policy',
    'data_security.application', 'data_security.application.protection', 'data_security.application.crypto_service',
    'data_security.adapters', 'data_security.adapters.tabular', 'data_security.adapters.tabular.legacy',
    'data_security.adapters.django', 'data_security.adapters.django.legacy', 'ctf_backend.security_bootstrap',
})
PHASE2_LEGACY = {
    'mainline1.rules': ('data_security.contracts', 'data_security.adapters.tabular.legacy'),
    'ai_assistant.security': ('data_security.contracts', 'data_security.adapters.django.legacy'),
    'legal.services.fact_redactor': ('data_security.contracts', 'data_security.adapters.django.legacy'),
}
# Phase 3 is additive in inventory, not in the dependency matrix. Source-module
# keys intentionally avoid granting every adapter the same SDK/domain privileges.
PHASE3_MODULES = PHASE2_MODULES | frozenset({
    'data_security.adapters.keys', 'data_security.adapters.persistence',
    'data_security.adapters.persistence.policies', 'data_security.adapters.persistence.audit',
    'data_security.adapters.persistence.backup', 'data_security.application.policy_catalog',
    'data_security.application.audit_gateway', 'data_security.adapters.llm',
    'data_security.adapters.llm.official', 'data_security.adapters.django.authentication',
    'data_security.adapters.django.logging', 'data_security.adapters.django.content',
    'data_security.adapters.django.execution',
})
PHASE3_PACKAGES = frozenset({
    'data_security.core', 'data_security.application', 'data_security.adapters',
    'data_security.adapters.persistence', 'data_security.adapters.llm',
    'data_security.adapters.tabular', 'data_security.adapters.django',
})
PHASE3_LEGACY = {
    **PHASE2_LEGACY,
    'ai_providers': ('data_security.contracts',),
    'audit.bridge': ('data_security.contracts',),
    'audit.services': ('data_security.contracts',),
    'export_risk.decisions.outbox': ('data_security.contracts',),
    'ctfsafe.encryption': ('data_security.contracts',),
    'users.management.commands.bootstrap_teacher': ('data_security.adapters.django.authentication',),
    'agents.context.teaching_context': ('data_security.adapters.django.content',),
    'ai_assistant.service': ('data_security.adapters.django.content',),
    'ai_assistant.prompt_budget': ('data_security.adapters.django.content',),
    'agents.context.student_profile_adapter': ('data_security.adapters.django.content',),
    'agents.specialists.knowledge_agent': ('data_security.adapters.django.content',),
    'agents.specialists.knowledge_diagnosis_agent': ('data_security.adapters.django.content',),
    'agents.specialists.study_strategy_agent': ('data_security.adapters.django.content',),
    'legal.services.compliance_agent': ('data_security.adapters.django.content',),
    'legal_kb.services.rag_answer_service': ('data_security.adapters.django.content',),
}
PHASE3_STARTUP = {
    'ctf_backend.settings': {'ctf_backend.security_bootstrap.framework_startup',
                             'ctf_backend.security_bootstrap.startup_database_url',
                             'ctf_backend.security_bootstrap.startup_secret'},
    'ctf_backend.apps': {'ctf_backend.security_bootstrap.start_application'},
}
PHASE3_EXTERNAL = {
    'data_security.adapters.persistence.audit': {
        'django.db.DatabaseError', 'django.db.transaction',
        'audit.models.AuditEvent', 'audit.models.AuditLedgerEntry',
        'audit.models.AuditLedgerLock', 'audit.models.SecurityAuditRecord',
        'audit.services.AuditLedgerService',
    },
    'data_security.adapters.persistence.backup': {'psycopg2'},
    'data_security.adapters.llm.official': {'requests', 'websockets.sync.client.connect', 'urllib.parse.urlencode'},
    'data_security.adapters.django.execution': {'django.db.connections'},
    'data_security.adapters.django.authentication': {
        'django.core.management.base.CommandError',
        'rest_framework.authentication.BaseAuthentication',
        'rest_framework.authentication.get_authorization_header',
        'rest_framework.exceptions.AuthenticationFailed',
    },
    'ctf_backend.security_bootstrap': {
        'django.conf.settings', 'rest_framework.settings.api_settings', 'rest_framework.views.APIView',
        'rest_framework.authentication.SessionAuthentication',
        'ai_providers.MultiProviderManager', 'ai_providers.ProviderHandle', 'ai_providers.bind_manager',
        'ai_assistant.security.sanitize_output',
        'audit.bridge', 'audit.bridge.bind', 'export_risk.decisions.outbox', 'export_risk.decisions.outbox.bind',
        'ctfsafe.encryption.bind_field_crypto', 'challenges.views.ProxySessionAuthentication',
        'challenges.views.proxy_challenge_view',
    },
}
PHASE3_IO_STDLIB = {
    'data_security.adapters.keys': {'os', 'pathlib', 'stat'},
    'data_security.adapters.persistence.policies': {'pathlib', 'stat'},
    'data_security.adapters.persistence.backup': {'os', 'pathlib', 'shutil', 'struct', 'subprocess', 'contextlib'},
    'data_security.adapters.django.logging': {'logging'},
    'data_security.adapters.django.execution': {'asyncio', 'concurrent'},
    'ctf_backend.security_bootstrap': {'os', 'pathlib', 'secrets'},
}
PHASE4_MODULES = PHASE3_MODULES | frozenset({
    'data_security.adapters.persistence.apps', 'data_security.adapters.persistence.models',
    'data_security.adapters.persistence.policy_writes', 'data_security.adapters.persistence.orm_policies',
    'data_security.adapters.persistence.migrations',
    'data_security.adapters.persistence.migrations.0001_policyversion',
    'data_security.adapters.django.policy_api', 'data_security.adapters.persistence.fields',
    'data_security.adapters.persistence.field_migration',
    'data_security.adapters.persistence.field_rotation',
})
PHASE4_PACKAGES = PHASE3_PACKAGES | {'data_security.adapters.persistence.migrations'}
PHASE4_LEGACY = {
    **PHASE3_LEGACY,
    'users.models': ('data_security.adapters.persistence.fields',),
    'users.serializers': ('data_security.adapters.persistence.fields',),
    'exams.serializers': ('data_security.adapters.persistence.fields',),
    'submissions.serializers': ('data_security.adapters.persistence.fields',),
    'challenges.admin': ('data_security.adapters.persistence.fields',),
    'users.admin': ('data_security.adapters.persistence.fields',),
    'submissions.admin': ('data_security.adapters.persistence.fields',),
    'exams.admin': ('data_security.adapters.persistence.fields',),
    'legal.models': ('data_security.adapters.persistence.fields',),
    'legal.admin': ('data_security.adapters.persistence.fields',),
    'legal.serializers': ('data_security.adapters.persistence.fields',),
    'legal.views': ('data_security.adapters.persistence.fields',),
    'legal.services.data_access': ('data_security.adapters.persistence.fields',),
    'legal.services.compliance_orchestrator': ('data_security.adapters.persistence.fields',),
    'legal.services.exercise_fact_builder': ('data_security.adapters.persistence.fields',),
    'users.views': ('data_security.adapters.persistence.fields', 'data_security.contracts'),
    'ai_assistant.models': ('data_security.adapters.persistence.fields',),
    'ai_assistant.views': ('data_security.adapters.persistence.fields',),
    'agent_runtime.models': ('data_security.adapters.persistence.fields',),
    'challenges.models': ('data_security.adapters.persistence.fields',),
    'exams.models': ('data_security.adapters.persistence.fields',),
    'submissions.models': ('data_security.adapters.persistence.fields',),
    'submissions.views': ('data_security.adapters.persistence.fields',),
    'audit.models': ('data_security.adapters.persistence.fields',),
    'audit.views': ('data_security.adapters.persistence.fields',),
    'audit.serializers': ('data_security.adapters.persistence.fields',),
    'audit.admin': ('data_security.adapters.persistence.fields',),
    'student_profiles.models': ('data_security.adapters.persistence.fields',),
    'student_profiles.admin': ('data_security.adapters.persistence.fields',),
    'student_profiles.views': ('data_security.adapters.persistence.fields',),
    'student_profiles.serializers': ('data_security.adapters.persistence.fields',),
    'student_profiles.onboarding_service': ('data_security.adapters.persistence.fields',),
    'student_profiles.persona_service': ('data_security.adapters.persistence.fields',),
    'student_profiles.growth_service': ('data_security.adapters.persistence.fields',),
}
PHASE4_EXTERNAL = {
    **PHASE3_EXTERNAL,
    'data_security.adapters.django.policy_api': {'django.urls.path', 'rest_framework.decorators.api_view',
        'rest_framework.decorators.permission_classes', 'rest_framework.permissions.IsAuthenticated',
        'rest_framework.response.Response'},
    'data_security.adapters.persistence.apps': {'django.apps.AppConfig'},
    'data_security.adapters.persistence.fields': {'django.db.models', 'django.db.transaction'},
    'data_security.adapters.persistence.field_migration': {'django.db.DatabaseError', 'django.db.connection', 'django.db.transaction'},
    'data_security.adapters.persistence.field_rotation': {'django.db.DatabaseError', 'django.db.connection', 'django.db.transaction'},
    'ctf_backend.security_bootstrap': PHASE3_EXTERNAL['ctf_backend.security_bootstrap'] | {'django.apps.apps'},
    'data_security.adapters.persistence.models': {'django.db.models'},
    'data_security.adapters.persistence.orm_policies': {
        'django.db.DatabaseError', 'django.db.connection', 'django.db.transaction'},
    'data_security.adapters.persistence.migrations.0001_policyversion': {'django.db.models', 'django.db.migrations'},
}
PHASE4_IO_STDLIB = {
    **PHASE3_IO_STDLIB,
    'data_security.adapters.persistence.policies': {'pathlib', 'stat', 'os', 'tempfile', 'fcntl'},
    'data_security.adapters.persistence.field_migration': {'pathlib', 'os'},
}
PHASE5_MODULES = PHASE4_MODULES | frozenset({
    'data_security.adapters.tabular.codec', 'data_security.adapters.tabular.column_v1',
    'data_security.adapters.tabular.source_plans', 'data_security.adapters.tabular.parsed_artifacts',
    'data_security.application.legacy_tabular',
})
PHASE5_PACKAGES = PHASE4_PACKAGES
PHASE5_LEGACY = {
    **PHASE4_LEGACY,
    'mainline1.repository': ('data_security.contracts', 'data_security.adapters.tabular.parsed_artifacts'),
    'tasks.controlled-export-execution.controlled_export.transformations': (
        'data_security.contracts', 'data_security.application.legacy_tabular',
        'data_security.adapters.tabular.codec', 'data_security.adapters.tabular.column_v1'),
    'tasks.controlled-export-execution.controlled_export.services': ('data_security.contracts',),
}
PHASE5_EXTERNAL = {
    **PHASE4_EXTERNAL,
    'data_security.adapters.tabular.codec': {'magic', 'defusedxml.ElementTree',
        'defusedxml.common.DefusedXmlException', 'openpyxl.Workbook', 'openpyxl.load_workbook',
        'openpyxl.utils.exceptions.IllegalCharacterError'},
    'data_security.adapters.tabular.parsed_artifacts': {
        'mainline1.parsing.ParseResult', 'mainline1.parsing.PARSER_VERSION',
        'mainline1.parsing.fingerprint', 'mainline1.parsing.normalize_scope'},
}
PHASE5_IO_STDLIB = {
    **PHASE4_IO_STDLIB,
    'data_security.adapters.tabular.codec': {'csv', 'io', 'zipfile', 'xml'},
    'data_security.adapters.tabular.parsed_artifacts': {'unicodedata'},
}

PHASE6_MODULES = PHASE5_MODULES | frozenset({
    'controlled_export_service.security_bootstrap',
    'tasks.controlled-export-execution.controlled_export_service.security_bootstrap',
    'data_security.adapters.persistence.quota', 'data_security.adapters.persistence.uow',
    'data_security.adapters.persistence.risk', 'data_security.adapters.persistence.private_store',
    'data_security.application.reports', 'data_security.application.table_reports',
    'data_security.application.export_flow', 'data_security.application.canary',
    'data_security.application.private_files', 'data_security.application.backup_retention',
    'data_security.application.legacy_archive', 'data_security.application.backup_recovery',
    'data_security.adapters.persistence.private_maintenance', 'data_security.adapters.persistence.recovery_state',
    'data_security.adapters.persistence.recovery_verifier', 'data_security.adapters.persistence.executor_recovery',
    'data_security.adapters.persistence.migrations.0011_privatefileoperation_legacy_sources',
    'data_security.adapters.persistence.canary_catalog', 'data_security.adapters.persistence.canary_targets',
    'data_security.adapters.persistence.migrations.0012_canaryregistration',
    'data_security.adapters.django.canary_tools', 'data_security.adapters.django.uploads',
    'data_security.adapters.django.recovery_ingress',
    'data_security.adapters.django.private_ingress', 'data_security.adapters.django.export_recovery',
    'data_security.adapters.django.export_delivery', 'data_security.adapters.persistence.export_delivery',
    'data_security.adapters.django.private_files', 'data_security.adapters.persistence.file_operations',
    'data_security.adapters.persistence.file_shares',
    'data_security.adapters.persistence.migrations.0010_privatefileoperation',
    'data_security.adapters.persistence.migrations.0009_export_binding',
    'data_security.adapters.persistence.report_records', 'data_security.adapters.persistence.recovery',
    'data_security.adapters.persistence.legacy_archive', 'data_security.adapters.persistence.export_plans',
    'data_security.adapters.persistence.migrations.0008_exportplanapproval',
    'data_security.adapters.persistence.migrations.0007_recoverypermission',
    'data_security.adapters.persistence.migrations.0002_quota_execution',
    'data_security.adapters.persistence.migrations.0003_private_object',
    'data_security.adapters.persistence.migrations.0004_export_report',
    'data_security.adapters.persistence.migrations.0005_delivery_receipt',
    'data_security.adapters.persistence.migrations.0006_preparation_fence',
})
PHASE6_PACKAGES = PHASE5_PACKAGES
PHASE6_LEGACY = {
    **PHASE5_LEGACY,
    'audit.models': (*PHASE5_LEGACY['audit.models'], 'data_security.contracts'),
    'tasks.controlled-export-execution.controlled_export.views': ('data_security.contracts',),
    'audit.recovery_permissions': ('data_security.contracts',),
    'audit.legacy_archives': ('data_security.contracts',),
    'audit.export_plans': ('data_security.contracts',),
    'resources.private_uploads': ('data_security.contracts',),
    'resources.export_sources': ('data_security.contracts',),
    'export_risk.column_authority': ('data_security.contracts',),
    'resources.serializers': ('data_security.contracts', 'data_security.adapters.django.private_files'),
    'resources.views': ('data_security.contracts', 'data_security.adapters.django.private_files'),
    'feedback_center.private_uploads': ('data_security.contracts',),
    'feedback_center.views': ('data_security.contracts', 'data_security.adapters.django.private_files'),
}
PHASE6_STARTUP = {
    **PHASE3_STARTUP,
    'ctf_backend.asgi': {'ctf_backend.security_bootstrap.guard_private_upload_asgi'},
    'tasks.controlled-export-execution.controlled_export.apps': {
        'controlled_export_service.security_bootstrap.start_application'},
    'tasks.controlled-export-execution.controlled_export_service.asgi': {
        'controlled_export_service.security_bootstrap.guard_private_upload_asgi'},
}
PHASE6_EXTERNAL = {
    **PHASE5_EXTERNAL,
    'tasks.controlled-export-execution.controlled_export_service.security_bootstrap': {
        'django.conf.settings', 'controlled_export.services.execute_authorized_export',
        'controlled_export.services.observe_private_preparation',
        'controlled_export.services.inspect_private_preparation'},
    'data_security.adapters.persistence.executor_recovery': {
        'django.db.DatabaseError', 'django.db.connection', 'django.db.transaction',
        'controlled_export.errors.ControlledExportError', 'controlled_export.models.DeliveryAttempt',
        'controlled_export.models.ExecutionAttempt', 'controlled_export.models.ExportExecution',
        'controlled_export.models.OutboxEvent', 'controlled_export.models.ProtectedArtifact', 'controlled_export.models.ShareGrant'},
    'data_security.adapters.django.private_ingress': {
        'django.core.handlers.asgi.get_script_prefix', 'django.core.handlers.asgi.ASGIHandler',
        'django.core.exceptions.RequestAborted', 'django.core.exceptions.RequestDataTooBig', 'django.http.HttpResponse'},
    'data_security.adapters.django.recovery_ingress': {'django.http.HttpResponse'},
    'data_security.adapters.django.private_files': {
        'django.http.HttpResponse', 'django.utils.http.content_disposition_header', 'django.urls.path',
        'rest_framework.decorators.api_view', 'rest_framework.decorators.permission_classes',
        'rest_framework.permissions.IsAuthenticated', 'rest_framework.response.Response'},
    'data_security.adapters.django.export_delivery': {
        'django.urls.path', 'rest_framework.decorators.api_view', 'rest_framework.decorators.permission_classes',
        'rest_framework.permissions.IsAuthenticated', 'rest_framework.response.Response'},
    'data_security.adapters.persistence.canary_catalog': {'django.db.models'},
    'data_security.adapters.persistence.canary_targets': {
        'django.db.DatabaseError', 'django.db.connection', 'django.db.transaction',
        'challenges.models.Challenge', 'legal_kb.models.LegalDocument',
        'resources.models.ResourceCache', 'users.models.CTFUser'},
    'data_security.adapters.persistence.migrations.0012_canaryregistration': {'django.db.models', 'django.db.migrations'},
    'data_security.adapters.persistence.file_operations': {'django.db.connection', 'django.db.transaction'},
    'data_security.adapters.persistence.file_shares': {'django.db.DatabaseError', 'django.db.connection', 'django.db.transaction'},
    'data_security.adapters.persistence.migrations.0010_privatefileoperation': {'django.db.models', 'django.db.migrations'},
    'ctf_backend.security_bootstrap': PHASE5_EXTERNAL['ctf_backend.security_bootstrap'] | {
        'agent_runtime.gateway.AgentGateway',
        'resources.private_uploads.ResourcePrivateUploads',
        'feedback_center.private_uploads.FeedbackPrivateUploads',
        'audit.recovery_permissions.RecoveryPermissionOwner', 'audit.legacy_archives.LegacyArchiveOwner',
        'audit.export_plans.ExportPlanOwner', 'resources.export_sources.ResourceExportSources',
        'export_risk.column_authority.ColumnRiskOwner', 'export_risk.column_authority.freeze_request',
        'export_risk.contracts.SourceMode'},
    'data_security.adapters.django.uploads': {
        'django.core.exceptions.RequestDataTooBig', 'django.core.exceptions.TooManyFilesSent',
        'django.core.files.uploadedfile.InMemoryUploadedFile',
        'django.core.files.uploadhandler.FileUploadHandler', 'django.core.files.uploadhandler.StopFutureHandlers',
        'django.http.multipartparser.MultiPartParserError',
    },
    'data_security.adapters.persistence.audit': PHASE5_EXTERNAL['data_security.adapters.persistence.audit'] | {
        'audit.models.AuthenticatedAuditEntry', 'django.db.connection'},
    'data_security.adapters.persistence.legacy_archive': {
        'django.db.DatabaseError', 'django.db.connection', 'django.db.transaction', 'django.db.models.Q',
        'audit.models.AuditLedgerEntry', 'audit.models.AuditLedgerLock', 'audit.models.SecurityAuditRecord',
        'audit.services.AuditLedgerService',
    },
    'data_security.adapters.persistence.backup': PHASE5_EXTERNAL['data_security.adapters.persistence.backup'] | {'psycopg2.sql'},
    'data_security.adapters.persistence.private_maintenance': {'django.db.connection', 'django.db.transaction'},
    'data_security.adapters.persistence.recovery_verifier': {
        'django.db.DatabaseError', 'django.db.connection', 'django.db.transaction', 'django.db.models.Q',
        'audit.models.AuditLedgerEntry', 'audit.models.AuditLedgerLock', 'audit.models.SecurityAuditRecord',
        'audit.services.AuditLedgerService', 'export_quota.models.QuotaBucket', 'export_quota.models.QuotaReservation',
        'feedback_center.models.FeedbackAttachment', 'resources.models.Resource'},
    'data_security.adapters.persistence.migrations.0011_privatefileoperation_legacy_sources': {
        'django.db.models', 'django.db.migrations'},
    'data_security.adapters.persistence.quota': {
        'django.db.DatabaseError', 'django.db.IntegrityError', 'django.db.transaction', 'django.utils.timezone',
        'export_quota.services.QuotaConflict', 'export_quota.services.QuotaError',
        'export_quota.services.QuotaExceeded', 'export_quota.services.QuotaService',
    },
    'data_security.adapters.persistence.uow': {'django.db.transaction'},
    'data_security.adapters.persistence.recovery': {
        'django.db.DatabaseError', 'django.db.connection', 'django.db.transaction'},
    'data_security.adapters.persistence.export_plans': {'django.db.DatabaseError', 'django.db.transaction'},
    'data_security.adapters.persistence.export_delivery': {
        'django.db.DatabaseError', 'django.db.connection',
        'export_risk.column_authority.ColumnRiskSupplier', 'export_risk.column_authority.decode_request',
        'export_risk.contracts.ExportRequestSnapshot'},
    'data_security.adapters.django.export_recovery': {
        'django.urls.path', 'rest_framework.decorators.api_view', 'rest_framework.decorators.permission_classes',
        'rest_framework.permissions.IsAuthenticated', 'rest_framework.response.Response'},
    'data_security.adapters.persistence.migrations.0009_export_binding': {'django.db.models', 'django.db.migrations'},
    'data_security.adapters.persistence.migrations.0008_exportplanapproval': {'django.db.models', 'django.db.migrations'},
    'data_security.adapters.persistence.migrations.0007_recoverypermission': {'django.db.models', 'django.db.migrations'},
    'data_security.adapters.persistence.risk': {
        'django.db.DatabaseError', 'django.db.IntegrityError', 'django.db.connection', 'django.db.transaction',
        'export_risk.contracts.AuthorizationSnapshot', 'export_risk.contracts.ExportRequestSnapshot',
        'export_risk.contracts.ExportRiskAssessment', 'export_risk.contracts.NotExecutable',
        'export_risk.contracts.SourceMode', 'export_risk.decisions.service.IdempotencyConflict',
        'export_risk.decisions.service.check_execution_eligibility',
        'export_risk.decisions.service.claim', 'export_risk.decisions.service.consume',
        'export_risk.decisions.service.create_risk_decision',
        'export_risk.decisions.service.prepare_execution', 'export_risk.decisions.service.recheck_execution',
        'export_risk.decisions.service.recheck_delivered',
    },
    'data_security.adapters.persistence.private_store': {'django.db.DatabaseError', 'django.db.transaction'},
    'data_security.adapters.persistence.report_records': {
        'django.db.DatabaseError', 'django.db.IntegrityError', 'django.db.connection', 'django.db.transaction'},
    'data_security.adapters.persistence.migrations.0006_preparation_fence': {
        'django.db.models', 'django.db.migrations', 'django.db.models.deletion'},
    'data_security.adapters.persistence.migrations.0005_delivery_receipt': {'django.db.models', 'django.db.migrations'},
    'data_security.adapters.persistence.migrations.0004_export_report': {
        'django.db.models', 'django.db.migrations', 'django.db.models.deletion'},
    'data_security.adapters.persistence.migrations.0002_quota_execution': {'django.db.models', 'django.db.migrations'},
    'data_security.adapters.persistence.migrations.0003_private_object': {'django.db.models', 'django.db.migrations'},
}
PHASE6_IO_STDLIB = {
    **PHASE5_IO_STDLIB,
    'tasks.controlled-export-execution.controlled_export_service.security_bootstrap': {'pathlib', 'secrets'},
    'data_security.adapters.django.uploads': {'io'},
    'data_security.adapters.django.private_ingress': {'io'},
    'data_security.adapters.persistence.file_operations': {'os', 'stat', 'fcntl', 'contextlib'},
    'data_security.adapters.persistence.backup': PHASE5_IO_STDLIB['data_security.adapters.persistence.backup'] | {'stat', 'tarfile'},
    'data_security.adapters.persistence.audit': {'os', 'pathlib', 'stat'},
    'data_security.adapters.persistence.legacy_archive': {'os', 'pathlib', 'stat', 'subprocess', 'contextlib'},
    'data_security.adapters.persistence.private_store': {'os', 'pathlib', 'stat'},
    'data_security.adapters.persistence.private_maintenance': {'contextlib', 'os', 'pathlib', 'stat'},
    'data_security.adapters.persistence.recovery_state': {'os', 'pathlib', 'stat'},
}

PHASE7_MODULES = PHASE6_MODULES | frozenset({
    'data_security.adapters.django.rag', 'data_security.adapters.django.reveal_api',
    'data_security.application.reveal', 'data_security.adapters.persistence.reveal',
    'data_security.adapters.persistence.migrations.0013_reveal_request',
    'data_security.adapters.persistence.migrations.0014_reveal_request_metadata',
    'data_security.adapters.persistence.migrations.0015_export_retention_registration',
    'data_security.adapters.persistence.migrations.0016_export_retention_intent',
    'data_security.adapters.persistence.migrations.0017_reveal_retention_registration',
    'data_security.adapters.persistence.migrations.0018_export_candidate_registration',
    'data_security.adapters.persistence.reveal_retention',
    'data_security.adapters.persistence.export_lifecycle',
    'data_security.adapters.persistence.export_retention_journal',
    'data_security.adapters.django.statistics_api', 'data_security.adapters.persistence.statistics',
})
PHASE7_PACKAGES = PHASE6_PACKAGES
PHASE7_LEGACY = {
    **PHASE6_LEGACY,
    'rag_ingestion.services': ('data_security.adapters.django.rag',),
    'legal_kb.services.retrieval_service': ('data_security.adapters.django.rag',),
    'legal_kb.services.ingestion_service': ('data_security.adapters.django.rag',),
    'legal_kb.services.platform_indexing_service': ('data_security.adapters.django.rag',),
    'rag_ingestion.serializers': ('data_security.adapters.django.rag',),
    'ai_assistant.service': (*PHASE6_LEGACY['ai_assistant.service'], 'data_security.adapters.django.rag'),
    'ai_assistant.views': (*PHASE6_LEGACY['ai_assistant.views'],
                           'data_security.adapters.django.content', 'data_security.adapters.django.rag'),
    'ai_assistant.response_adapter': ('data_security.adapters.django.rag',),
    'ai_assistant.tutor_request_orchestrator': ('data_security.adapters.django.content',),
    'legal_kb.services.rag_answer_service': (*PHASE6_LEGACY['legal_kb.services.rag_answer_service'],
                                           'data_security.adapters.django.rag'),
}
PHASE7_EXTERNAL = {
    **PHASE6_EXTERNAL,
    'data_security.adapters.persistence.audit': PHASE6_EXTERNAL['data_security.adapters.persistence.audit'] | {
        'django.core.management.color.no_style'},
    'data_security.adapters.django.rag': {'rest_framework.exceptions.APIException'},
    'data_security.adapters.django.statistics_api': {
        'django.urls.path', 'rest_framework.permissions.IsAuthenticated',
        'rest_framework.response.Response', 'rest_framework.views.APIView'},
    'data_security.adapters.persistence.statistics': {'django.db.DatabaseError'},
    'data_security.adapters.django.reveal_api': {
        'django.urls.path', 'rest_framework.parsers.JSONParser', 'rest_framework.permissions.IsAuthenticated',
        'rest_framework.response.Response', 'rest_framework.views.APIView'},
    'data_security.adapters.persistence.reveal': {
        'django.db.DatabaseError', 'django.db.connection', 'django.db.models.Q', 'legal.models.LegalAnalysisTask', 'legal.models.LegalReport',
        'legal.permissions.IsLegalReviewer', 'legal.services.data_access.authorized_legal_objects',
        'users.models.CTFUser', 'users.permissions.authorized_users'},
    'data_security.adapters.persistence.migrations.0013_reveal_request': {
        'django.conf.settings', 'django.db.models', 'django.db.migrations', 'django.db.models.deletion'},
    'data_security.adapters.persistence.migrations.0014_reveal_request_metadata': {
        'django.db.models', 'django.db.migrations'},
    'data_security.adapters.persistence.migrations.0015_export_retention_registration': {
        'django.db.models', 'django.db.migrations'},
    'data_security.adapters.persistence.migrations.0016_export_retention_intent': {
        'django.db.models', 'django.db.migrations'},
    'data_security.adapters.persistence.migrations.0017_reveal_retention_registration': {
        'django.db.models', 'django.db.migrations'},
    'data_security.adapters.persistence.migrations.0018_export_candidate_registration': {
        'django.db.models', 'django.db.migrations'},
    'data_security.adapters.persistence.reveal_retention': {'django.db.connection'},
    'data_security.adapters.persistence.export_lifecycle': {
        'django.db.DatabaseError', 'django.db.connection', 'django.db.transaction', 'audit.models.AuthenticatedAuditEntry'},
    'ctf_backend.security_bootstrap': PHASE6_EXTERNAL['ctf_backend.security_bootstrap'] | {
        'rag_ingestion.adapters.parser_plain.PlainTextParser',
        'rag_ingestion.adapters.parser_docx.DocxParser',
        'rag_ingestion.adapters.parser_pdf.PdfParser',
        'rag_ingestion.adapters.parser_markitdown.MarkItDownParser',
        'rag_ingestion.pipeline.IngestionPipeline', 'rag_ingestion.chunking.StructureAwareChunker',
        'rag_ingestion.registry.select_parser', 'rag_ingestion.registry.bind_ingestion',
        'rag_ingestion.adapters.embedder_legalkb.LegalKbEmbedder',
        'rag_ingestion.adapters.repository_legalkb.LegalKbChunkRepository',
        'legal_kb.services.embedding_service.EmbeddingService',
    },
}
PHASE7_IO_STDLIB = {
    **PHASE6_IO_STDLIB,
    'data_security.adapters.persistence.export_lifecycle': {'os'},
    'data_security.adapters.persistence.export_retention_journal': {'os', 'pathlib', 'stat'},
}


IO_STDLIB = {
    'M5': {'os', 'pathlib', 'stat'},
    'M6': {'os', 'pathlib', 'stat', 'io', 'subprocess', 'contextlib', 'tempfile', 'shutil', 'time'},
    'M7': {'abc', 'asyncio', 'contextlib', 'io', 'urllib', 'http', 'ssl', 'socket', 'time'},
    'M8': {'csv', 'io', 'zipfile', 'xml', 'decimal', 'codecs'},
    'M9': {'logging', 'contextlib', 'http', 'urllib'},
    'B': {'os', 'pathlib', 'contextlib', 'secrets', 'time'},
}


@dataclass(frozen=True)
class Violation:
    file: str
    line: int
    code: str


def owner(module):
    if module in ('data_security', 'data_security.core', 'data_security.adapters'):
        return 'M0'
    if any(module == prefix or module.startswith(prefix + '.') for prefix in BOOTSTRAP_MODULES):
        return 'B'
    prefixes = (
        ('data_security.contracts', 'M0'), ('data_security.core.redaction', 'M1'),
        ('data_security.core.detectors', 'M1'), ('data_security.core.algorithms', 'M1'),
        ('data_security.core.policy', 'M2'), ('data_security.core.crypto', 'M3'),
        ('data_security.application', 'M4'), ('data_security.adapters.keys', 'M5'),
        ('data_security.adapters.persistence', 'M6'), ('data_security.adapters.llm', 'M7'),
        ('data_security.adapters.tabular', 'M8'), ('data_security.adapters.django', 'M9'),
    )
    for prefix, result in prefixes:
        if module == prefix or module.startswith(prefix + '.'):
            return result
    return None


def module_name(path):
    path = Path(path)
    parts = list(path.with_suffix('').parts)
    if 'backend' in parts:
        parts = parts[parts.index('backend') + 1:]
    if parts[-1] == '__init__':
        parts.pop()
    return '.'.join(parts)


def allowed_import(source_owner, target, *, phase=1, module=None, is_module=False):
    target_owner = owner(target)
    if target_owner:
        if target_owner not in ALLOWED[source_owner]:
            return False
        if phase in (3, 4, 5, 6, 7) and target_owner != 'M0':
            # A concrete module or one member imported from it, not arbitrary
            # future descendants hidden under an approved package prefix.
            modules, packages = {3: (PHASE3_MODULES, PHASE3_PACKAGES),
                                 4: (PHASE4_MODULES, PHASE4_PACKAGES),
                                 5: (PHASE5_MODULES, PHASE5_PACKAGES),
                                 6: (PHASE6_MODULES, PHASE6_PACKAGES),
                                 7: (PHASE7_MODULES, PHASE7_PACKAGES)}[phase]
            return (target in modules or not is_module and
                    target.rpartition('.')[0] in modules - packages)
        return True
    if target.startswith(('data_security', 'ctf_backend.security_bootstrap')):
        return False
    top = target.split('.')[0]
    if top in PURE_STDLIB or (source_owner == 'M1' and top == 'ipaddress'):
        return True
    if phase in (3, 4, 5, 6, 7):
        if source_owner == 'M3' and top == 'cryptography':
            return True
        external, io = {3: (PHASE3_EXTERNAL, PHASE3_IO_STDLIB),
                        4: (PHASE4_EXTERNAL, PHASE4_IO_STDLIB),
                        5: (PHASE5_EXTERNAL, PHASE5_IO_STDLIB),
                        6: (PHASE6_EXTERNAL, PHASE6_IO_STDLIB),
                        7: (PHASE7_EXTERNAL, PHASE7_IO_STDLIB)}[phase]
        return (target in external.get(module, set()) or
                top in io.get(module, set()) and top in sys.stdlib_module_names)
    if top in IO_STDLIB.get(source_owner, set()) and top in sys.stdlib_module_names:
        return True
    if source_owner == 'M8' and any(target == value or target.startswith(value + '.') for value in LEGACY_PORTS):
        return True
    return top in EXTERNAL[source_owner]


def check_source(path, source, *, phase=1):
    module = module_name(path)
    current = owner(module)
    http_bridge = phase == 7 and module in (
        'ai_assistant.views', 'ai_assistant.response_adapter', 'ai_assistant.tutor_request_orchestrator')
    package = module if str(path).endswith('__init__.py') else module.rpartition('.')[0]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', SyntaxWarning)
            tree = ast.parse(source)
    except SyntaxError as exc:
        return [Violation(str(path), exc.lineno or 1, 'INVALID_PYTHON')]
    findings = []
    if module.startswith('data_security.') and current is None:
        findings.append(Violation(str(path), 1, 'UNCLASSIFIED_SECURITY_MODULE'))
    aliases = {}
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.append((node.lineno, alias.name, True))
                aliases[alias.asname or alias.name.split('.')[0]] = alias.name if alias.asname else alias.name.split('.')[0]
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ''
            if node.level:
                parts = package.split('.')
                keep = len(parts) - node.level + 1
                if keep <= 0:
                    findings.append(Violation(str(path), node.lineno, 'RELATIVE_IMPORT_ESCAPE'))
                    continue
                base = '.'.join(parts[:keep] + ([base] if base else []))
            for alias in node.names:
                target = base + '.' + alias.name
                imported.append((node.lineno, target, False))
                aliases[alias.asname or alias.name] = target
    for line, target, is_module in imported:
        if http_bridge and target.split('.')[0] in ('openai', 'anthropic'):
            findings.append(Violation(str(path), line, 'BUSINESS_SDK_BYPASS'))
        if current:
            if not allowed_import(current, target, phase=phase, module=module, is_module=is_module):
                findings.append(Violation(str(path), line, 'DEPENDENCY_' + current))
        elif owner(target) == 'B':
            startup = PHASE6_STARTUP if phase in (6, 7) else PHASE3_STARTUP
            if phase not in (3, 4, 5, 6, 7) or target not in startup.get(module, set()):
                findings.append(Violation(str(path), line, 'BOOTSTRAP_REVERSE_IMPORT'))
        elif target.startswith('data_security') and module != 'data_security':
            permitted = phase == 2 and any(target == prefix or target.startswith(prefix + '.')
                for prefix in PHASE2_LEGACY.get(module, ()))
            if phase in (3, 4, 5, 6, 7):
                legacy = {3: PHASE3_LEGACY, 4: PHASE4_LEGACY, 5: PHASE5_LEGACY,
                          6: PHASE6_LEGACY, 7: PHASE7_LEGACY}[phase]
                permitted = any(target == prefix or not is_module and target.rpartition('.')[0] == prefix or
                    prefix == 'data_security.contracts' and target.startswith(prefix + '.')
                    for prefix in legacy.get(module, ()))
            if not permitted:
                findings.append(Violation(str(path), line,
                    f'PHASE{phase}_BUSINESS_NOT_CONNECTED' if phase in (3, 4, 5, 6, 7) else 'PHASE1_BUSINESS_NOT_CONNECTED'))
        elif phase in (3, 4, 5, 6, 7) and module == 'ai_providers' and target.split('.')[0] not in PURE_STDLIB | {'asyncio'}:
            findings.append(Violation(str(path), line, 'PHASE3_AI_FACADE_DEPENDENCY'))
    if current or phase in (3, 4, 5, 6, 7):
        def dotted(node):
            if isinstance(node, ast.Name):
                return aliases.get(node.id, node.id)
            if isinstance(node, ast.Attribute):
                return dotted(node.value) + '.' + node.attr
            return ''
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                name = dotted(node.value)
                if name:
                    aliases[node.targets[0].id] = name
        for node in ast.walk(tree):
            if isinstance(node, (ast.Subscript, ast.Attribute)) and (
                    http_bridge or current and current not in ('M5', 'B')):
                name = dotted(node.value) if isinstance(node, ast.Subscript) else dotted(node)
                if name == 'os.environ' or name.startswith('os.environ.'):
                    findings.append(Violation(str(path), node.lineno, 'SECRET_CONFIG_BYPASS'))
            if not isinstance(node, ast.Call):
                continue
            name = dotted(node.func)
            if name in ('eval', 'exec', '__import__', 'builtins.eval', 'builtins.exec', 'builtins.__import__') or name.startswith('importlib.'):
                findings.append(Violation(str(path), node.lineno, 'DYNAMIC_CODE_OR_IMPORT'))
            if current in ('M0', 'M1', 'M2', 'M3', 'M4') and (
                name in ('open', 'print', 'input', 'builtins.open') or
                name.endswith(('.now', '.today', '.utcnow')) or name.startswith(('random.', 'secrets.', 'time.'))
            ):
                findings.append(Violation(str(path), node.lineno, 'IMPLICIT_IO_CLOCK_RANDOM'))
            if (http_bridge or current and current not in ('B', 'M5')) and name in (
                    'os.getenv', 'os.environ.get', 'os.environ.__getitem__'):
                findings.append(Violation(str(path), node.lineno, 'SECRET_CONFIG_BYPASS'))
            if (phase in (3, 4, 5, 6, 7) and current == 'M6' and
                    name == 'audit.services.AuditLedgerService.append_entry'):
                findings.append(Violation(str(path), node.lineno, 'AUDIT_SINK_PUBLIC_CALLBACK'))
    return findings


def scan(root, *, phase=None):
    root = Path(root).resolve()
    if phase is None:
        declaration = root / 'tools/data_security/phase-boundary.json'
        if declaration.is_symlink():
            return 0, [Violation(str(declaration), 1, 'UNKNOWN_PHASE_BOUNDARY')]
        try:
            value = json.loads(declaration.read_text()) if declaration.exists() else {'phase': 1, 'version': 'phase-boundary.v1'}
        except (OSError, ValueError):
            return 0, [Violation(str(declaration), 1, 'UNKNOWN_PHASE_BOUNDARY')]
        if (type(value) is not dict or set(value) != {'phase', 'version'} or
                type(value['phase']) is not int or value['phase'] not in (1, 2, 3, 4, 5, 6, 7) or
                value['version'] != 'phase-boundary.v1'):
            return 0, [Violation(str(declaration), 1, 'UNKNOWN_PHASE_BOUNDARY')]
        phase = value['phase']
    # An explicit phase is historical/strict, never silently promoted by the
    # declaration. Only the default scan follows the declared current phase.
    if type(phase) is not int or phase not in (1, 2, 3, 4, 5, 6, 7):
        raise ValueError('UNKNOWN_PHASE_BOUNDARY')
    violations = []
    checked = 0
    paths = list((root / 'backend').rglob('*.py'))
    paths += list((root / 'tasks/controlled-export-execution/controlled_export').rglob('*.py'))
    paths += list((root / 'tasks/controlled-export-execution/controlled_export_service').rglob('*.py'))
    for path in sorted(paths):
        relative = path.relative_to(root)
        if any(part in ('.venv', '__pycache__', 'tests') for part in relative.parts):
            continue
        if phase not in (3, 4, 5, 6, 7) and 'migrations' in relative.parts:
            continue
        if path.name.startswith('test_') or path.name == 'tests.py':
            continue
        if path.is_symlink():
            violations.append(Violation(str(relative), 1, 'SOURCE_SYMLINK'))
            continue
        checked += 1
        module = module_name(relative)
        inventory = {2: PHASE2_MODULES, 3: PHASE3_MODULES, 4: PHASE4_MODULES,
                     5: PHASE5_MODULES, 6: PHASE6_MODULES, 7: PHASE7_MODULES}.get(phase, PHASE2_MODULES)
        if owner(module) in ALLOWED.keys() - {'M0'} and (phase == 1 or module not in inventory):
            violations.append(Violation(str(relative), 1, f'PHASE{phase}_FUTURE_IMPLEMENTATION'))
        # Bytes preserve Python's declared encoding and UTF-8 BOM handling.
        violations.extend(check_source(relative, path.read_bytes(), phase=phase))
    return checked, violations


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument('--phase', type=int, choices=(1, 2, 3, 4, 5, 6, 7))
    args = parser.parse_args()
    checked, findings = scan(args.root, phase=args.phase)
    print(json.dumps({'checked_python_files': checked, 'violations': [
        {'file': f.file, 'line': f.line, 'code': f.code} for f in findings]}, ensure_ascii=False))
    return int(bool(findings))


if __name__ == '__main__':
    raise SystemExit(main())
