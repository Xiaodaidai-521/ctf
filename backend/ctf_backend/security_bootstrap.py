"""Explicit startup/composition boundary. No dynamic implementation paths."""
from functools import partial
import secrets
import os


def framework_startup():
    # This one lazy compatibility input does not bind detection/protection or tokens.
    from data_security.adapters.keys import legacy_teacher_inputs
    from data_security.adapters.django.authentication import bind_bootstrap_teacher_inputs
    bind_bootstrap_teacher_inputs(legacy_teacher_inputs)
    if os.environ.get('DATA_SECURITY_CONFIG'):
        config, resolver = _configuration(os.environ['DATA_SECURITY_CONFIG'])
        ref = KeyReference.from_wire(config['framework_key'])
        material = resolver.resolve(ref, KeyPurpose.FRAMEWORK, 'service/security')
        require(type(material) is SecretMaterial and ref.status is KeyStatus.ACTIVE,
                ReasonCode.KEY_UNAVAILABLE)
        secret = bytes(material.borrow(KeyPurpose.FRAMEWORK)).decode('utf-8')
        require(len(secret) >= 50, ReasonCode.KEY_UNAVAILABLE)
        return secret
    secret = os.environ.get('SECRET_KEY', '')
    if not secret:
        raise RuntimeError('FRAMEWORK_KEY_REQUIRED')
    return secret

from datetime import datetime, timezone
from pathlib import Path
import json
import re

from data_security.contracts import (BASELINE_LIMITS, BoundedPayload, Environment, FrozenJSON,
    KeyPurpose, KeyReference, KeyStatus, MediaType, Outlet, PayloadKind, PolicyBinding,
    ProtectionContext, ProtectionError, Purpose, ReasonCode, Role, SecretMaterial)
from data_security.contracts.schema import require
from data_security.core.redaction import detect, legacy_confidentiality
from data_security.adapters.tabular.legacy import bind_detect
from data_security.adapters.django.legacy import (
    LEGACY_INTERNAL, LEGACY_SECRET, LEGACY_TOKEN, bind_confidentiality,
)

# Identity check is a configuration boundary, not a defence against arbitrary
# Python execution. token_bytes uses SystemRandom -> OS urandom, not random.Random.
_OS_RANDOM = secrets.token_bytes


def validate_production_random(random_bytes):
    require(random_bytes is _OS_RANDOM and secrets.token_bytes is _OS_RANDOM,
            ReasonCode.AUTHORIZATION_DENIED)


def validate_production_inputs(*, random_bytes, policy=None, keys=None, audit=None):
    validate_production_random(random_bytes)
    # There is no approved production implementation to accept in this phase.
    require(policy is None and keys is None and audit is None, ReasonCode.AUTHORIZATION_DENIED)


def bind_legacy_for_tests(*, environment):
    require(environment is Environment.TEST, ReasonCode.AUTHORIZATION_DENIED)
    bind_detect(detect)
    bind_confidentiality(partial(legacy_confidentiality, secret_patterns=LEGACY_SECRET,
        token_pattern=LEGACY_TOKEN, internal_patterns=LEGACY_INTERNAL))


def startup_secret(name):
    require(name in ('DB_PASSWORD', 'LEARNING_MAP_SERVICE_TOKEN', 'MODULE6_SERVICE_TOKEN'),
            ReasonCode.AUTHORIZATION_DENIED)
    # These legacy credentials are not enabled by the formal isolated profile.
    return '' if os.environ.get('DATA_SECURITY_CONFIG') else os.environ.get(name, '')


def startup_database_url():
    return os.environ.get('DATABASE_URL', '')


