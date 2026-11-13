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
    KeyPurpose, KeyReference, KeyStatus, MediaType, ObjectContext, Outlet, PayloadKind, PolicyBinding,
    ProtectionContext, ProtectionError, Purpose, ReasonCode, Role, SecretMaterial)
from data_security.contracts.schema import reference, require
from data_security.core.redaction import detect, legacy_confidentiality
from data_security.adapters.tabular.legacy import bind_detect
from data_security.adapters.django.legacy import (
    LEGACY_INTERNAL, LEGACY_SECRET, LEGACY_TOKEN, bind_confidentiality,
)

# Identity check is a configuration boundary, not a defence against arbitrary
# Python execution. token_bytes uses SystemRandom -> OS urandom, not random.Random.
_OS_RANDOM = secrets.token_bytes
_PRIVATE_UPLOAD_PATHS = ('/api/resources/upload', '/api/resources/upload/')
_PRIVATE_UPLOAD_PATTERNS = (re.compile(
    r'/api/feedback/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/attachments/?'),)
_PRIVATE_REFERENCE_PATTERNS = tuple(re.compile(pattern) for pattern in (
    r'/api/resources/[0-9]+/(?:download|cover/download|shares|cover/shares)/?',
    r'/api/resources/file-operations/[0-9a-f-]{36}/?',
    r'/api/feedback/[0-9a-f-]{36}/(?:file-operations/[0-9a-f-]{36}|attachments/[0-9a-f-]{36}/(?:download|shares))/?',
    r'/api/data-security/(?:files/shares/[0-9a-f-]{36}|exports/(?:resources|recovery)/[^/]+)/?',
))


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


def _bootstrap_file_permissions(path):
    if os.name == 'nt':
        from data_security.adapters.private_permissions import is_private_path
        return is_private_path(path)
    return not path.stat().st_mode & 0o022


def _configuration(path):
    from data_security.adapters.keys import FileKeyResolver
    source = Path(path)
    require(source.is_absolute() and source == source.resolve() and
            _bootstrap_file_permissions(source) and source.stat().st_size <= 65536,
            ReasonCode.AUTHORIZATION_DENIED)
    config = json.loads(source.read_bytes())
    require(type(config) is dict, ReasonCode.INVALID_TYPE)
    version = config.get('schema_version')
    require(version in ('ds.bootstrap.v1', 'ds.bootstrap.v2'), ReasonCode.UNKNOWN_SCHEMA)
    fields = {'schema_version', 'environment', 'key_manifest', 'policy_file', 'policy_binding',
              'framework_key', 'data_key', 'audit_key', 'providers', 'backup'}
    if version == 'ds.bootstrap.v2':
        fields |= {'policy_repository'}
        fields |= {'field_storage', 'audit_chain', 'export_recovery', 'export_delivery', 'private_files',
                   'retained_data_keys', 'canary', 'reveal_requests', 'export_retention', 'reveal_retention'} & config.keys()
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
                _bootstrap_file_permissions(recovery) and recovery.stat().st_size <= 65536,
                ReasonCode.AUTHORIZATION_DENIED)
        import hashlib
        record = recovery.read_bytes()
        require(hashlib.sha256(record).hexdigest() == proof['sha256'], ReasonCode.HASH_MISMATCH)
        record = json.loads(record)
        require(record.get('returncode') == 0 and record.get('key_material_in_evidence') is False and
                record.get('recovery_observations', {}).get('receipt_durability') == 'durable' and
                bool(record.get('recovery_observations', {}).get('checks')), ReasonCode.AUTHORIZATION_DENIED)
    if 'reveal_requests' in config:
        options = config['reveal_requests']
        require(type(options) is dict and set(options) == {'enabled'} and type(options['enabled']) is bool,
                ReasonCode.INVALID_VALUE)
    if 'export_retention' in config:
        options = config['export_retention']
        require(type(options) is dict and set(options) - {'journal_root'} == {'scope_ref'}, ReasonCode.UNKNOWN_FIELD)
        reference(options['scope_ref'])
        if 'journal_root' in options:
            require(type(options['journal_root']) is str, ReasonCode.INVALID_TYPE)
    if 'reveal_retention' in config:
        options = config['reveal_retention']
        require(type(options) is dict and set(options) == {'scope_ref'}, ReasonCode.UNKNOWN_FIELD)
        reference(options['scope_ref'])
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


