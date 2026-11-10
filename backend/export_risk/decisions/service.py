"""Decision persistence and execution preparation (H3-H6; R1/R3).

Impure layer: DB, clock, uuid. Current permission/approval checks precede both
first issue and replay. Execution eligibility is shared by replay and claim;
locks follow decision -> authorization -> quota bucket -> reservation.
"""

import uuid
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from ..contracts import (
    AuthorizationResult, Disposition, ExecutionAuthorization, NotExecutable,
    Obligation, SourceMode,
)
from ..contracts import reason_codes as rc
from ..judgment.hard_constraints import evaluate_hard_constraints
from ..judgment.validity import authorization_validity, parse_aware_timestamp
from ..models import ExecutionAuthorizationRecord, IdempotencyRecord, RiskDecision
from .admission import check_admission
from .serde import digest, obligations_to_json
from . import outbox

SUPPORTED_OBLIGATION_TYPES = {"mask", "approval"}


class IdempotencyConflict(Exception):
    """Same idempotency key reused with a different bound request/decision."""


class AssessmentBindingError(ValueError):
    """The assessment does not belong to the request it is being persisted for."""


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:16]}"


@transaction.atomic
def create_risk_decision(assessment, request, *, idempotency_key, valid_seconds=600):
    """Persist an immutable assessment bound to this request; idempotent on key."""
    if (assessment.request_id != request.request_id
            or assessment.request_fingerprint != request.request_fingerprint):
        raise AssessmentBindingError(
            f"assessment {assessment.request_id!r}/{assessment.request_fingerprint!r} "
            f"does not match request {request.request_id!r}/{request.request_fingerprint!r}"
        )
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
        environment=request.environment, source_mode=assessment.input_source_mode.value,
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


def _authorization_blocker(request, snapshot, now):
    """Check the fresh grant's complete envelope on first preparation and replay.

    A request fingerprint cannot prove that live permission allow-lists are
    unchanged. Reuse the pure hard constraints and aware-time validator. The
    caller establishes request/snapshot/decision/environment agreement.
    """
    if snapshot.result == AuthorizationResult.FORBIDDEN:
        return NotExecutable(Disposition.DENY, (rc.EXEC_AUTHORIZATION_FORBIDDEN,))
    if snapshot.subject_id != request.subject_id:
        return NotExecutable(Disposition.DENY, (rc.EXEC_AUTHORIZATION_SUBJECT_MISMATCH,))
    if snapshot.result != AuthorizationResult.AUTHORIZED:
        return NotExecutable(Disposition.DEFER, (rc.EXEC_AUTHORIZATION_UNKNOWN,))
    hard = evaluate_hard_constraints(request, snapshot)
    if hard.triggered:
        return NotExecutable(Disposition.DENY, hard.reason_codes)
    validity_code = authorization_validity(snapshot, now.isoformat())
    if validity_code is not None:
        code = (rc.EXEC_AUTHORIZATION_EXPIRED
                if validity_code == rc.DEGRADE_AUTHORIZATION_EXPIRED
                else rc.EXEC_AUTHORIZATION_VALIDITY_UNKNOWN)
        return NotExecutable(Disposition.DEFER, (code,))
    return None


def _approval_blocker(decision, request, approval, environment):
    """Check current approval status and authority on first preparation and replay."""
    status = approval.status(decision.decision_id, request.request_fingerprint) if approval else "none"
    if status != "approved":
        return NotExecutable(Disposition.REQUIRE_APPROVAL, (rc.EXEC_APPROVAL_REQUIRED,),
                             approval_request_id=_uid("appr"))
    if environment == "production" and not getattr(approval, "is_production_authority", False):
        return NotExecutable(Disposition.DENY, (rc.EXEC_APPROVAL_AUTHORITY_UNTRUSTED,))
    return None


def _unexpired(expiry, now):
    """Unknown or timezone-free deadlines never mean valid forever."""
    return expiry is not None and expiry.utcoffset() is not None and now < expiry


def _tighten_expiry(auth, expiry):
    """A locked valid authorization may be shortened, never extended on replay."""
    if auth.valid_until is not None and expiry < auth.valid_until:
        auth.valid_until = expiry
        auth.save(update_fields=["valid_until"])


def _legacy_require_active(*, reservation_id, request_fingerprint, amount=None):
    """Compatibility for callers not yet using the delivery flow's injected port."""
    from export_quota.services import QuotaError, QuotaService
    try:
        return QuotaService.require_active(
            reservation_id=reservation_id, request_fingerprint=request_fingerprint,
            amount=amount,
        ).expires_at
    except QuotaError:
        return None


