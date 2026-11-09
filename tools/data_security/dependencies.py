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
    if module == 'ctf_backend.security_bootstrap' or module.startswith('ctf_backend.security_bootstrap.'):
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
        if phase in (3, 4, 5) and target_owner != 'M0':
            # A concrete module or one member imported from it, not arbitrary
            # future descendants hidden under an approved package prefix.
            modules, packages = {3: (PHASE3_MODULES, PHASE3_PACKAGES),
                                 4: (PHASE4_MODULES, PHASE4_PACKAGES),
                                 5: (PHASE5_MODULES, PHASE5_PACKAGES)}[phase]
            return (target in modules or not is_module and
                    target.rpartition('.')[0] in modules - packages)
        return True
    if target.startswith(('data_security', 'ctf_backend.security_bootstrap')):
        return False
    top = target.split('.')[0]
    if top in PURE_STDLIB or (source_owner == 'M1' and top == 'ipaddress'):
        return True
    if phase in (3, 4, 5):
        if source_owner == 'M3' and top == 'cryptography':
            return True
        external, io = {3: (PHASE3_EXTERNAL, PHASE3_IO_STDLIB),
                        4: (PHASE4_EXTERNAL, PHASE4_IO_STDLIB),
                        5: (PHASE5_EXTERNAL, PHASE5_IO_STDLIB)}[phase]
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
        if current:
            if not allowed_import(current, target, phase=phase, module=module, is_module=is_module):
                findings.append(Violation(str(path), line, 'DEPENDENCY_' + current))
        elif target == 'ctf_backend.security_bootstrap' or target.startswith('ctf_backend.security_bootstrap.'):
            if phase not in (3, 4, 5) or target not in PHASE3_STARTUP.get(module, set()):
                findings.append(Violation(str(path), line, 'BOOTSTRAP_REVERSE_IMPORT'))
        elif target.startswith('data_security') and module != 'data_security':
            permitted = phase == 2 and any(target == prefix or target.startswith(prefix + '.')
                for prefix in PHASE2_LEGACY.get(module, ()))
            if phase in (3, 4, 5):
                legacy = {3: PHASE3_LEGACY, 4: PHASE4_LEGACY, 5: PHASE5_LEGACY}[phase]
                permitted = any(target == prefix or not is_module and target.rpartition('.')[0] == prefix or
                    prefix == 'data_security.contracts' and target.startswith(prefix + '.')
                    for prefix in legacy.get(module, ()))
            if not permitted:
                findings.append(Violation(str(path), line,
                    f'PHASE{phase}_BUSINESS_NOT_CONNECTED' if phase in (3, 4, 5) else 'PHASE1_BUSINESS_NOT_CONNECTED'))
        elif phase in (3, 4, 5) and module == 'ai_providers' and target.split('.')[0] not in PURE_STDLIB | {'asyncio'}:
            findings.append(Violation(str(path), line, 'PHASE3_AI_FACADE_DEPENDENCY'))
    if current or phase in (3, 4, 5):
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
            if isinstance(node, (ast.Subscript, ast.Attribute)) and current and current not in ('M5', 'B'):
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
            if current and current not in ('B', 'M5') and name in ('os.getenv', 'os.environ.get', 'os.environ.__getitem__'):
                findings.append(Violation(str(path), node.lineno, 'SECRET_CONFIG_BYPASS'))
            if (phase in (3, 4, 5) and current == 'M6' and
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
                type(value['phase']) is not int or value['phase'] not in (1, 2, 3, 4, 5) or
                value['version'] != 'phase-boundary.v1'):
            return 0, [Violation(str(declaration), 1, 'UNKNOWN_PHASE_BOUNDARY')]
        phase = value['phase']
    # An explicit phase is historical/strict, never silently promoted by the
    # declaration. Only the default scan follows the declared current phase.
    if type(phase) is not int or phase not in (1, 2, 3, 4, 5):
        raise ValueError('UNKNOWN_PHASE_BOUNDARY')
    violations = []
    checked = 0
    paths = list((root / 'backend').rglob('*.py'))
    paths += list((root / 'tasks/controlled-export-execution/controlled_export').rglob('*.py'))
    for path in sorted(paths):
        relative = path.relative_to(root)
        if any(part in ('.venv', '__pycache__', 'tests') for part in relative.parts):
            continue
        if phase not in (3, 4, 5) and 'migrations' in relative.parts:
            continue
        if path.name.startswith('test_') or path.name == 'tests.py':
            continue
        if path.is_symlink():
            violations.append(Violation(str(relative), 1, 'SOURCE_SYMLINK'))
            continue
        checked += 1
        module = module_name(relative)
        inventory = {2: PHASE2_MODULES, 3: PHASE3_MODULES, 4: PHASE4_MODULES,
                     5: PHASE5_MODULES}.get(phase, PHASE2_MODULES)
        if owner(module) in ALLOWED.keys() - {'M0'} and (phase == 1 or module not in inventory):
            violations.append(Violation(str(relative), 1, f'PHASE{phase}_FUTURE_IMPLEMENTATION'))
        # Bytes preserve Python's declared encoding and UTF-8 BOM handling.
        violations.extend(check_source(relative, path.read_bytes(), phase=phase))
    return checked, violations


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument('--phase', type=int, choices=(1, 2, 3, 4, 5))
    args = parser.parse_args()
    checked, findings = scan(args.root, phase=args.phase)
    print(json.dumps({'checked_python_files': checked, 'violations': [
        {'file': f.file, 'line': f.line, 'code': f.code} for f in findings]}, ensure_ascii=False))
    return int(bool(findings))


if __name__ == '__main__':
    raise SystemExit(main())