def _configuration(path):
    from data_security.adapters.keys import FileKeyResolver
    source = Path(path)
    require(source.is_absolute() and source == source.resolve() and
            not source.stat().st_mode & 0o022 and source.stat().st_size <= 65536,
            ReasonCode.AUTHORIZATION_DENIED)
    config = json.loads(source.read_bytes())
    require(type(config) is dict, ReasonCode.INVALID_TYPE)
    version = config.get('schema_version')
    require(version in ('ds.bootstrap.v1', 'ds.bootstrap.v2'), ReasonCode.UNKNOWN_SCHEMA)
    fields = {'schema_version', 'environment', 'key_manifest', 'policy_file', 'policy_binding',
              'framework_key', 'data_key', 'audit_key', 'providers', 'backup'}
    if version == 'ds.bootstrap.v2':
        fields |= {'policy_repository'}
        if 'field_storage' in config:
            fields.add('field_storage')
    require(set(config) == fields, ReasonCode.UNKNOWN_FIELD)
    require(config['environment'] == 'evaluation', ReasonCode.AUTHORIZATION_DENIED)
    if version == 'ds.bootstrap.v2':
        choice = config['policy_repository']
        require(type(choice) is dict and set(choice) == {'kind', 'writable'} and
                choice['kind'] in ('file', 'orm') and type(choice['writable']) is bool,
                ReasonCode.INVALID_VALUE)
        require(choice['kind'] != 'orm' or config['policy_file'] is None, ReasonCode.INVALID_VALUE)
    if 'field_storage' in config:
        options = config['field_storage']
        require(type(options) is dict and set(options) - {'index_deadline'} ==
                {'legacy_reads', 'index_keys', 'read_keys', 'recovery_record'} and
                type(options['legacy_reads']) is bool and type(options['index_keys']) is list and
                1 <= len(options['index_keys']) <= 2 and type(options['read_keys']) is list and
                len(options['read_keys']) <= 2, ReasonCode.INVALID_VALUE)
        proof = options['recovery_record']
        require(type(proof) is dict and set(proof) == {'path', 'sha256'}, ReasonCode.INVALID_VALUE)
        recovery = Path(proof['path'])
        require(recovery.is_absolute() and recovery == recovery.resolve() and
                not recovery.stat().st_mode & 0o022 and recovery.stat().st_size <= 65536,
                ReasonCode.AUTHORIZATION_DENIED)
        import hashlib
        record = recovery.read_bytes()
        require(hashlib.sha256(record).hexdigest() == proof['sha256'], ReasonCode.HASH_MISMATCH)
        record = json.loads(record)
        require(record.get('returncode') == 0 and record.get('key_material_in_evidence') is False and
                record.get('recovery_observations', {}).get('receipt_durability') == 'durable' and
                bool(record.get('recovery_observations', {}).get('checks')), ReasonCode.AUTHORIZATION_DENIED)
    resolver = FileKeyResolver(manifest_path=config['key_manifest'], environment=Environment.EVALUATION,
                               repository_root=Path(__file__).resolve().parents[2],
                               query_index='field_storage' in config)
    return config, resolver


def _confidentiality(value):
    if type(value) is dict:
        return {key: '[REDACTED]' if key.lower() in
                ('password', 'token', 'access_token', 'refresh_token', 'api_key', 'secret', 'cookie', 'authorization')
                else _confidentiality(item) for key, item in value.items()}
    if type(value) is list:
        return [_confidentiality(item) for item in value]
    if isinstance(value, str):
        value = re.sub(r'(?i)\b(?:authorization\s*[:=]\s*)?Bearer\s+[^\s,;]+', '[REDACTED]', str(value))
        value, _ = legacy_confidentiality(value, 'output-v1', secret_patterns=LEGACY_SECRET,
                                          token_pattern=LEGACY_TOKEN, internal_patterns=())
        value, _ = legacy_confidentiality(value, 'legal-v1', secret_patterns=LEGACY_SECRET,
                                          token_pattern=LEGACY_TOKEN, internal_patterns=())
    return value


