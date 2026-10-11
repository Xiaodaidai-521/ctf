"""Decision persistence + execution preparation (regex spec H3-H6; R1/R3).

Production-decision layer (impure: DB, clock, uuid). Enforces: immutable
decisions, idempotency bound to a request/decision/obligations digest, the
authorization state machine, trusted-source admission, quota reservation and
approval gating. The pure judgment core is never bypassed here — this layer only
persists and prepares what the core already decided.
"""

import uuid
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from ..contracts import Disposition, ExecutionAuthorization, NotExecutable, Obligation
from ..contracts import reason_codes as rc
from ..models import ExecutionAuthorizationRecord, IdempotencyRecord, RiskDecision
from .admission import check_admission
from .serde import digest, obligations_to_json
from . import outbox

SUPPORTED_OBLIGATION_TYPES = {"mask", "approval"}


class IdempotencyConflict(Exception):
    """Same idempotency key reused with a different bound request/decision."""


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:16]}"


@transaction.atomic
def create_risk_decision(assessment, request, *, idempotency_key, valid_seconds=600):
    """Persist an immutable decision for ``assessment``; idempotent on key."""
    bound = digest("create", request.request_fingerprint,
                   assessment.recommended_action.value,
                   obligations_to_json(assessment.obligations), assessment.policy_version)

    existing = IdempotencyRecord.objects.filter(key=idempotency_key).first()
    if existing is not None:
        if existing.operation != "create_decision" or existing.bound_digest != bound:
            raise IdempotencyConflict(idempotency_key)
        return RiskDecision.objects.get(decision_id=existing.result_ref)

    decision_id = _uid("dec")
    decision = RiskDecision.objects.create(
        decision_id=decision_id, assessment_id=assessment.request_id,
        request_id=request.request_id, request_fingerprint=request.request_fingerprint,
        asset_version=request.asset_version, profile_id=assessment.profile_id,
        scope=list(request.scope), action=assessment.recommended_action.value,
        obligations=obligations_to_json(assessment.obligations),
        policy_version=assessment.policy_version, model_version=assessment.model_version,
        feature_set_version=assessment.feature_set_version,
        valid_until=timezone.now() + timedelta(seconds=valid_seconds), status="valid",
    )
    IdempotencyRecord.objects.create(
        key=idempotency_key, operation="create_decision",
        request_fingerprint=request.request_fingerprint, bound_digest=bound, result_ref=decision_id,
    )
    outbox.enqueue(_uid("evt"), "decision.issued",
                   {"decision_id": decision_id, "action": decision.action})
    return decision


def _recheck(auth, decision):
    """Re-validate current conditions on idempotent replay (review R1)."""
    if auth is None:
        return NotExecutable(Disposition.DENY, (rc.EXEC_DECISION_INVALID,))
    if decision.status != "valid":
        return NotExecutable(Disposition.DENY, (rc.EXEC_AUTHORIZATION_REVOKED,))
    if auth.state in ("revoked", "expired"):
        return NotExecutable(Disposition.DENY, (rc.EXEC_AUTHORIZATION_REVOKED,))
    if decision.valid_until and decision.valid_until < timezone.now():
        return NotExecutable(Disposition.DEFER, (rc.EXEC_DECISION_EXPIRED,))
    return None


def _to_authorization(auth, decision, request) -> ExecutionAuthorization:
    obligations = tuple(
        Obligation(
            obligation_id=o.get("obligation_id", ""), type=o.get("type", ""),
            parameters=o.get("parameters", {}), applicable_scope=o.get("applicable_scope", ""),
            enforcement_stage=o.get("enforcement_stage", ""),
            required_evidence=tuple(o.get("required_evidence", ())),
        )
        for o in (decision.obligations or [])
    )
    return ExecutionAuthorization(
        authorization_id=auth.authorization_id, execution_id=auth.execution_id,
        decision_id=decision.decision_id, request_fingerprint=decision.request_fingerprint,
        asset_version=decision.asset_version, profile_id=decision.profile_id,
        scope=tuple(decision.scope or ()), obligations=obligations,
        reservation_id=auth.reservation_id,
        valid_until=decision.valid_until.isoformat() if decision.valid_until else "",
    )