def assemble(*, config_path, random_bytes=_OS_RANDOM, policy=None, keys=None, audit=None, _recovery=False):
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
    retained_data = config.get('retained_data_keys', [])
    require(type(retained_data) is list and len(retained_data) <= 64, ReasonCode.INVALID_VALUE)
    retained_data = tuple(KeyReference.from_wire(item) for item in retained_data)
    for ref in retained_data:
        require(ref.purpose is KeyPurpose.DATA and ref.status is KeyStatus.READ_ONLY and
                ref.key_ref not in references, ReasonCode.KEY_UNAVAILABLE)
        material = resolver.resolve(ref, KeyPurpose.DATA, identity)
        require(type(material) is SecretMaterial, ReasonCode.KEY_UNAVAILABLE)
        value = bytes(material.borrow(KeyPurpose.DATA))
        require(value not in values, ReasonCode.KEY_UNAVAILABLE)
        values.add(value)
        references[ref.key_ref] = ref
    crypto = CryptoService(keys=resolver, service_identity=identity, random_bytes=random_bytes,
        environment=Environment.EVALUATION, limits=BASELINE_LIMITS, retained_data_keys=retained_data)
    audit_options = {}
    if 'audit_chain' in config:
        options = config['audit_chain']
        require(type(options) is dict and set(options) == {'chain_version', 'project_ref', 'object_uuid',
            'object_version', 'authorization_ref', 'retained_keys', 'checkpoint_root', 'checkpoint_ref'},
            ReasonCode.UNKNOWN_FIELD)
        require(options['chain_version'] == 'ds.audit.v2' and type(options['retained_keys']) is list and
                (options['checkpoint_root'] is None or type(options['checkpoint_root']) is str),
                ReasonCode.INVALID_VALUE)
        audit_context = ObjectContext(schema_version=ObjectContext.SCHEMA, environment=Environment.EVALUATION,
            project_ref=options['project_ref'], object_uuid=options['object_uuid'],
            object_version=options['object_version'], field_ref='audit/ledger.v2',
            authorization_ref=options['authorization_ref'])
        retained = tuple(KeyReference.from_wire(item) for item in options['retained_keys'])
        for ref in retained:
            require(ref.purpose is KeyPurpose.AUDIT and ref.status is KeyStatus.READ_ONLY,
                    ReasonCode.KEY_UNAVAILABLE)
            material = resolver.resolve(ref, KeyPurpose.AUDIT, identity)
            require(type(material) is SecretMaterial, ReasonCode.KEY_UNAVAILABLE)
            value = bytes(material.borrow(KeyPurpose.AUDIT))
            require(value not in values, ReasonCode.KEY_UNAVAILABLE)
            values.add(value)
            references[ref.key_ref] = ref
        audit_options = dict(crypto=crypto, key=references['audit_key'], context=audit_context,
            retained_keys=retained, checkpoint_root=options['checkpoint_root'], checkpoint_ref=options['checkpoint_ref'])
    sink = DjangoAuditSink(clock=clock, **audit_options)
    if sink.checkpoint_ref is not None and not _recovery:
        require(type(sink.verify('ds.audit.v2')) is not ProtectionError, ReasonCode.AUDIT_UNAVAILABLE)
    # The isolated recovery verifier checks the selected checkpoint inside its read-only snapshot.
    gateway = AuditGateway(sink=sink)
    catalog = PolicyCatalog(repository=repository, clock=clock, management=choice['writable'], audit=gateway)
    snapshot = catalog.snapshot(binding)
    require(type(snapshot) is not ProtectionError, ReasonCode.POLICY_NOT_APPROVED)
    if config['schema_version'] == 'ds.bootstrap.v1':
        require(snapshot.approval.approval_ref == 'approval/phase3-20261105-1329', ReasonCode.POLICY_NOT_APPROVED)
    protection = ProtectionService(policies=catalog, audit=gateway, clock=clock,
        random_bytes=random_bytes, environment=Environment.EVALUATION, limits=BASELINE_LIMITS,
        field_ref='content/body', authenticated_audit=bool(audit_options))

    def context(outlet):
        return ProtectionContext(schema_version=ProtectionContext.SCHEMA, actor_ref=identity,
            authorization_ref='authorization/phase3-isolated', scope_refs=('content/body',),
            environment=Environment.EVALUATION, domain='ctf', outlet=outlet, purpose=Purpose.ANALYSIS,
            role=Role.SERVICE, object_ref='request/content', object_version='v1',
            source_ref=None, source_version=None, source_hash=None, trace_id='trace/' + random_bytes(16).hex())

    backup = _backup_adapter(config, resolver, clock)
    canaries = (_canary_components(config['canary'], crypto=crypto, data_key=references['data_key'],
        audit=gateway, binding=binding, clock=clock, backup=backup) if 'canary' in config else None)
    if canaries is not None:
        canaries['log_context'] = context(Outlet.LOG)
    else:
        from data_security.adapters.persistence.canary_catalog import CanaryRegistration
        try:
            has_canaries = CanaryRegistration.objects.exists()
        except Exception as error:
            if getattr(error.__cause__, 'pgcode', None) != '42P01':
                raise
            has_canaries = False
        require(not has_canaries, ReasonCode.SOURCE_NOT_APPROVED)
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
            confidentiality=_confidentiality, limits=BASELINE_LIMITS, service_identity=identity, clock=clock,
            canary=canaries['tools'] if canaries is not None else None)
        handles.append(ProviderHandle(name=provider['endpoint_ref'], model=provider['models'][0], port=adapter,
                                      context_factory=context, binding=binding, limits=BASELINE_LIMITS,
                                      sanitize_response=lambda value: sanitize_output(value)[0], run_sync=run_port))
    require(len({handle.name for handle in handles}) == len(handles), ReasonCode.INVALID_VALUE)

    def protect_text(value):
        payload = BoundedPayload(schema_version=BoundedPayload.SCHEMA, kind=PayloadKind.TEXT,
            media_type=MediaType.TEXT, text=_confidentiality(value), tree=None, binary=None, limits=BASELINE_LIMITS)
        result = call_port(protection.protect, payload, context(Outlet.MODEL), binding)
        if type(result) is ProtectionError:
            raise RuntimeError(result.code.value)
        return result.payload.text

    def protect_value(value, *, outlet=Outlet.API, object_ref='request/content', object_version='v1'):
        from dataclasses import replace
        json_value = not isinstance(value, str)
        value = _confidentiality(value)
        payload = BoundedPayload(schema_version=BoundedPayload.SCHEMA,
            kind=PayloadKind.JSON if json_value else PayloadKind.TEXT,
            media_type=MediaType.JSON if json_value else MediaType.TEXT,
            text=None if json_value else value, tree=FrozenJSON(value) if json_value else None,
            binary=None, limits=BASELINE_LIMITS)
        protection_context = replace(context(outlet), object_ref=object_ref, object_version=object_version)
        result = call_port(protection.protect, payload, protection_context, binding)
        if type(result) is ProtectionError:
            raise RuntimeError(result.code.value)
        return result.payload.tree.to_value() if json_value else result.payload.text

    def protect_rag_value(value, *, outlet=Outlet.RAG, object_ref='rag/content', object_version='v1'):
        require(bool(audit_options), ReasonCode.AUDIT_UNAVAILABLE)
        return protect_value(value, outlet=outlet, object_ref=object_ref, object_version=object_version)

    reveal_retention = None
    if 'reveal_retention' in config:
        from data_security.adapters.persistence.reveal_retention import DjangoRevealRetention
        require('field_storage' in config and sink.crypto is not None, ReasonCode.SOURCE_NOT_APPROVED)
        reveal_retention = DjangoRevealRetention(scope_ref=config['reveal_retention']['scope_ref'],
            audit=gateway, policy_binding=binding, clock=clock)
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
            if key.key_ref in references:
                require(purpose is KeyPurpose.DATA and references[key.key_ref] == key,
                        ReasonCode.KEY_UNAVAILABLE)
                continue
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
            index_deadline=datetime.fromisoformat(deadline) if deadline is not None else None,
            register_retention=reveal_retention.register_field if reveal_retention is not None else None)

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

    components = {'manager': MultiProviderManager(handles), 'protection': protection, 'crypto': crypto,
        'audit': gateway, 'binding': binding, 'clock': clock, 'data_ref': references['data_key'],
        'protect_text': protect_text, 'protect_value': protect_value, 'protect_rag_value': protect_rag_value,
        'backup': backup, 'catalog': catalog, 'preview': preview,
        'key_metadata': tuple(ref.to_wire() for ref in references.values()),
        'phase4': config['schema_version'] == 'ds.bootstrap.v2', 'fields': fields,
        'canary': canaries, 'security_runtime': None, 'reveal_requests': None, 'reveal_source': None,
        'export_lifecycle': None, 'reveal_retention': reveal_retention}
    if 'reveal_requests' in config and config['reveal_requests']['enabled']:
        from data_security.adapters.persistence.reveal import DjangoRevealRepository
        require(fields is not None and sink.crypto is not None, ReasonCode.SOURCE_NOT_APPROVED)
        components['reveal_requests'] = partial(assemble_reveal, components=components)
        components['reveal_source'] = DjangoRevealRepository(fields=fields, clock=clock).lookup
    if canaries is not None:
        from agent_runtime.gateway import AgentGateway
        canaries['owner'].read_flag = (lambda target: fields.read(target, 'flag')) if fields is not None else None
        provider = next((handle for handle in handles if handle.name == canaries['provider_ref']), None)
        require(provider is not None, ReasonCode.PROVIDER_UNAVAILABLE)
        components['security_runtime'] = AgentGateway(security_tools=canaries['registry'], security_provider=provider)
    components['recover_export'] = (_export_recovery_api(components, config['export_recovery'])
                                    if 'export_recovery' in config else None)
    components['export_delivery'] = (_resource_exports(components, config['export_delivery'])
                                      if 'export_delivery' in config else None)
    components['private_uploads'], components['file_shares'] = {}, None
    if 'private_files' in config:
        from django.conf import settings
        from uuid import UUID
        from data_security.adapters.persistence.file_shares import DjangoPrivateFileShares
        options = config['private_files']
        require(type(options) is dict and set(options) == {'private_root', 'project_ref'}, ReasonCode.UNKNOWN_FIELD)
        root = Path(options['private_root'])
        require(root.is_absolute() and root == root.resolve(), ReasonCode.AUTHORIZATION_DENIED)
        for public in (settings.MEDIA_ROOT, settings.STATIC_ROOT):
            if public:
                public = Path(public).resolve()
                require(not root.is_relative_to(public) and not public.is_relative_to(root),
                        ReasonCode.AUTHORIZATION_DENIED)
        if 'export_delivery' in config:
            require(all(options[key] == config['export_delivery'][key] for key in options),
                    ReasonCode.SOURCE_NOT_APPROVED)
        require(components['audit'].sink.crypto is not None, ReasonCode.SOURCE_NOT_APPROVED)
        components['private_uploads'] = _private_upload_owners(components,
            private_root=root, project_ref=options['project_ref'], downloads=True)
        components['file_shares'] = DjangoPrivateFileShares(owners=components['private_uploads'],
            audit=gateway, read_event=sink.read_authenticated, policy_binding=binding, clock=clock,
            identity=lambda: str(UUID(bytes=_OS_RANDOM(16))))
    components['recovery_admission'] = None
    if backup is not None and backup.full_inventory:
        from data_security.adapters.persistence.recovery_state import recovery_admission
        for name in ('private_files', 'export_delivery'):
            if name in config:
                require(Path(config[name]['private_root']) == backup.private_root, ReasonCode.SOURCE_NOT_APPROVED)
        components['recovery_admission'] = partial(recovery_admission, backup.private_root,
            backup.source_identity, limits=BASELINE_LIMITS)
    components['statistics'] = None
    if components['phase4']:
        from data_security.adapters.persistence.report_records import DjangoReportRepository
        from data_security.adapters.persistence.statistics import read_statistics
        from data_security.application.reports import ReportAuthenticator

        def verify_retained_report(record):
            key = sink.keys.get(record.proof.key.key_ref)
            if key is None:
                return ProtectionError(schema_version=ProtectionError.SCHEMA, code=ReasonCode.KEY_UNAVAILABLE,
                                       retryable=False, trace_id='statistics/report')
            # Historical integrity only; no current grant, delivery or file access.
            authenticator = ReportAuthenticator(crypto=crypto, key=key,
                executor_ref='service/resource-column-export', environment=Environment.EVALUATION,
                clock=lambda: record.report.created_at)
            return authenticator.verify(record.report, record.proof, record.binding, record.plan, record.context,
                input_hash=record.plan.input_hash, output_hash=record.report.output_hash,
                ciphertext_hash=record.stored.ciphertext_hash)

        capabilities = [{'capability': name, 'state': 'enabled-unverified' if enabled else 'disabled'}
            for name, enabled in (('field-protection', fields is not None), ('text-rag', True),
                ('reveal-requests', components['reveal_requests'] is not None),
                ('resource-export', components['export_delivery'] is not None),
                ('private-files', bool(components['private_uploads'])))]
        components['statistics'] = partial(read_statistics,
            reports=DjangoReportRepository(environment=Environment.EVALUATION),
            verify_report=verify_retained_report, capabilities=capabilities, clock=clock, limits=BASELINE_LIMITS)
        if 'export_retention' in config:
            from data_security.adapters.persistence.export_lifecycle import DjangoExportLifecycle
            require(sink.crypto is not None and sink.checkpoint_root is not None, ReasonCode.AUDIT_UNAVAILABLE)
            options = config['export_retention']
            store, journal = None, None
            if 'journal_root' in options:
                from django.conf import settings
                from data_security.adapters.persistence.export_retention_journal import ExportRetentionJournal
                from data_security.adapters.persistence.private_store import DjangoPrivateStore
                private = config.get('private_files', config.get('export_delivery'))
                require(private is not None, ReasonCode.SOURCE_NOT_APPROVED)
                root = Path(options['journal_root'])
                separate = [private['private_root'], sink.checkpoint_root, settings.MEDIA_ROOT, settings.STATIC_ROOT]
                if backup is not None:
                    separate.extend([backup.directory, backup.private_root])
                for path in separate:
                    if path:
                        path = Path(path).resolve()
                        require(not root.is_relative_to(path) and not path.is_relative_to(root),
                                ReasonCode.SOURCE_NOT_APPROVED)
                store = DjangoPrivateStore(root=private['private_root'], crypto=crypto, environment=Environment.EVALUATION)
                journal = ExportRetentionJournal(root=root, scope_ref=options['scope_ref'], sink=sink, limits=BASELINE_LIMITS)
            components['export_lifecycle'] = DjangoExportLifecycle(scope_ref=options['scope_ref'],
                reports=DjangoReportRepository(environment=Environment.EVALUATION),
                verify_report=verify_retained_report, audit=gateway, read_event=sink.read_authenticated,
                clock=clock, limits=BASELINE_LIMITS, store=store, journal=journal)
    return components