def assemble(*, config_path, random_bytes=_OS_RANDOM, policy=None, keys=None, audit=None):
    """Only concrete approved adapters. Call after Django application setup."""
    validate_production_inputs(random_bytes=random_bytes, policy=policy, keys=keys, audit=audit)
    config, resolver = _configuration(config_path)
    from data_security.adapters.persistence.policies import FilePolicyRepository
    from data_security.adapters.persistence.audit import DjangoAuditSink
    from data_security.application.policy_catalog import PolicyCatalog
    from data_security.application.audit_gateway import AuditGateway
    from data_security.application.protection import ProtectionService
    from data_security.application.crypto_service import CryptoService
    from data_security.adapters.llm.official import OfficialAI
    from data_security.adapters.django.execution import call_port, run_port
    from ai_providers import MultiProviderManager, ProviderHandle
    from ai_assistant.security import sanitize_output

    clock = lambda: datetime.now(timezone.utc)
    identity = 'service/security'
    binding = PolicyBinding.from_wire(config['policy_binding'])
    choice = config.get('policy_repository', {'kind': 'file', 'writable': False})
    if choice['kind'] == 'orm':
        from data_security.adapters.persistence.orm_policies import ORMPolicyRepository
        repository = ORMPolicyRepository(writable=choice['writable'])
    else:
        repository = FilePolicyRepository(path=config['policy_file'], writable=choice['writable'])
    gateway = AuditGateway(sink=DjangoAuditSink(clock=clock))
    catalog = PolicyCatalog(repository=repository, clock=clock, management=choice['writable'], audit=gateway)
    snapshot = catalog.snapshot(binding)
    require(type(snapshot) is not ProtectionError, ReasonCode.POLICY_NOT_APPROVED)
    if config['schema_version'] == 'ds.bootstrap.v1':
        require(snapshot.approval.approval_ref == 'approval/phase3-20261105-1329', ReasonCode.POLICY_NOT_APPROVED)
    references, values = {}, set()
    for name, purpose in (('framework_key', KeyPurpose.FRAMEWORK), ('data_key', KeyPurpose.DATA),
                          ('audit_key', KeyPurpose.AUDIT)):
        ref = KeyReference.from_wire(config[name])
        material = resolver.resolve(ref, purpose, identity)
        require(type(material) is SecretMaterial and ref.status is KeyStatus.ACTIVE, ReasonCode.KEY_UNAVAILABLE)
        value = bytes(material.borrow(purpose))
        require(value not in values, ReasonCode.KEY_UNAVAILABLE)
        if purpose is KeyPurpose.FRAMEWORK:
            require(len(value) >= 50, ReasonCode.KEY_UNAVAILABLE)
        values.add(value)
        references[name] = ref
    protection = ProtectionService(policies=catalog, audit=gateway, clock=clock,
        random_bytes=random_bytes, environment=Environment.EVALUATION, limits=BASELINE_LIMITS,
        field_ref='content/body')
    crypto = CryptoService(keys=resolver, service_identity=identity, random_bytes=random_bytes,
        environment=Environment.EVALUATION, limits=BASELINE_LIMITS)

    def context(outlet):
        return ProtectionContext(schema_version=ProtectionContext.SCHEMA, actor_ref=identity,
            authorization_ref='authorization/phase3-isolated', scope_refs=('content/body',),
            environment=Environment.EVALUATION, domain='ctf', outlet=outlet, purpose=Purpose.ANALYSIS,
            role=Role.SERVICE, object_ref='request/content', object_version='v1',
            source_ref=None, source_version=None, source_hash=None, trace_id='trace/' + random_bytes(16).hex())

    handles = []
    require(type(config['providers']) is list and len(config['providers']) <= 6, ReasonCode.INVALID_VALUE)
    for provider in config['providers']:
        require(type(provider) is dict and set(provider) == {'endpoint_ref', 'base_url', 'models', 'key_ref'},
                ReasonCode.UNKNOWN_FIELD)
        ref = KeyReference.from_wire(provider['key_ref'])
        material = resolver.resolve(ref, KeyPurpose.PROVIDER, identity)
        require(type(material) is SecretMaterial, ReasonCode.KEY_UNAVAILABLE)
        value = bytes(material.borrow(KeyPurpose.PROVIDER))
        require(value not in values, ReasonCode.KEY_UNAVAILABLE)
        values.add(value)
        require(type(provider['models']) is list and all(type(model) is str for model in provider['models']),
                ReasonCode.INVALID_VALUE)
        adapter = OfficialAI(endpoint_ref=provider['endpoint_ref'], base_url=provider['base_url'],
            models=tuple(provider['models']), key_ref=ref, keys=resolver, protection=protection,
            confidentiality=_confidentiality, limits=BASELINE_LIMITS, service_identity=identity, clock=clock)
        handles.append(ProviderHandle(name=provider['endpoint_ref'], model=provider['models'][0], port=adapter,
                                      context_factory=context, binding=binding, limits=BASELINE_LIMITS,
                                      sanitize_response=lambda value: sanitize_output(value)[0], run_sync=run_port))
    require(len({handle.name for handle in handles}) == len(handles), ReasonCode.INVALID_VALUE)
    backup = None
    if config['backup'] is not None:
        from data_security.adapters.persistence.backup import PostgresAgeBackup
        options = config['backup']
        require(type(options) is dict and set(options) == {'database', 'directory', 'checks', 'age', 'pg_dump', 'pg_restore'},
                ReasonCode.UNKNOWN_FIELD)
        require(options['database'].get('host') in ('127.0.0.1', '::1') and
                not options['database'].get('password'), ReasonCode.AUTHORIZATION_DENIED)
        backup = PostgresAgeBackup(resolver=resolver, service_identity=identity,
            database=options['database'], directory=Path(options['directory']),
            checks=tuple(tuple(check) for check in options['checks']), environment=Environment.EVALUATION,
            domain='ctf', age=Path(options['age']), pg_dump=Path(options['pg_dump']), pg_restore=Path(options['pg_restore']))

    def protect_text(value):
        payload = BoundedPayload(schema_version=BoundedPayload.SCHEMA, kind=PayloadKind.TEXT,
            media_type=MediaType.TEXT, text=_confidentiality(value), tree=None, binary=None, limits=BASELINE_LIMITS)
        result = call_port(protection.protect, payload, context(Outlet.MODEL), binding)
        if type(result) is ProtectionError:
            raise RuntimeError(result.code.value)
        return result.payload.text

    def protect_value(value):
        json_value = not isinstance(value, str)
        value = _confidentiality(value)
        payload = BoundedPayload(schema_version=BoundedPayload.SCHEMA,
            kind=PayloadKind.JSON if json_value else PayloadKind.TEXT,
            media_type=MediaType.JSON if json_value else MediaType.TEXT,
            text=None if json_value else value, tree=FrozenJSON(value) if json_value else None,
            binary=None, limits=BASELINE_LIMITS)
        result = call_port(protection.protect, payload, context(Outlet.API), binding)
        if type(result) is ProtectionError:
            raise RuntimeError(result.code.value)
        return result.payload.tree.to_value() if json_value else result.payload.text

    fields = None
    if 'field_storage' in config:
        from data_security.adapters.persistence.fields import FieldStorage
        options = config['field_storage']
        index_keys = tuple(KeyReference.from_wire(item) for item in options['index_keys'])
        read_keys = tuple(KeyReference.from_wire(item) for item in options['read_keys'])
        require(len({key.key_ref for key in index_keys}) == len(index_keys), ReasonCode.KEY_UNAVAILABLE)
        for key in (*index_keys, *read_keys):
            purpose = KeyPurpose.INDEX if key in index_keys else KeyPurpose.DATA
            require(key.purpose is purpose and (key.status is KeyStatus.ACTIVE if purpose is KeyPurpose.INDEX
                    else key.status is KeyStatus.READ_ONLY), ReasonCode.KEY_UNAVAILABLE)
            material = resolver.resolve(key, purpose, identity)
            require(type(material) is SecretMaterial, ReasonCode.KEY_UNAVAILABLE)
            value = bytes(material.borrow(purpose))
            require(value not in values, ReasonCode.KEY_UNAVAILABLE)
            values.add(value)
            references[key.key_ref] = key
        deadline = options.get('index_deadline')
        require(deadline is None or type(deadline) is str, ReasonCode.INVALID_VALUE)
        require(len(index_keys) == 2 or deadline is None, ReasonCode.INVALID_VALUE)
        fields = FieldStorage(crypto=crypto, data_key=references['data_key'], protect_value=protect_value,
            index_keys=index_keys, read_keys=read_keys, legacy_reads=options['legacy_reads'],
            index_deadline=datetime.fromisoformat(deadline) if deadline is not None else None)

    def preview(case, user_id):
        from dataclasses import replace
        samples = {'email': 'Student@Example.invalid', 'ipv4': '192.0.2.42',
                   'card': '4111111111111111',
                   'mixed': 'Student@Example.invalid 192.0.2.42 4111111111111111'}
        payload = BoundedPayload(schema_version=BoundedPayload.SCHEMA, kind=PayloadKind.TEXT,
            media_type=MediaType.TEXT, text=samples[case], tree=None, binary=None, limits=BASELINE_LIMITS)
        preview_context = replace(context(Outlet.API), object_ref='preview/synthetic',
                                  authorization_ref='authorization/admin-' + str(user_id))
        result = call_port(protection.protect, payload, preview_context, binding)
        if type(result) is ProtectionError:
            return result
        return {'output': result.payload.text, 'policy_version': binding.protection_version,
                'synthetic_only': True}

    return {'manager': MultiProviderManager(handles), 'protection': protection, 'crypto': crypto,
            'audit': gateway, 'binding': binding, 'clock': clock, 'data_ref': references['data_key'],
            'protect_text': protect_text, 'backup': backup, 'catalog': catalog, 'preview': preview,
            'key_metadata': tuple(ref.to_wire() for ref in references.values()),
            'phase4': config['schema_version'] == 'ds.bootstrap.v2', 'fields': fields}


