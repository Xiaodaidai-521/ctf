"""Explicit same-process preparation assembly; not an export authority or production switch."""
from dataclasses import replace
from functools import partial
import hashlib
import json
from pathlib import Path
import re
import secrets

from django.conf import settings

from data_security.contracts import (
    BASELINE_LIMITS, Environment, KeyPurpose, KeyReference, KeyStatus, Limits, ProtectionError, ReasonCode, SecretMaterial,
)
from data_security.contracts.schema import digest, reference, require


_UPLOAD_PATHS = ("/api/controlled-export/executions", "/api/controlled-export/executions/")
_LEGACY_DELIVERY_PATHS = (re.compile(r"/api/controlled-export/(?:shares|deliveries)(?:/.*)?"),)


def assemble_private_preparation(*, crypto, data_key, private_root, project_ref, limits: Limits):
    """Inject approved crypto/key inputs explicitly; prepare and observe only verified ciphertext."""
    from data_security.adapters.persistence.private_store import DjangoPrivateStore
    from data_security.adapters.persistence.file_operations import DjangoFileOperations
    from data_security.application.private_files import PrivateFilePreparation
    from controlled_export.services import execute_authorized_export, observe_private_preparation

    require(settings.CONTROLLED_EXPORT_ENVIRONMENT == "evaluation", ReasonCode.SOURCE_NOT_APPROVED)
    require(type(limits) is Limits, ReasonCode.INVALID_TYPE)
    require(limits.max_bytes <= settings.CONTROLLED_EXPORT_MAX_INPUT_BYTES and
            limits.max_rows <= settings.CONTROLLED_EXPORT_MAX_ROWS and
            limits.max_columns <= settings.CONTROLLED_EXPORT_MAX_COLUMNS, ReasonCode.LIMIT_EXCEEDED)
    reference(project_ref)
    legacy_root = Path(settings.CONTROLLED_EXPORT_PRIVATE_ROOT).resolve()
    encrypted_root = Path(private_root).resolve()
    require(not encrypted_root.is_relative_to(legacy_root) and not legacy_root.is_relative_to(encrypted_root),
            ReasonCode.AUTHORIZATION_DENIED)
    store = DjangoPrivateStore(root=private_root, crypto=crypto, environment=Environment.EVALUATION)
    operations = DjangoFileOperations(store=store)
    preparation = PrivateFilePreparation(crypto=crypto, data_key=data_key, store=store, limits=limits, operations=operations)

    def prepare(payload, context):
        with operations.claim(operation_ref="executor-preparation/" + context.object_uuid,
                actor_ref="service/controlled-export", scope_ref="controlled-export/preparations",
                request_hash=hashlib.sha256(payload.binary).hexdigest(), object_uuid=context.object_uuid,
                field_refs=(context.field_ref,)) as operation:
            result = preparation.prepare(payload, context, operation=operation)
            if isinstance(result, ProtectionError):
                return result
            prepared = operations.prepared(operation)
            return prepared if isinstance(prepared, ProtectionError) else result

    def read_prepared(context):
        with operations.claim(operation_ref="executor-preparation/" + context.object_uuid,
                actor_ref="service/controlled-export", scope_ref="controlled-export/preparations") as operation:
            result = operations.prepared(operation, recover=True)
            return result if isinstance(result, ProtectionError) else store.read_prepared(context)

    return {
        "execute": partial(execute_authorized_export, prepare_private=prepare,
                           private_project_ref=project_ref, private_limits=limits),
        "observe": partial(observe_private_preparation, private_project_ref=project_ref),
        "reconcile": partial(observe_private_preparation, private_project_ref=project_ref, read_prepared=read_prepared),
        "limits": limits,
    }


def assemble_recovery(*, backups, crypto, project_ref, limits):
    """Explicit offline adapter inputs, not a request-body or automatic startup capability."""
    from data_security.adapters.persistence.backup import PostgresAgeBackup
    from data_security.adapters.persistence.executor_recovery import DjangoExecutorRecoveryVerifier
    from data_security.adapters.persistence.private_store import DjangoPrivateStore
    from data_security.adapters.persistence.recovery_state import RecoveryJournal
    from data_security.application.backup_recovery import RecoveryFlow
    from controlled_export.services import inspect_private_preparation

    require(type(backups) is PostgresAgeBackup and backups.full_inventory and backups.identity_ref is not None
            and backups.environment is Environment.EVALUATION
            and settings.CONTROLLED_EXPORT_ENVIRONMENT == "evaluation", ReasonCode.SOURCE_NOT_APPROVED)
    require(type(limits) is Limits and limits == backups.limits, ReasonCode.LIMIT_EXCEEDED)
    reference(project_ref)
    store = DjangoPrivateStore(root=backups.private_root, crypto=crypto, environment=Environment.EVALUATION)
    journal = RecoveryJournal(root=backups.private_root, target_identity=backups.source_identity,
        code_version=backups.code_version, environment=backups.environment, domain=backups.domain,
        service_identity=backups.service_identity, clock=backups.clock, limits=limits)
    verifier = DjangoExecutorRecoveryVerifier(store=store, inspect_attempt=inspect_private_preparation,
        backup=backups, project_ref=project_ref, limits=limits, clock=backups.clock)
    return RecoveryFlow(backups=backups, journal=journal, verify_owners=verifier, clock=backups.clock)