def assemble_reveal(*, components):
    """One request-scoped repository; this factory does not enable an HTTP route."""
    from data_security.application.reveal import RevealFlow
    from data_security.adapters.persistence.reveal import DjangoRevealRepository
    from data_security.adapters.persistence.uow import DjangoUnitOfWork

    require(components['fields'] is not None, ReasonCode.SOURCE_NOT_APPROVED)
    require(components['audit'].sink.crypto is not None, ReasonCode.AUDIT_UNAVAILABLE)
    repository = DjangoRevealRepository(fields=components['fields'], clock=components['clock'],
        policy_binding=components['binding'], read_event=components['audit'].sink.read_authenticated,
        retention=components.get('reveal_retention'))
    return RevealFlow(repository=repository, sources=repository, crypto=components['crypto'],
        policies=components['catalog'], policy_binding=components['binding'], audit=components['audit'],
        uow_factory=DjangoUnitOfWork, clock=components['clock'], limits=BASELINE_LIMITS,
        requests=repository, protection=components['protection'],
        reason_field_ref=components['protection'].field_ref, identifier=lambda: _OS_RANDOM(16).hex())


def _canary_components(options, *, crypto, data_key, audit, binding, clock, backup):
    from data_security.contracts import CanarySeed
    from data_security.application.canary import CanaryTools
    from data_security.adapters.django.canary_tools import CanaryToolRegistry
    from data_security.adapters.persistence.canary_targets import DjangoCanaryTargets
    from data_security.adapters.persistence.recovery_state import recovery_admission

    require(type(options) is dict and set(options) == {'seeds', 'project_ref', 'provider_ref'},
            ReasonCode.UNKNOWN_FIELD)
    require(type(options['seeds']) is list and 0 < len(options['seeds']) <= BASELINE_LIMITS.max_findings,
            ReasonCode.LIMIT_EXCEEDED)
    require(options['provider_ref'] in ('volcano', 'deepseek', 'moonshot', 'qwen') and
            audit.sink.crypto is not None and backup is not None and backup.full_inventory,
            ReasonCode.SOURCE_NOT_APPROVED)
    seeds = tuple(CanarySeed.from_wire(value) for value in options['seeds'])
    owner = DjangoCanaryTargets(seeds=seeds, crypto=crypto, data_key=data_key,
        project_ref=options['project_ref'], environment=Environment.EVALUATION, domain='ctf',
        audit=audit, read_event=audit.sink.read_authenticated,
        recovery_events=lambda: audit.sink.inspect_recovery(BASELINE_LIMITS), policy_binding=binding,
        clock=clock, limits=BASELINE_LIMITS,
        admission=partial(recovery_admission, backup.private_root, backup.source_identity, limits=BASELINE_LIMITS))
    tools = CanaryTools(seeds=seeds, environment=Environment.EVALUATION, domain='ctf',
        limits=BASELINE_LIMITS, policy_binding=binding, authorize=owner.authorize,
        plant_target=owner.plant_target, audit=audit, clock=clock,
        event_id=lambda: 'canary/check/' + _OS_RANDOM(16).hex())
    owner.catalog_inventory()
    registry = CanaryToolRegistry(plant=tools.plant, checker=tools, resolve_context=owner.resolve_context,
                                 load_output=owner.load_output)
    return {'owner': owner, 'tools': tools, 'registry': registry, 'seeds': seeds,
            'provider_ref': options['provider_ref']}