def assemble_field_backfill(*, config_path):
    from django.apps import apps
    from data_security.adapters.persistence.fields import bind_field_storage
    from data_security.adapters.persistence.field_migration import FieldBackfill
    components = assemble(config_path=config_path)
    require(components['fields'] is not None, ReasonCode.KEY_UNAVAILABLE)
    bind_field_storage(components['fields'])
    owners = (
        'users.CTFUser', 'ai_assistant.AIMessage', 'agent_runtime.UserMemory', 'agent_runtime.AgentRun',
        'challenges.Challenge', 'challenges.ChallengeSolution', 'exams.TheoryQuestion', 'exams.ExamAnswer',
        'submissions.Submission', 'legal.LegalAnalysisTask', 'legal.LegalEvidence', 'legal.LegalReport',
        'legal.ComplianceAgentRun', 'legal.LegalFactSnapshot', 'student_profiles.StudentProfile',
        'student_profiles.DynamicGrowthProfile', 'student_profiles.LearningPreference',
        'student_profiles.LearningPersona', 'student_profiles.OnboardingInterview',
        'student_profiles.StudentProfileReport', 'audit.AuditEvent', 'audit.AIAuditLog',
    )
    return FieldBackfill(models=tuple(apps.get_model(label) for label in owners), storage=components['fields'])