def prepare_execution(decision_id, request, authorization_snapshot, *, idempotency_key,
                      environment="production", approval=None, quota=None, quota_limit=0,
                      data_domain="", window_key=""):
    """Return NotExecutable or ExecutionAuthorization, re-checking live state."""
    with transaction.atomic():
        # Admission (review R3): synthetic/evaluation input cannot sign in production.
        reason = check_admission(environment, [request.source_mode, authorization_snapshot.source_mode])
        if reason:
            return NotExecutable(Disposition.DENY, (reason,))

        decision = RiskDecision.objects.select_for_update().filter(decision_id=decision_id).first()
        if decision is None or decision.status != "valid":
            return NotExecutable(Disposition.DENY, (rc.EXEC_DECISION_INVALID,))
        if decision.request_fingerprint != request.request_fingerprint:
            return NotExecutable(Disposition.DENY, (rc.EXEC_FINGERPRINT_MISMATCH,))
        if decision.valid_until and decision.valid_until < timezone.now():
            return NotExecutable(Disposition.DEFER, (rc.EXEC_DECISION_EXPIRED,))

        bound = digest("prepare", request.request_fingerprint, decision_id, decision.obligations)
        rec = IdempotencyRecord.objects.filter(key=idempotency_key).first()
        if rec is not None:
            if rec.operation != "prepare_execution" or rec.bound_digest != bound:
                raise IdempotencyConflict(idempotency_key)
            auth = ExecutionAuthorizationRecord.objects.filter(authorization_id=rec.result_ref).first()
            nx = _recheck(auth, decision)  # replay still re-checks (R1)
            return nx if nx is not None else _to_authorization(auth, decision, request)

        # Action gating.
        if decision.action == "deny":
            return NotExecutable(Disposition.DENY, (rc.EXEC_ACTION_DENY,))
        if decision.action == "defer":
            return NotExecutable(Disposition.DEFER, (rc.EXEC_ACTION_DEFER,))
        if decision.action == "require_approval":
            status = approval.status(decision_id, request.request_fingerprint) if approval else "none"
            if status != "approved":
                return NotExecutable(Disposition.REQUIRE_APPROVAL, (rc.EXEC_APPROVAL_REQUIRED,),
                                     approval_request_id=_uid("appr"))

        # Unsupported obligation -> never sign an authorization carrying it.
        for o in (decision.obligations or []):
            if o.get("type") not in SUPPORTED_OBLIGATION_TYPES:
                return NotExecutable(Disposition.REQUIRE_APPROVAL, (rc.EXEC_OBLIGATION_UNSUPPORTED,))

        # Quota reservation (optional). Over-limit -> defer, do not sign.
        reservation_id = ""
        if quota is not None:
            from export_quota.services import QuotaExceeded
            reservation_id = _uid("resv")
            try:
                quota.reserve(subject_id=request.subject_id, data_domain=data_domain or "default",
                              window_key=window_key or "default", amount=max(0, request.record_count),
                              request_fingerprint=request.request_fingerprint,
                              reservation_id=reservation_id, limit=quota_limit)
            except QuotaExceeded:
                return NotExecutable(Disposition.DEFER, (rc.EXEC_QUOTA_EXCEEDED,))

        auth = ExecutionAuthorizationRecord.objects.create(
            authorization_id=_uid("auth"), decision_id=decision_id,
            request_fingerprint=request.request_fingerprint, state="valid",
            execution_id=_uid("exec"), reservation_id=reservation_id, valid_until=decision.valid_until,
        )
        IdempotencyRecord.objects.create(
            key=idempotency_key, operation="prepare_execution",
            request_fingerprint=request.request_fingerprint, bound_digest=bound,
            result_ref=auth.authorization_id,
        )
        outbox.enqueue(_uid("evt"), "execution.authorized",
                       {"authorization_id": auth.authorization_id, "decision_id": decision_id})
        return _to_authorization(auth, decision, request)


@transaction.atomic
def claim(authorization_id: str) -> bool:
    """Atomically move valid -> claiming. Returns False if already taken.

    True single-claim guarantee needs a real DB row lock (PostgreSQL); on SQLite
    the select_for_update is a no-op, so concurrency is asserted only under PG.
    """
    auth = ExecutionAuthorizationRecord.objects.select_for_update().get(authorization_id=authorization_id)
    if auth.state != "valid":
        return False
    auth.state = "claiming"
    auth.save(update_fields=["state"])
    return True


@transaction.atomic
def consume(authorization_id: str, execution_result: str = "") -> bool:
    """Move claiming -> consumed (terminal)."""
    auth = ExecutionAuthorizationRecord.objects.select_for_update().get(authorization_id=authorization_id)
    if auth.state != "claiming":
        return False
    auth.state = "consumed"
    auth.consumed_at = timezone.now()
    auth.save(update_fields=["state", "consumed_at"])
    return True


@transaction.atomic
def revoke_authorization(authorization_id: str) -> None:
    ExecutionAuthorizationRecord.objects.filter(authorization_id=authorization_id).update(state="revoked")


@transaction.atomic
def invalidate_decision(decision_id: str, *, superseded_by: str = "") -> None:
    """Invalidate a decision without overwriting history (a new row supersedes)."""
    status = "superseded" if superseded_by else "invalidated"
    RiskDecision.objects.filter(decision_id=decision_id).update(status=status)