def assemble_canary_runtime(*, config_path):
    """Explicit internal model-driven tool entry; no HTTP or default learning writes."""
    components = assemble(config_path=config_path)
    require(components['security_runtime'] is not None, ReasonCode.SOURCE_NOT_APPROVED)
    return components['security_runtime']


def _backup_adapter(config, resolver, clock, *, identity_ref=None):
    from data_security.adapters.persistence.backup import PostgresAgeBackup

    if config['backup'] is None:
        return None
    options = config['backup']
    require(type(options) is dict, ReasonCode.INVALID_TYPE)
    fields = {'database', 'directory', 'checks', 'age', 'pg_dump', 'pg_restore'}
    if config['schema_version'] == 'ds.bootstrap.v2' and 'private_root' in options:
        fields |= {'private_root', 'code_version', 'required_keys'}
        fields |= {'full_inventory'} & options.keys()
    require(set(options) == fields, ReasonCode.UNKNOWN_FIELD)
    require(options['database'].get('host') in ('127.0.0.1', '::1') and
            not options['database'].get('password'), ReasonCode.AUTHORIZATION_DENIED)
    private = {}
    if 'private_root' in options:
        require(type(options['private_root']) is str and type(options['required_keys']) is list,
                ReasonCode.INVALID_TYPE)
        private = dict(private_root=Path(options['private_root']), code_version=options['code_version'],
            required_keys=tuple(KeyReference.from_wire(item) for item in options['required_keys']),
            full_inventory=options.get('full_inventory', False), limits=BASELINE_LIMITS)
    return PostgresAgeBackup(resolver=resolver, service_identity='service/security', database=options['database'],
        directory=Path(options['directory']), checks=tuple(tuple(check) for check in options['checks']),
        environment=Environment.EVALUATION, domain='ctf', age=Path(options['age']),
        pg_dump=Path(options['pg_dump']), pg_restore=Path(options['pg_restore']), clock=clock,
        identity_ref=identity_ref, **private)


def assemble_recovery(*, config_path, identity, archive_directory=None, archive_identity=None):
    """Offline target entry. Construction neither reads database tables nor starts HTTP."""
    from data_security.adapters.persistence.recovery_state import RecoveryJournal
    from data_security.application.backup_recovery import RecoveryFlow

    config, resolver = _configuration(config_path)
    require(type(identity) is KeyReference and identity.purpose is KeyPurpose.BACKUP_PRIVATE
            and identity.status in (KeyStatus.ACTIVE, KeyStatus.READ_ONLY), ReasonCode.KEY_UNAVAILABLE)
    clock = lambda: datetime.now(timezone.utc)
    backup = _backup_adapter(config, resolver, clock, identity_ref=identity)
    require(backup is not None and backup.full_inventory, ReasonCode.SOURCE_NOT_APPROVED)
    journal = RecoveryJournal(root=backup.private_root, target_identity=backup.source_identity,
        code_version=backup.code_version, environment=Environment.EVALUATION, domain='ctf',
        service_identity='service/security', clock=clock, limits=BASELINE_LIMITS)

    def verify_owners(context):
        from django.apps import apps
        from data_security.adapters.persistence.private_store import DjangoPrivateStore
        from data_security.adapters.persistence.report_records import DjangoReportRepository
        from data_security.adapters.persistence.file_shares import DjangoPrivateFileShares
        from data_security.adapters.persistence.recovery_verifier import DjangoRecoveryVerifier
        from data_security.adapters.persistence.legacy_archive import DjangoLegacyAuditArchive
        from data_security.application.reports import ReportAuthenticator

        components = assemble(config_path=config_path, _recovery=True)
        require(components['backup'].source_identity == backup.source_identity
                and components['backup'].code_version == backup.code_version, ReasonCode.SOURCE_NOT_APPROVED)
        sink = components['audit'].sink
        require(sink.crypto is not None and sink.checkpoint_ref is not None, ReasonCode.AUDIT_UNAVAILABLE)
        private = config.get('private_files', config.get('export_delivery', {}))
        owners = _private_upload_owners(components, private_root=backup.private_root,
            project_ref=private.get('project_ref', 'ctf'))
        store = DjangoPrivateStore(root=backup.private_root, crypto=components['crypto'], environment=Environment.EVALUATION)

        def verify_report(record):
            key = sink.keys.get(record.proof.key.key_ref)
            require(key is not None, ReasonCode.KEY_UNAVAILABLE)
            # Historical integrity only. Actual delivery still uses the current clock and ACL.
            authenticator = ReportAuthenticator(crypto=components['crypto'], key=key,
                executor_ref='service/resource-column-export', environment=Environment.EVALUATION,
                clock=lambda: record.report.created_at)
            return authenticator.verify(record.report, record.proof, record.binding, record.plan, record.context,
                input_hash=record.plan.input_hash, output_hash=record.report.output_hash,
                ciphertext_hash=record.stored.ciphertext_hash)

        def inspect_share(share_id, read_event):
            owner = DjangoPrivateFileShares(owners=owners, audit=components['audit'], read_event=read_event,
                policy_binding=components['binding'], clock=clock, identity=None)
            return owner._load(share_id, terminal=True)

        archives = None
        if archive_directory is not None:
            require(type(archive_identity) is KeyReference and archive_identity.purpose is KeyPurpose.BACKUP_PRIVATE
                    and archive_identity.status in (KeyStatus.ACTIVE, KeyStatus.READ_ONLY), ReasonCode.KEY_UNAVAILABLE)
            archives = DjangoLegacyAuditArchive(directory=archive_directory, age=backup.age, keys=resolver,
                service_identity='service/security', environment=Environment.EVALUATION, domain='ctf',
                policy_binding=components['binding'], limits=BASELINE_LIMITS, clock=clock)
        verification = DjangoRecoveryVerifier(store=store, owners=owners, audit=sink,
            reports=DjangoReportRepository(environment=Environment.EVALUATION), verify_report=verify_report,
            field_storage=components['fields'], field_models=tuple(apps.get_model(label) for label in _FIELD_OWNERS),
            inspect_share=inspect_share, limits=BASELINE_LIMITS, clock=clock, database=backup.database,
            archives=archives, archive_identity=archive_identity,
            export_lifecycle=components['export_lifecycle'])(context)
        if type(verification) is ProtectionError or components['canary'] is None:
            return verification
        canary_recovery = components['canary']['owner'].restore_catalog()
        if type(canary_recovery) is ProtectionError:
            return canary_recovery
        return dict(verification, canary_catalog=canary_recovery,
            data_key_refs=sorted(set(verification['data_key_refs']) | set(canary_recovery['data_key_refs'])))

    def replay_governance(context):
        components = assemble(config_path=config_path, _recovery=True)
        require(components['backup'].source_identity == backup.source_identity
                and components['backup'].code_version == backup.code_version, ReasonCode.SOURCE_NOT_APPROVED)
        return components['export_lifecycle'].replay(context, recovery_journal=journal)

    return RecoveryFlow(backups=backup, journal=journal, verify_owners=verify_owners, clock=clock,
        replay_governance=replay_governance if 'journal_root' in config.get('export_retention', {}) else None)