def _recheck_record(auth, decision, now, deadline, *, require_active, state="valid"):
    """Shared stored-state/hold validation for replay and claim, inside locks.

    ``deadline`` is the caller's full execution deadline (decision, and for
    replay the current grant). The authorization is tightened once to the
    earliest of that deadline and any live reservation expiry; expired holds are
    rejected, never released, so an unknown delivery keeps its capacity.
    """
    if auth is None or decision is None:
        return NotExecutable(Disposition.DENY, (rc.EXEC_DECISION_INVALID,))
    if decision.status != "valid" or auth.state != state:
        return NotExecutable(Disposition.DENY, (rc.EXEC_AUTHORIZATION_REVOKED,))
    if (auth.decision_id != decision.decision_id
            or auth.request_fingerprint != decision.request_fingerprint):
        return NotExecutable(Disposition.DENY, (rc.EXEC_FINGERPRINT_MISMATCH,))
    if not _unexpired(auth.valid_until, now) or not _unexpired(deadline, now):
        return NotExecutable(Disposition.DEFER, (rc.EXEC_DECISION_EXPIRED,))
    _tighten_expiry(auth, deadline)
    if auth.reservation_id:
        reservation_expiry = require_active(
            reservation_id=auth.reservation_id, request_fingerprint=auth.request_fingerprint,
        )
        if not _unexpired(reservation_expiry, timezone.now()):
            return NotExecutable(Disposition.DEFER, (rc.EXEC_RESERVATION_INVALID,))
        _tighten_expiry(auth, reservation_expiry)
    # Re-read the clock after lock waits; the earlier instant cannot extend validity.
    if not _unexpired(auth.valid_until, timezone.now()):
        return NotExecutable(Disposition.DEFER, (rc.EXEC_DECISION_EXPIRED,))
    return None


def _to_authorization(auth, decision) -> ExecutionAuthorization:
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
        valid_until=auth.valid_until.isoformat() if auth.valid_until else "",
    )


def _execution_blocker(decision, request, snapshot, now, *, environment, approval):
    """Shared live eligibility checks for issuing and pre-delivery rechecking."""
    reason = check_admission(environment, [request.source_mode, snapshot.source_mode])
    if reason:
        return NotExecutable(Disposition.DENY, (reason,))
    if decision is None or decision.status != "valid":
        return NotExecutable(Disposition.DENY, (rc.EXEC_DECISION_INVALID,))
    if decision.request_fingerprint != request.request_fingerprint:
        return NotExecutable(Disposition.DENY, (rc.EXEC_FINGERPRINT_MISMATCH,))
    if not _unexpired(decision.valid_until, now):
        return NotExecutable(Disposition.DEFER, (rc.EXEC_DECISION_EXPIRED,))
    if len({request.environment, snapshot.environment, decision.environment, environment}) != 1:
        return NotExecutable(Disposition.DEFER, (rc.CONSISTENCY_ENVIRONMENT_MISMATCH,))
    if environment == "production" and decision.source_mode != SourceMode.PRODUCTION.value:
        return NotExecutable(Disposition.DENY, (rc.EXEC_DECISION_SOURCE_UNTRUSTED,))
    blocker = _authorization_blocker(request, snapshot, now)
    if blocker is not None:
        return blocker
    if decision.action == "deny":
        return NotExecutable(Disposition.DENY, (rc.EXEC_ACTION_DENY,))
    if decision.action == "defer":
        return NotExecutable(Disposition.DEFER, (rc.EXEC_ACTION_DEFER,))
    if decision.action == "require_approval":
        blocker = _approval_blocker(decision, request, approval, environment)
        if blocker is not None:
            return blocker
    for ob in (decision.obligations or []):
        if ob.get("type") not in SUPPORTED_OBLIGATION_TYPES:
            return NotExecutable(Disposition.REQUIRE_APPROVAL, (rc.EXEC_OBLIGATION_UNSUPPORTED,))
    return None


def check_execution_eligibility(decision_id, request, authorization_snapshot, *,
                                environment="production", approval=None):
    """Pre-reservation eligibility only: no hold, authorization, claim or quota write.

    Preparation and delivery still recheck; this result is not an execution grant.
    """
    with transaction.atomic():
        decision = RiskDecision.objects.select_for_update().filter(decision_id=decision_id).first()
        return _execution_blocker(decision, request, authorization_snapshot, timezone.now(),
                                  environment=environment, approval=approval)