def start_application():
    if not settings.CONTROLLED_EXPORT_PRIVATE_CONFIG:
        return
    from data_security.adapters.keys import FileKeyResolver
    from data_security.application.crypto_service import CryptoService

    path = Path(settings.CONTROLLED_EXPORT_PRIVATE_CONFIG)
    require(path.is_absolute() and path == path.resolve() and not path.stat().st_mode & 0o022
            and path.stat().st_size <= 65536, ReasonCode.AUTHORIZATION_DENIED)
    config = json.loads(path.read_bytes())
    require(type(config) is dict, ReasonCode.INVALID_TYPE)
    fields = {"schema_version", "environment", "key_manifest", "data_key", "private_root", "project_ref", "limits"}
    if config.get("schema_version") == "ds.executor-preparation.v2":
        fields |= {"retained_data_keys", "recovery_target_identity"}
    require(set(config) == fields, ReasonCode.UNKNOWN_FIELD)
    require(config["schema_version"] in ("ds.executor-preparation.v1", "ds.executor-preparation.v2")
            and config["environment"] == "evaluation"
            and settings.CONTROLLED_EXPORT_ENVIRONMENT == "evaluation", ReasonCode.SOURCE_NOT_APPROVED)
    require(settings.SECRET_KEY != "isolated-development-only" and settings.CONTROLLED_EXPORT_INTERNAL_KEY
            and settings.EXECUTION_AUTHORITY_HMAC_SECRET, ReasonCode.KEY_UNAVAILABLE)
    limits = Limits.from_wire(config["limits"])
    keys = FileKeyResolver(manifest_path=config["key_manifest"], environment=Environment.EVALUATION,
                          repository_root=Path(__file__).resolve().parents[3])
    key = KeyReference.from_wire(config["data_key"])
    require(key.purpose is KeyPurpose.DATA and key.status is KeyStatus.ACTIVE, ReasonCode.KEY_UNAVAILABLE)
    material = keys.resolve(key, KeyPurpose.DATA, "service/security")
    require(type(material) is SecretMaterial, ReasonCode.KEY_UNAVAILABLE)
    retained = config.get("retained_data_keys", [])
    require(type(retained) is list and len(retained) <= 64, ReasonCode.INVALID_VALUE)
    retained = tuple(KeyReference.from_wire(item) for item in retained)
    materials = {bytes(material.borrow(KeyPurpose.DATA))}
    for previous in retained:
        require(previous.purpose is KeyPurpose.DATA and previous.status is KeyStatus.READ_ONLY,
                ReasonCode.KEY_UNAVAILABLE)
        selected = keys.resolve(previous, KeyPurpose.DATA, "service/security")
        require(type(selected) is SecretMaterial, ReasonCode.KEY_UNAVAILABLE)
        value = bytes(selected.borrow(KeyPurpose.DATA))
        require(value not in materials, ReasonCode.KEY_UNAVAILABLE)
        materials.add(value)
    crypto = CryptoService(keys=keys, service_identity="service/security", random_bytes=secrets.token_bytes,
                           environment=Environment.EVALUATION, limits=limits, retained_data_keys=retained)
    settings.CONTROLLED_EXPORT_PRIVATE_PREPARATION = assemble_private_preparation(crypto=crypto, data_key=key,
        private_root=config["private_root"], project_ref=config["project_ref"], limits=limits)
    from data_security.adapters.django.recovery_ingress import bind_recovery_admission
    from data_security.adapters.persistence.recovery_state import recovery_admission
    target = config.get("recovery_target_identity")
    if target is not None:
        digest(target)
    bind_recovery_admission(partial(recovery_admission, config["private_root"], target, limits=limits)
                            if target is not None else None)


def private_upload_middleware(get_response):
    from data_security.adapters.django.private_ingress import ClosedPrivateUploadIngress, OpenPrivateUploadIngress
    from data_security.adapters.django.recovery_ingress import recovery_middleware

    components = settings.CONTROLLED_EXPORT_PRIVATE_PREPARATION
    if not settings.CONTROLLED_EXPORT_PRIVATE_MODE and components is None:
        return recovery_middleware(get_response)
    # Formal preparation never routes into legacy share/download/receipt operations.
    downstream = ClosedPrivateUploadIngress(get_response, paths=(), patterns=_LEGACY_DELIVERY_PATHS)
    if components is None or settings.CONTROLLED_EXPORT_ENVIRONMENT != "evaluation":
        return recovery_middleware(ClosedPrivateUploadIngress(downstream, paths=_UPLOAD_PATHS))

    def prepared_request(request):
        request._controlled_export_private_preparation = components
        return downstream(request)

    return recovery_middleware(OpenPrivateUploadIngress(prepared_request, paths=_UPLOAD_PATHS, limits=components["limits"]))


def guard_private_upload_asgi(application):
    from data_security.adapters.django.private_ingress import ClosedPrivateUploadIngress, OpenPrivateUploadIngress
    from data_security.adapters.django.recovery_ingress import guard_recovery_asgi

    components = settings.CONTROLLED_EXPORT_PRIVATE_PREPARATION
    if not settings.CONTROLLED_EXPORT_PRIVATE_MODE and components is None:
        return guard_recovery_asgi(application)
    downstream = ClosedPrivateUploadIngress(application, paths=(), patterns=_LEGACY_DELIVERY_PATHS).asgi
    if components is None or settings.CONTROLLED_EXPORT_ENVIRONMENT != "evaluation":
        downstream = ClosedPrivateUploadIngress(downstream, paths=_UPLOAD_PATHS).asgi
    else:
        downstream = OpenPrivateUploadIngress(downstream, paths=_UPLOAD_PATHS, limits=components["limits"]).asgi
    return guard_recovery_asgi(OpenPrivateUploadIngress(downstream, paths=(), patterns=(re.compile(
        r"/api/controlled-export/executions/[0-9a-f-]{36}/preparation/?"),),
        limits=replace(BASELINE_LIMITS, max_bytes=32768, max_text_chars=32768, max_inflight_objects=1)).asgi)