def _verified_recovery_point(components, proof):
    from data_security.adapters.persistence.recovery_state import VerifiedRecoveryPoint

    backup = components['backup']
    require(backup is not None and backup.full_inventory and type(proof) is dict
            and set(proof) == {'path', 'sha256'}, ReasonCode.SOURCE_NOT_APPROVED)
    return VerifiedRecoveryPoint(path=proof['path'], sha256=proof['sha256'],
        source_identity=backup.source_identity, code_version=backup.code_version,
        environment=Environment.EVALUATION, domain='ctf', limits=BASELINE_LIMITS)


def assemble_legacy_archives(*, config_path, directory, age, recipient, identity=None, recovery_proof=None):
    """Explicit isolated archival; private-key content checks require a separate opt-in."""
    from audit.legacy_archives import LegacyArchiveOwner
    from data_security.adapters.persistence.legacy_archive import DjangoLegacyAuditArchive
    from data_security.application.legacy_archive import LegacyArchiveFlow

    components = assemble(config_path=config_path)
    require(components['audit'].sink.crypto is not None, ReasonCode.SOURCE_NOT_APPROVED)
    require(type(recipient) is KeyReference and recipient.purpose is KeyPurpose.BACKUP_PUBLIC
            and recipient.status is KeyStatus.ACTIVE, ReasonCode.KEY_UNAVAILABLE)
    require(identity is None or (type(identity) is KeyReference and identity.purpose is KeyPurpose.BACKUP_PRIVATE
            and identity.status is not KeyStatus.RETIRED), ReasonCode.KEY_UNAVAILABLE)
    archives = DjangoLegacyAuditArchive(directory=directory, age=age, keys=components['crypto'].keys,
        service_identity='service/security', environment=Environment.EVALUATION, domain='ctf',
        policy_binding=components['binding'], limits=BASELINE_LIMITS, clock=components['clock'])
    flow = LegacyArchiveFlow(archives=archives, audit=components['audit'],
        read_event=components['audit'].sink.read_authenticated, recipient=recipient,
        policy_binding=components['binding'], clock=components['clock'], service_identity='service/security',
        identity=identity, checkpoint=components['audit'].sink.checkpoint if recovery_proof is not None else None,
        verify_recovery=_verified_recovery_point(components, recovery_proof) if recovery_proof is not None else None)
    return LegacyArchiveOwner(capture=flow.capture, reconcile=flow.reconcile,
        identity=lambda: _OS_RANDOM(16).hex(), environment=Environment.EVALUATION, domain='ctf',
        verify_content=flow.verify_content if identity is not None else None,
        govern=flow.govern if identity is not None and recovery_proof is not None else None)


def assemble_backup_cycle(*, config_path, recipient):
    """Explicit daily/weekly entry; the online service receives only an age recipient."""
    from data_security.application.backup_recovery import BackupCycle

    components = assemble(config_path=config_path)
    require(type(recipient) is KeyReference and recipient.purpose is KeyPurpose.BACKUP_PUBLIC
            and recipient.status is KeyStatus.ACTIVE, ReasonCode.KEY_UNAVAILABLE)
    require(components['backup'] is not None, ReasonCode.SOURCE_NOT_APPROVED)
    return BackupCycle(backups=components['backup'], recipient=recipient, limits=BASELINE_LIMITS,
        clock=components['clock'], identity=lambda: _OS_RANDOM(16).hex())


def assemble_export_retention(*, config_path):
    """Explicit new-export preview/apply; deletion requires a separate initialized external journal."""
    owner = assemble(config_path=config_path)['export_lifecycle']
    require(owner is not None, ReasonCode.SOURCE_NOT_APPROVED)
    return owner


def assemble_backup_retention(*, config_path):
    """Explicit isolated D8 entry; no scheduler, default cleanup or production activation."""
    from data_security.application.backup_retention import BackupRetention

    components = assemble(config_path=config_path)
    backup = components['backup']
    require(backup is not None and backup.private_root is not None, ReasonCode.SOURCE_NOT_APPROVED)
    return BackupRetention(backups=backup, limits=BASELINE_LIMITS)


def assemble_resource_uploads(*, config_path, private_root, project_ref, source_reads=False):
    """Explicit owner capability; this does not bind HTTP or authorize old-file access."""
    require(type(source_reads) is bool, ReasonCode.INVALID_TYPE)
    components = assemble(config_path=config_path)
    require(not source_reads or components['audit'].sink.crypto is not None, ReasonCode.SOURCE_NOT_APPROVED)
    return _private_upload_owners(components, private_root=private_root,
        project_ref=project_ref, source_reads=source_reads)['resources']


def assemble_feedback_uploads(*, config_path, private_root, project_ref):
    """Explicit feedback candidates only; no HTTP enablement or legacy migration."""
    return _private_upload_owners(assemble(config_path=config_path),
        private_root=private_root, project_ref=project_ref)['feedback']


def assemble_private_maintenance(*, config_path, private_root, project_ref, legacy_root, recovery_proof=None):
    """Owner-only staging/governance; this does not add a maintenance HTTP endpoint."""
    components = assemble(config_path=config_path)
    require(components['audit'].sink.crypto is not None, ReasonCode.SOURCE_NOT_APPROVED)
    proof = _verified_recovery_point(components, recovery_proof) if recovery_proof is not None else None
    if proof is not None:
        require(Path(private_root) == components['backup'].private_root, ReasonCode.SOURCE_NOT_APPROVED)
    return _private_upload_owners(components, private_root=private_root, project_ref=project_ref,
        legacy_root=legacy_root, verify_recovery=proof)


def _private_upload_owners(components, *, private_root, project_ref, source_reads=False, downloads=False,
                           legacy_root=None, verify_recovery=None):
    from uuid import UUID
    from data_security.contracts.schema import reference
    from data_security.adapters.persistence.private_store import DjangoPrivateStore
    from data_security.adapters.persistence.file_operations import DjangoFileOperations
    from data_security.application.private_files import PrivateFilePreparation
    from resources.private_uploads import ResourcePrivateUploads
    from feedback_center.private_uploads import FeedbackPrivateUploads

    reference(project_ref)
    store = DjangoPrivateStore(root=private_root, crypto=components['crypto'], environment=Environment.EVALUATION)
    operations = DjangoFileOperations(store=store)
    preparation = PrivateFilePreparation(crypto=components['crypto'], data_key=components['data_ref'],
        store=store, limits=BASELINE_LIMITS, operations=operations)
    options = dict(prepare=preparation.prepare, operations=operations,
        object_id=lambda: str(UUID(bytes=_OS_RANDOM(16))), project_ref=project_ref,
        environment=Environment.EVALUATION, limits=BASELINE_LIMITS,
        audit=components['audit'], policy_binding=components['binding'], clock=components['clock'],
        data_key_ref=components['data_ref'].key_ref, read_event=components['audit'].sink.read_authenticated,
        read_download=store.open_verified_source if downloads else None)
    if legacy_root is not None:
        from data_security.adapters.persistence.private_maintenance import DjangoPrivateMaintenance
        options['maintenance'] = DjangoPrivateMaintenance(operations=operations, legacy_root=legacy_root,
            limits=BASELINE_LIMITS, verify_recovery=verify_recovery)
    return {'resources': ResourcePrivateUploads(**options,
                read_source=store.open_verified_source if source_reads else None),
            'feedback': FeedbackPrivateUploads(**options)}