def prepare_execution(decision_id, request, authorization_snapshot, *, idempotency_key,
                      environment="production", approval=None, quota=None, quota_limit=0,
                      data_domain="", window_key="", reservation_id="",
                      authorization_id=None, execution_id=None,
                      require_active=_legacy_require_active, execution_binding_hash=None):
    """Prepare using either the legacy quota path or an already reserved flow hold.

    The flow supplies all three identities and require_active; this path never
    reserves or releases quota. Its adapter also binds the complete execution
    hash for read-only delivered rechecks. Legacy callers keep their old digest.
    """
    external_hold = bool(reservation_id)
    if external_hold and (quota is not None or authorization_id is None or execution_id is None
                          or require_active is _legacy_require_active):
        raise ValueError("external hold requires explicit identities and require_active, without quota")
    if not external_hold and (authorization_id is not None or execution_id is not None):
        raise ValueError("explicit identities require an external hold")
    with transaction.atomic():
        decision = RiskDecision.objects.select_for_update().filter(decision_id=decision_id).first()
        blocker = _execution_blocker(decision, request, authorization_snapshot, timezone.now(),
                                     environment=environment, approval=approval)
        if blocker is not None:
            return blocker

        # Upstream grant and decision both bound the execution, not just preparation.
        expiry = min(decision.valid_until, parse_aware_timestamp(authorization_snapshot.valid_until))
        bound = digest("prepare", request.request_fingerprint, decision_id, decision.obligations)
        if external_hold:
            bound = digest(bound, reservation_id, authorization_id, execution_id)
        if execution_binding_hash is not None:
            bound = digest(bound, execution_binding_hash)
        rec = IdempotencyRecord.objects.filter(key=idempotency_key).first()
        if rec is not None:
            if rec.operation != "prepare_execution" or rec.bound_digest != bound:
                raise IdempotencyConflict(idempotency_key)
            auth = ExecutionAuthorizationRecord.objects.select_for_update().filter(
                authorization_id=rec.result_ref,
            ).first()
            # Re-check stored state and tighten to the current full deadline; a
            # newer grant can only shorten, never revive, the existing hold.
            blocker = _recheck_record(auth, decision, timezone.now(), expiry,
                                      require_active=require_active)
            if blocker is not None:
                return blocker
            return _to_authorization(auth, decision)

        if external_hold:
            reservation_expiry = require_active(
                reservation_id=reservation_id, request_fingerprint=request.request_fingerprint,
                amount=request.record_count,
            )
            if not _unexpired(reservation_expiry, timezone.now()):
                return NotExecutable(Disposition.DEFER, (rc.EXEC_RESERVATION_INVALID,))
            expiry = min(expiry, reservation_expiry)
        elif quota is not None:
            from export_quota.services import QuotaError, QuotaExceeded
            reservation_id = _uid("resv")
            try:
                reservation = quota.reserve(
                    subject_id=request.subject_id, data_domain=data_domain or "default",
                    window_key=window_key or "default", amount=max(0, request.record_count),
                    request_fingerprint=request.request_fingerprint,
                    reservation_id=reservation_id, limit=quota_limit,
                )
            except QuotaExceeded:
                return NotExecutable(Disposition.DEFER, (rc.EXEC_QUOTA_EXCEEDED,))
            except QuotaError:
                return NotExecutable(Disposition.DEFER, (rc.EXEC_RESERVATION_INVALID,))
            reservation_expiry = getattr(reservation, "expires_at", None)
            if not _unexpired(reservation_expiry, timezone.now()):
                quota.release(reservation_id=reservation_id)  # don't commit a leaked hold
                return NotExecutable(Disposition.DEFER, (rc.EXEC_RESERVATION_INVALID,))
            expiry = min(expiry, reservation_expiry)
        if not _unexpired(expiry, timezone.now()):
            if reservation_id and not external_hold:
                quota.release(reservation_id=reservation_id)  # legacy-owned hold only
            return NotExecutable(Disposition.DEFER, (rc.EXEC_AUTHORIZATION_EXPIRED,))

        auth = ExecutionAuthorizationRecord.objects.create(
            authorization_id=authorization_id or _uid("auth"), decision_id=decision_id,
            request_fingerprint=request.request_fingerprint, state="valid",
            execution_id=execution_id or _uid("exec"), reservation_id=reservation_id, valid_until=expiry,
        )
        IdempotencyRecord.objects.create(
            key=idempotency_key, operation="prepare_execution",
            request_fingerprint=request.request_fingerprint, bound_digest=bound,
            result_ref=auth.authorization_id,
        )
        outbox.enqueue(_uid("evt"), "execution.authorized",
                       {"authorization_id": auth.authorization_id, "decision_id": decision_id})
        return _to_authorization(auth, decision)


@transaction.atomic
def claim(authorization_id: str, *, require_active=_legacy_require_active) -> bool:
    """Claim once if decision, authorization and quota hold are still valid.

    Lock decision before authorization, matching preparation. SQLite cannot
    establish the PostgreSQL single-winner/competing-transition guarantee.
    """
    original = ExecutionAuthorizationRecord.objects.filter(authorization_id=authorization_id).first()
    if original is None:
        return False
    decision = RiskDecision.objects.select_for_update().filter(decision_id=original.decision_id).first()
    auth = ExecutionAuthorizationRecord.objects.select_for_update().get(pk=original.pk)
    deadline = decision.valid_until if decision is not None else None
    blocker = _recheck_record(auth, decision, timezone.now(), deadline,
                              require_active=require_active)
    if blocker is not None:
        if auth.state == "valid" and rc.EXEC_DECISION_EXPIRED in blocker.reason_codes:
            auth.state = "expired"
            auth.save(update_fields=["state"])
        return False
    auth.state = "claiming"
    auth.save(update_fields=["state"])
    return True