def assemble_field_rotation(*, config_path):
    from data_security.adapters.persistence.field_rotation import FieldRotation
    backfill = assemble_field_backfill(config_path=config_path)
    return FieldRotation(models=backfill.models.values(), storage=backfill.storage)


def start_application():
    path = os.environ.get('DATA_SECURITY_CONFIG')
    if not path:
        return
    components = assemble(config_path=path)
    from django.conf import settings
    from rest_framework.settings import api_settings
    from rest_framework.views import APIView
    from rest_framework.authentication import SessionAuthentication
    from data_security.adapters.django.authentication import (DisabledTokenAuthentication,
                                                             bind_bootstrap_teacher_inputs)
    from data_security.adapters.django.content import bind_content_protection
    from data_security.adapters.django.logging import install_safe_logging
    from ai_providers import bind_manager
    from audit import bridge
    from export_risk.decisions import outbox
    from ctfsafe.encryption import bind_field_crypto
    from challenges.views import ProxySessionAuthentication, proxy_challenge_view
    bridge.bind(audit=components['audit'], policy_binding=components['binding'], clock=components['clock'],
                event_id=lambda: 'audit/' + _OS_RANDOM(16).hex())
    outbox.bind(audit=components['audit'], policy_binding=components['binding'], clock=components['clock'])
    bind_field_crypto(components['crypto'], key_ref=components['data_ref'], limits=BASELINE_LIMITS)
    bind_bootstrap_teacher_inputs(None)  # No unattended credential creation in formal mode.
    bind_content_protection(components['protect_text'])
    api_settings.DEFAULT_AUTHENTICATION_CLASSES = (SessionAuthentication, DisabledTokenAuthentication)
    APIView.authentication_classes = api_settings.DEFAULT_AUTHENTICATION_CLASSES
    settings.REST_FRAMEWORK['DEFAULT_AUTHENTICATION_CLASSES'] = (
        'rest_framework.authentication.SessionAuthentication',
        'data_security.adapters.django.authentication.DisabledTokenAuthentication')
    proxy_challenge_view.cls.authentication_classes = (ProxySessionAuthentication, DisabledTokenAuthentication)
    install_safe_logging()
    bind_manager(components['manager'])
    if components['phase4']:
        from data_security.adapters.persistence.fields import bind_field_storage
        bind_field_storage(components['fields'])
        from data_security.adapters.django.policy_api import bind_policy_api
        bind_policy_api(catalog=components['catalog'], binding=components['binding'],
                        preview=components['preview'], key_metadata=components['key_metadata'])