def assemble_export_plan_approvals(*, config_path):
    """Explicit isolated target approval; no source approval, execution or HTTP activation."""
    from audit.export_plans import ExportPlanOwner
    from data_security.adapters.persistence.export_plans import DjangoExportPlanApprovals

    components = assemble(config_path=config_path)
    require(components['audit'].sink.crypto is not None, ReasonCode.SOURCE_NOT_APPROVED)
    permissions = DjangoExportPlanApprovals(record_event=components['audit'].record, clock=components['clock'],
        read_event=components['audit'].sink.read_authenticated)
    return ExportPlanOwner(write_permission=permissions.write, read_permission=permissions.authorize,
        identity=lambda: _OS_RANDOM(16).hex(), clock=components['clock'], environment=Environment.EVALUATION,
        read_approval=permissions.read_approval)


def assemble_recovery_permissions(*, config_path):
    """Explicit permission owner; no automatic role grants or HTTP activation."""
    return _recovery_permission_owner(assemble(config_path=config_path))


def _recovery_permission_owner(components):
    from audit.recovery_permissions import RecoveryPermissionOwner
    from data_security.adapters.persistence.recovery import (
        DjangoRecoveryAuthorization, DjangoRecoveryPermissionWriter,
    )

    writer = DjangoRecoveryPermissionWriter(record_event=components['audit'].record,
        policy_binding=components['binding'], clock=components['clock'])

    def read_permission(principal, authorization_ref, binding, operation):
        return DjangoRecoveryAuthorization(principal=principal, authorization_ref=authorization_ref,
            clock=components['clock'])(binding, operation)

    return RecoveryPermissionOwner(write_permission=writer.write, read_permission=read_permission,
        identity=lambda: _OS_RANDOM(16).hex(), clock=components['clock'], environment=Environment.EVALUATION)