@transaction.atomic
def recheck_execution(authorization_id, request, authorization_snapshot, *, decision_id,
                      execution_id, reservation_id, require_active, environment="production",
                      approval=None):
    """Recheck a claimed flow execution before logical delivery; never settle a hold.

    The caller's short UoW retains these locks until delivery/audit commit. Fresh
    grants are supplied by the trusted assembly, not by the download client.
    """
    decision = RiskDecision.objects.select_for_update().filter(decision_id=decision_id).first()
    auth = ExecutionAuthorizationRecord.objects.select_for_update().filter(
        authorization_id=authorization_id,
    ).first()
    if (auth is None or auth.decision_id != decision_id or auth.execution_id != execution_id
            or not reservation_id or auth.reservation_id != reservation_id):
        return NotExecutable(Disposition.DENY, (rc.EXEC_FINGERPRINT_MISMATCH,))
    blocker = _execution_blocker(decision, request, authorization_snapshot, timezone.now(),
                                 environment=environment, approval=approval)
    if blocker is not None:
        return blocker
    deadline = min(decision.valid_until, parse_aware_timestamp(authorization_snapshot.valid_until))
    blocker = _recheck_record(auth, decision, timezone.now(), deadline,
                              require_active=require_active, state="claiming")
    if blocker is not None:
        return blocker
    return _to_authorization(auth, decision)


@transaction.atomic
def recheck_delivered(authorization_id, request, authorization_snapshot, *, decision_id,
                      execution_id, reservation_id, decision_key, idempotency_key,
                      execution_binding_hash, expires_at, environment="production", approval=None):
    """Lock and read the consumed authorization; never claim, tighten or read a hold.

    Lock decision before authorization, retaining both until the caller's outer
    UoW ends (or this short transaction ends for a standalone call). Both owner
    idempotency records must identify this exact request/execution. Recheck state
    and deadlines after lock waits, without renewing the authorization.
    """
    decision = RiskDecision.objects.select_for_update().filter(decision_id=decision_id).first()
    auth = ExecutionAuthorizationRecord.objects.select_for_update().filter(
        authorization_id=authorization_id,
    ).first()
    admission = IdempotencyRecord.objects.filter(key=decision_key).first()
    issued = IdempotencyRecord.objects.filter(key=idempotency_key).first()
    if decision is None or auth is None or admission is None or issued is None:
        return NotExecutable(Disposition.DENY, (rc.EXEC_DECISION_INVALID,))
    if (admission.operation != "create_decision" or admission.result_ref != decision_id
            or admission.request_fingerprint != request.request_fingerprint
            or auth.decision_id != decision_id or auth.execution_id != execution_id
            or auth.reservation_id != reservation_id
            or auth.request_fingerprint != request.request_fingerprint):
        return NotExecutable(Disposition.DENY, (rc.EXEC_FINGERPRINT_MISMATCH,))
    bound = digest("prepare", request.request_fingerprint, decision_id, decision.obligations)
    bound = digest(bound, reservation_id, authorization_id, execution_id)
    bound = digest(bound, execution_binding_hash)
    if (issued.operation != "prepare_execution" or issued.result_ref != authorization_id
            or issued.request_fingerprint != request.request_fingerprint or issued.bound_digest != bound):
        raise IdempotencyConflict(idempotency_key)
    if auth.state != "consumed":
        return NotExecutable(Disposition.DENY, (rc.EXEC_AUTHORIZATION_REVOKED,))
    blocker = _execution_blocker(decision, request, authorization_snapshot, timezone.now(),
                                 environment=environment, approval=approval)
    if blocker is not None:
        return blocker
    # Approval/permission reads may take time. Retest every deadline at return,
    # including the original authorization deadline, which may predate binding expiry.
    now = timezone.now()
    deadline = min(decision.valid_until, parse_aware_timestamp(authorization_snapshot.valid_until), expires_at)
    if not _unexpired(auth.valid_until, now) or not _unexpired(deadline, now):
        return NotExecutable(Disposition.DEFER, (rc.EXEC_DECISION_EXPIRED,))
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
    """Invalidate a decision without overwriting its historical bindings."""
    status = "superseded" if superseded_by else "invalidated"
    RiskDecision.objects.filter(decision_id=decision_id).update(status=status)
