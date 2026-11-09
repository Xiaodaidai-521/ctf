"""Interpret one explicit approved snapshot; never fetch a policy or authority."""
from data_security.contracts import (Algorithm, Category, Finding, LocationKind,
    PolicyBinding, PolicySnapshot, PolicyStatus, ProtectionContext, ReasonCode, ResolvedAction)
from data_security.contracts.schema import content_hash, reference, require, utc


def validate_snapshot(snapshot, binding, *, at):
    require(type(snapshot) is PolicySnapshot and type(binding) is PolicyBinding, ReasonCode.INVALID_TYPE)
    utc(at)
    require(snapshot.status is PolicyStatus.APPROVED and snapshot.approval is not None,
            ReasonCode.POLICY_NOT_APPROVED)
    require(snapshot.content_hash == content_hash(snapshot.content()) == snapshot.approval.content_hash,
            ReasonCode.HASH_MISMATCH)
    require((snapshot.version, snapshot.content_hash) == (binding.protection_version, binding.protection_hash),
            ReasonCode.POLICY_NOT_APPROVED)
    require(snapshot.approval.approved_at <= snapshot.effective_at <= at < snapshot.expires_at,
            ReasonCode.AUTHORIZATION_EXPIRED)
    return snapshot


def resolve_actions(snapshot, context, findings, binding, *, at, field_ref):
    validate_snapshot(snapshot, binding, at=at)
    require(type(context) is ProtectionContext, ReasonCode.AUTHORIZATION_DENIED)
    reference(field_ref)
    # Upstream authorization must project this field into the explicit scope.
    require(field_ref in context.scope_refs, ReasonCode.AUTHORIZATION_DENIED)
    require(type(findings) is tuple and len(findings) <= 10000 and all(type(f) is Finding for f in findings),
            ReasonCode.LIMIT_EXCEEDED)
    rules = {(r.category, r.outlet, r.role, r.purpose): r.action for r in snapshot.rules}
    actions = []
    for index, finding in enumerate(findings):
        location = finding.location
        # Only an explicitly projected text field may use an exception. v1 has
        # no approved JSON-path or table-column mapping to a field reference.
        exempt = finding.category is Category.IPV4 and location.kind is LocationKind.TEXT_SPAN and any(
            (e.source_ref, e.source_version, e.source_hash) ==
            (context.source_ref, context.source_version, context.source_hash) and
            e.outlet is context.outlet and e.purpose is context.purpose and field_ref in e.field_refs and
            e.approval.approved_at <= at < e.expires_at for e in snapshot.teaching_exceptions)
        if exempt:
            continue
        action = rules.get((finding.category, context.outlet, context.role, context.purpose))
        require(action is not None, ReasonCode.POLICY_NOT_APPROVED)
        action.validate_category(finding.category)
        if location.kind is LocationKind.CELL:
            require(action.algorithm in (Algorithm.DROP, Algorithm.REPLACE), ReasonCode.INVALID_COORDINATE)
        actions.append(ResolvedAction(schema_version=ResolvedAction.SCHEMA, action_id=f'action/{index}',
            source_operation_ref=f'finding/{index}', location=location, category=finding.category,
            algorithm=action, finding_refs=(f'finding/{index}',), requirement_refs=()))
    return tuple(actions)