def _resource_exports(components, options):
    """Complete isolated owner composition; no fixture ports, defaults or HTTP downloads."""
    from dataclasses import replace
    import hashlib
    from uuid import UUID

    from audit.export_plans import ExportPlanOwner
    from resources.private_uploads import ResourcePrivateUploads
    from resources.export_sources import ResourceExportSources
    from export_risk.column_authority import ColumnRiskOwner, freeze_request
    from export_risk.contracts import SourceMode
    from data_security.contracts import ResolvedAction, SourceDocument, SourcePlanBinding, SourceTrust, TableScope
    from data_security.adapters.persistence.export_delivery import DjangoResourceExports
    from data_security.adapters.persistence.file_operations import DjangoFileOperations
    from data_security.adapters.persistence.export_plans import DjangoExportPlanApprovals
    from data_security.adapters.persistence.private_store import DjangoPrivateStore
    from data_security.adapters.persistence.quota import DjangoQuotaPort
    from data_security.adapters.persistence.report_records import DjangoReportRepository
    from data_security.adapters.persistence.risk import DjangoRiskPort
    from data_security.adapters.persistence.uow import DjangoUnitOfWork
    from data_security.adapters.tabular.codec import TableCodec
    from data_security.adapters.tabular.source_plans import SourcePlanAdapter
    from data_security.application.export_flow import ExportFlow
    from data_security.application.private_files import PrivateFilePreparation
    from data_security.application.reports import ReportAuthenticator
    from data_security.application.table_reports import TableReportExecutor

    require(components['audit'].sink.crypto is not None, ReasonCode.SOURCE_NOT_APPROVED)
    require(type(options) is dict and set(options) ==
            {'private_root', 'project_ref', 'window_key', 'limit', 'ttl_seconds'}, ReasonCode.UNKNOWN_FIELD)
    require(type(options['private_root']) is str and Path(options['private_root']).is_absolute(),
            ReasonCode.AUTHORIZATION_DENIED)
    clock, binding, gateway = components['clock'], components['binding'], components['audit']
    store = DjangoPrivateStore(root=Path(options['private_root']), crypto=components['crypto'],
                               environment=Environment.EVALUATION)
    operations = DjangoFileOperations(store=store)
    preparation = PrivateFilePreparation(crypto=components['crypto'], data_key=components['data_ref'],
                                         store=store, limits=BASELINE_LIMITS, operations=operations)
    uploads = ResourcePrivateUploads(prepare=preparation.prepare, operations=operations,
        object_id=lambda: str(UUID(bytes=_OS_RANDOM(16))), project_ref=options['project_ref'],
        environment=Environment.EVALUATION, limits=BASELINE_LIMITS, audit=gateway, policy_binding=binding,
        clock=clock, data_key_ref=components['data_ref'].key_ref, read_event=gateway.sink.read_authenticated,
        read_source=store.open_verified_source)

    def freeze(fields, *, request_id, actor_ref, asset_version, scope_ref, quantity):
        return freeze_request(fields, request_id=request_id, subject_id=actor_ref, asset_version=asset_version,
            scope=(scope_ref,), record_count=quantity, environment='evaluation', source_mode=SourceMode.EVALUATION)

    def build_plan(document, approval, expires_at, payload):
        values = document.to_value()
        source = SourceDocument.from_wire(values['source'])
        snapshot = TableCodec(asset_version=values['asset_version']).parse(
            replace(payload, media_type=MediaType.CSV), BASELINE_LIMITS)
        if isinstance(snapshot, ProtectionError):
            return snapshot
        scope_hash = hashlib.sha256(json.dumps(source.document.to_value()['scope'], ensure_ascii=False,
            sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()
        retained = SourcePlanBinding(schema_version=SourcePlanBinding.SCHEMA, source_format=source.source_format,
            source_version=source.source_version, source_plan_hash=approval.content_hash,
            source_record_ref=values['source_ref'], source_record_version='1', source_trust=SourceTrust.SYNTHETIC,
            provenance_ref=values['source_ref'] + '/register', approval_basis_ref=approval.approval_ref,
            approval_basis_version='1', source_state='not-declared', source_environment='evaluation',
            source_domain='ctf', evaluation_ref=values['source_ref'], scope_hash=scope_hash,
            parser_version=None, parser_config_hash=None, requirements_hash=None, operation_contract_version=None)
        adapter = SourcePlanAdapter(source_binding=retained, source_approval=approval,
            scope=TableScope.from_wire(values['scope']), asset_version=values['asset_version'],
            input_hash=values['input_hash'], plan_id=values['source_ref'] + '/plan',
            created_at=clock(), expires_at=expires_at)
        return adapter.to_action_plan(source, snapshot, binding,
            tuple(ResolvedAction.from_wire(value) for value in values['actions']))

    sources = ResourceExportSources(read_references=uploads.authenticated_references,
        read_original=uploads.read_original, freeze_request=freeze, build_plan=build_plan, audit=gateway,
        read_event=gateway.sink.read_authenticated, policy_binding=binding, clock=clock,
        identity=lambda: _OS_RANDOM(16).hex())
    risks = ColumnRiskOwner(audit=gateway, read_event=gateway.sink.read_authenticated, clock=clock)
    permissions = DjangoExportPlanApprovals(record_event=gateway.record, clock=clock,
                                             read_event=gateway.sink.read_authenticated)
    targets = ExportPlanOwner(write_permission=permissions.write, read_permission=permissions.authorize,
        identity=lambda: _OS_RANDOM(16).hex(), clock=clock, environment=Environment.EVALUATION,
        read_approval=permissions.read_approval)
    quota = DjangoQuotaPort(environment='evaluation', window_key=options['window_key'],
                            limit=options['limit'], ttl_seconds=options['ttl_seconds'])
    authenticator = ReportAuthenticator(crypto=components['crypto'], key=gateway.sink.key,
        executor_ref='service/resource-column-export', environment=Environment.EVALUATION, clock=clock)
    def flow_factory(user, owned):
        def authorize(plan, execution, context):
            if components.get('canary') is not None:
                components['canary']['owner']._admitted()
            permitted = sources.authorize(user=user, source_ref=owned.source_ref,
                permission_ref=owned.permission_ref, expected_hash=owned.source_hash,
                expected_plan=owned.source_plan.to_wire())
            return permitted if isinstance(permitted, ProtectionError) else targets.authorize(
                user=user, plan=plan, binding=execution, context=context)

        def load_input(plan, execution, context):
            return sources.load_input(user=user, source_ref=owned.source_ref, permission_ref=owned.permission_ref,
                expected_hash=owned.source_hash, plan=plan, binding=execution, context=context)

        lifecycle = components.get('export_lifecycle')
        stage_candidate = lifecycle.stage_candidate if lifecycle is not None else None
        active_executor = TableReportExecutor(codec_factory=TableCodec, crypto=components['crypto'],
            data_key=components['data_ref'], store=store, authenticator=authenticator,
            limits=BASELINE_LIMITS, clock=clock, stage_candidate=stage_candidate)
        if components.get('canary') is not None:
            from data_security.application.canary import CanaryTools
            configured = components['canary']
            checker = CanaryTools(seeds=configured['seeds'], environment=Environment.EVALUATION, domain='ctf',
                limits=BASELINE_LIMITS, policy_binding=binding,
                authorize=lambda name, principal, seed: authorize(owned.plan, owned.binding, owned.context),
                plant_target=configured['owner'].plant_target, audit=gateway, clock=clock,
                event_id=lambda: 'canary/check/' + _OS_RANDOM(16).hex())
            active_executor = TableReportExecutor(codec_factory=TableCodec, crypto=components['crypto'],
                data_key=components['data_ref'], store=store, authenticator=authenticator,
                limits=BASELINE_LIMITS, clock=clock, canary=checker,
                canary_context_factory=authorize, stage_candidate=stage_candidate)
        risk = DjangoRiskPort(request=owned.request, scope=owned.plan.scope, domain_ref=owned.binding.domain_ref,
            policy_binding=owned.plan.policy_binding, environment='evaluation', assess=owned.risk.assess,
            authorize=owned.risk.authorize, approval=owned.risk.approval, active_until=quota.active_until)
        return ExportFlow(reports=DjangoReportRepository(environment=Environment.EVALUATION,
                lifecycle=components.get('export_lifecycle')),
            authenticator=authenticator, store=store, risk=risk, quota=quota, policies=components['catalog'],
            authorize=authorize, audit=gateway, uow_factory=DjangoUnitOfWork, clock=clock, request=owned.request,
            object_context=owned.context, load_input=load_input,
            executor=active_executor, crypto=components['crypto'], read_event=gateway.sink.read_authenticated)

    return DjangoResourceExports(sources=sources, risks=risks, targets=targets, flow_factory=flow_factory,
        clock=clock, ttl_seconds=quota.ttl_seconds, identity=lambda: _OS_RANDOM(16).hex(), uploads=uploads)


def assemble_export_recovery(*, config_path, user, authorization_ref, window_key, limit, ttl_seconds=300):
    """Recovery-only entry for a retained binding; never exposes execute, commit or publish."""
    from data_security.adapters.persistence.quota import DjangoQuotaPort
    quota = DjangoQuotaPort(environment='evaluation', window_key=window_key, limit=limit, ttl_seconds=ttl_seconds)
    return _export_recovery(assemble(config_path=config_path), user=user,
        authorization_ref=authorization_ref, quota=quota)


def _export_recovery(components, *, user, authorization_ref, quota):
    from data_security.adapters.persistence.report_records import DjangoReportRepository
    from data_security.adapters.persistence.uow import DjangoUnitOfWork
    from data_security.application.export_flow import ExportFlow

    owner = _recovery_permission_owner(components)
    flow = ExportFlow(reports=DjangoReportRepository(environment=Environment.EVALUATION),
        quota=quota, audit=components['audit'], uow_factory=DjangoUnitOfWork,
        clock=components['clock'], policies=components['catalog'],
        # No delivery capability is assembled on this entry. Recovery stays in the same flow.
        authenticator=None, store=None, risk=None, authorize=None,
        authorize_recovery=lambda binding, operation: owner.authorize(user=user, binding=binding,
            operation=operation, authorization_ref=authorization_ref))
    return {'release': flow.release, 'reconcile': flow.reconcile}


def _export_recovery_api(components, options):
    from data_security.adapters.persistence.quota import DjangoQuotaPort
    from data_security.adapters.persistence.report_records import DjangoReportRepository

    require(components['audit'].sink.crypto is not None, ReasonCode.SOURCE_NOT_APPROVED)
    require(type(options) is dict and set(options) == {'window_key', 'limit', 'ttl_seconds'},
            ReasonCode.UNKNOWN_FIELD)
    quota = DjangoQuotaPort(environment='evaluation', **options)
    reports = DjangoReportRepository(environment=Environment.EVALUATION)

    def recover(*, user, execution_ref, permission_ref, operation):
        binding = reports.load_binding(execution_ref)
        if isinstance(binding, ProtectionError):
            return binding
        entry = _export_recovery(components, user=user, authorization_ref=permission_ref, quota=quota)
        return entry[operation](binding)

    return recover


_FIELD_OWNERS = (
    'users.CTFUser', 'ai_assistant.AIMessage', 'agent_runtime.UserMemory', 'agent_runtime.AgentRun',
    'challenges.Challenge', 'challenges.ChallengeSolution', 'exams.TheoryQuestion', 'exams.ExamAnswer',
    'submissions.Submission', 'legal.LegalAnalysisTask', 'legal.LegalEvidence', 'legal.LegalReport',
    'legal.ComplianceAgentRun', 'legal.LegalFactSnapshot', 'student_profiles.StudentProfile',
    'student_profiles.DynamicGrowthProfile', 'student_profiles.LearningPreference',
    'student_profiles.LearningPersona', 'student_profiles.OnboardingInterview',
    'student_profiles.StudentProfileReport', 'audit.AuditEvent', 'audit.AIAuditLog',
)


def assemble_field_backfill(*, config_path):
    from django.apps import apps
    from data_security.adapters.persistence.fields import bind_field_storage
    from data_security.adapters.persistence.field_migration import FieldBackfill
    components = assemble(config_path=config_path)
    require(components['fields'] is not None, ReasonCode.KEY_UNAVAILABLE)
    bind_field_storage(components['fields'])
    return FieldBackfill(models=tuple(apps.get_model(label) for label in _FIELD_OWNERS), storage=components['fields'])


def assemble_field_rotation(*, config_path):
    from data_security.adapters.persistence.field_rotation import FieldRotation
    backfill = assemble_field_backfill(config_path=config_path)
    return FieldRotation(models=backfill.models.values(), storage=backfill.storage)


def private_upload_middleware(get_response):
    from data_security.adapters.django.private_ingress import ClosedPrivateUploadIngress, OpenPrivateUploadIngress
    from data_security.adapters.django.private_files import private_files
    if not os.environ.get('DATA_SECURITY_CONFIG'):
        return get_response
    owner = private_files('resources')
    if owner is not None and not isinstance(owner, ProtectionError):
        return OpenPrivateUploadIngress(get_response, paths=_PRIVATE_UPLOAD_PATHS,
            patterns=_PRIVATE_UPLOAD_PATTERNS, limits=BASELINE_LIMITS)
    return ClosedPrivateUploadIngress(get_response,
        paths=_PRIVATE_UPLOAD_PATHS, patterns=_PRIVATE_UPLOAD_PATTERNS)


def guard_private_upload_asgi(application):
    from dataclasses import replace
    from data_security.adapters.django.private_ingress import ClosedPrivateUploadIngress, OpenPrivateUploadIngress
    from data_security.adapters.django.private_files import private_files
    if not os.environ.get('DATA_SECURITY_CONFIG'):
        return application
    owner = private_files('resources')
    enabled = owner is not None and not isinstance(owner, ProtectionError)
    # Even invalid or currently closed reference requests must not hit Django's disk spool.
    application = OpenPrivateUploadIngress(application, paths=(), patterns=_PRIVATE_REFERENCE_PATTERNS,
        limits=replace(BASELINE_LIMITS, max_bytes=32768, max_text_chars=32768, max_inflight_objects=1)).asgi
    if enabled:
        application = OpenPrivateUploadIngress(application, paths=_PRIVATE_UPLOAD_PATHS,
            patterns=_PRIVATE_UPLOAD_PATTERNS, limits=BASELINE_LIMITS).asgi
    else:
        application = ClosedPrivateUploadIngress(application,
            paths=_PRIVATE_UPLOAD_PATHS, patterns=_PRIVATE_UPLOAD_PATTERNS).asgi
    from data_security.adapters.django.recovery_ingress import guard_recovery_asgi
    return guard_recovery_asgi(application)


def rag_parsers():
    from django.conf import settings
    from rag_ingestion.adapters.parser_plain import PlainTextParser
    from rag_ingestion.adapters.parser_docx import DocxParser
    from rag_ingestion.adapters.parser_pdf import PdfParser
    from rag_ingestion.adapters.parser_markitdown import MarkItDownParser
    classes = (PlainTextParser, DocxParser, PdfParser, MarkItDownParser)
    available = {cls.__module__ + '.' + cls.__name__: cls for cls in classes}
    paths = getattr(settings, 'RAG_INGESTION_PARSERS', None) or list(available)
    require(type(paths) in (list, tuple) and all(path in available for path in paths),
            ReasonCode.SOURCE_NOT_APPROVED)
    return [available[path]() for path in paths]


def assemble_rag(*, chunker=None, embedder=None, repository=None, parser_selector=None, protect=None):
    from rag_ingestion.pipeline import IngestionPipeline
    from rag_ingestion.chunking import StructureAwareChunker
    from rag_ingestion.registry import select_parser
    from rag_ingestion.adapters.embedder_legalkb import LegalKbEmbedder
    from rag_ingestion.adapters.repository_legalkb import LegalKbChunkRepository
    from legal_kb.services.embedding_service import EmbeddingService
    from data_security.adapters.django.rag import protect_rag

    def protect_document(value, **context):
        return {'text': protect_rag(value['text'], **context),
                'metadata': protect_rag(value['metadata'], **context)}

    return IngestionPipeline(
        chunker=chunker if chunker is not None else StructureAwareChunker(),
        embedder=embedder if embedder is not None else LegalKbEmbedder(EmbeddingService()),
        repository=repository if repository is not None else LegalKbChunkRepository(),
        parser_selector=parser_selector if parser_selector is not None else partial(select_parser, parsers=rag_parsers()),
        protect=protect if protect is not None else protect_document)


def start_application():
    from rag_ingestion.registry import bind_ingestion
    from legal_kb.services.embedding_service import EmbeddingService
    from data_security.adapters.django.rag import bind_rag_protection
    from data_security.adapters.django.reveal_api import bind_reveal_api
    from data_security.adapters.django.statistics_api import bind_statistics_api
    bind_reveal_api()
    bind_statistics_api()
    bind_ingestion(parser_factory=rag_parsers, pipeline_factory=assemble_rag,
                   embedding_factory=EmbeddingService)
    path = os.environ.get('DATA_SECURITY_CONFIG')
    if not path:
        bind_rag_protection(None)
        from data_security.runtime.bootstrap import start_runtime_protection
        start_runtime_protection()
        return
    components = assemble(config_path=path)
    bind_rag_protection(components['protect_rag_value'])
    from django.conf import settings
    from data_security.adapters.django.private_files import bind_private_files
    bind_private_files(components.get('private_uploads', {}), components.get('file_shares'))
    from data_security.adapters.django.recovery_ingress import bind_recovery_admission
    bind_recovery_admission(components.get('recovery_admission'))
    settings.DATA_SECURITY_FORMAL_MODE = True
    # A missing private-file capability keeps the pre-body gate closed.
    ingress = 'ctf_backend.security_bootstrap.private_upload_middleware'
    settings.MIDDLEWARE = [ingress, *(item for item in settings.MIDDLEWARE if item != ingress)]
    if components.get('recovery_admission') is not None:
        recovery_gate = 'data_security.adapters.django.recovery_ingress.recovery_middleware'
        settings.MIDDLEWARE = [recovery_gate, *(item for item in settings.MIDDLEWARE if item != recovery_gate)]
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
    canaries = components['canary']
    install_safe_logging(canary=canaries['tools'] if canaries is not None else None,
        canary_context=canaries['log_context'] if canaries is not None else None,
        limits=BASELINE_LIMITS if canaries is not None else None)
    bind_manager(components['manager'])
    from data_security.adapters.django.export_recovery import bind_export_recovery
    from data_security.adapters.django.export_delivery import bind_export_delivery
    bind_export_recovery(components['recover_export'])
    bind_export_delivery(components['export_delivery'])
    if components['phase4']:
        from data_security.adapters.persistence.fields import bind_field_storage
        bind_field_storage(components['fields'])
        from data_security.adapters.django.policy_api import bind_policy_api
        bind_policy_api(catalog=components['catalog'], binding=components['binding'],
                        preview=components['preview'], key_metadata=components['key_metadata'],
                        reveal_state='enabled-unverified' if components['reveal_requests'] is not None else 'disabled')
        bind_statistics_api(components['statistics'])
        if components['reveal_requests'] is not None:
            bind_reveal_api(factory=components['reveal_requests'], clock=components['clock'],
                            identifier=lambda: _OS_RANDOM(16).hex(), limits=BASELINE_LIMITS,
                            source_reader=components['reveal_source'])
