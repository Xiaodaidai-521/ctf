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


def _recheck_record(auth, decision, now, deadline):
    """Shared stored-state/hold validation for replay and claim, inside locks.

    ``deadline`` is the caller's full execution deadline (decision, and for
    replay the current grant). The authorization is tightened once to the
    earliest of that deadline and any live reservation expiry; expired holds are
    rejected, never released, so an unknown delivery keeps its capacity.
    """
    if auth is None or decision is None:
        return NotExecutable(Disposition.DENY, (rc.EXEC_DECISION_INVALID,))
    if decision.status != "valid" or auth.state != "valid":
        return NotExecutable(Disposition.DENY, (rc.EXEC_AUTHORIZATION_REVOKED,))
    if (auth.decision_id != decision.decision_id
            or auth.request_fingerprint != decision.request_fingerprint):
        return NotExecutable(Disposition.DENY, (rc.EXEC_FINGERPRINT_MISMATCH,))
    if not _unexpired(auth.valid_until, now) or not _unexpired(deadline, now):
        return NotExecutable(Disposition.DEFER, (rc.EXEC_DECISION_EXPIRED,))
    _tighten_expiry(auth, deadline)
    if auth.reservation_id:
        from export_quota.services import QuotaError, QuotaService
        try:
            reservation = QuotaService.require_active(
                reservation_id=auth.reservation_id, request_fingerprint=auth.request_fingerprint,
            )
        except QuotaError:
            return NotExecutable(Disposition.DEFER, (rc.EXEC_RESERVATION_INVALID,))
        _tighten_expiry(auth, reservation.expires_at)
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


def prepare_execution(decision_id, request, authorization_snapshot, *, idempotency_key,
                      environment="production", approval=None, quota=None, quota_limit=0,
                      data_domain="", window_key=""):
    """Return NotExecutable or a currently valid, deadline-bounded authorization."""
    with transaction.atomic():
        reason = check_admission(environment, [request.source_mode, authorization_snapshot.source_mode])
        if reason:
            return NotExecutable(Disposition.DENY, (reason,))
        decision = RiskDecision.objects.select_for_update().filter(decision_id=decision_id).first()
        now = timezone.now()
        if decision is None or decision.status != "valid":
            return NotExecutable(Disposition.DENY, (rc.EXEC_DECISION_INVALID,))
        if decision.request_fingerprint != request.request_fingerprint:
            return NotExecutable(Disposition.DENY, (rc.EXEC_FINGERPRINT_MISMATCH,))
        if not _unexpired(decision.valid_until, now):
            return NotExecutable(Disposition.DEFER, (rc.EXEC_DECISION_EXPIRED,))
        # One environment gate: request, snapshot, decision and caller must agree.
        if len({request.environment, authorization_snapshot.environment,
                decision.environment, environment}) != 1:
            return NotExecutable(Disposition.DEFER, (rc.CONSISTENCY_ENVIRONMENT_MISMATCH,))
        if environment == "production" and (
            decision.source_mode != SourceMode.PRODUCTION.value or decision.environment != "production"
        ):
            return NotExecutable(Disposition.DENY, (rc.EXEC_DECISION_SOURCE_UNTRUSTED,))
        blocker = _authorization_blocker(request, authorization_snapshot, now)
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

        # Upstream grant and decision both bound the execution, not just preparation.
        expiry = min(decision.valid_until, parse_aware_timestamp(authorization_snapshot.valid_until))
        bound = digest("prepare", request.request_fingerprint, decision_id, decision.obligations)
        rec = IdempotencyRecord.objects.filter(key=idempotency_key).first()
        if rec is not None:
            if rec.operation != "prepare_execution" or rec.bound_digest != bound:
                raise IdempotencyConflict(idempotency_key)
            auth = ExecutionAuthorizationRecord.objects.select_for_update().filter(
                authorization_id=rec.result_ref,
            ).first()
            # Re-check stored state and tighten to the current full deadline; a
            # newer grant can only shorten, never revive, the existing hold.
            blocker = _recheck_record(auth, decision, timezone.now(), expiry)
            if blocker is not None:
                return blocker
            return _to_authorization(auth, decision)

        reservation_id = ""
        if quota is not None:
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
            if reservation_id:
                quota.release(reservation_id=reservation_id)  # don't commit a leaked hold
            return NotExecutable(Disposition.DEFER, (rc.EXEC_AUTHORIZATION_EXPIRED,))

        auth = ExecutionAuthorizationRecord.objects.create(
            authorization_id=_uid("auth"), decision_id=decision_id,
            request_fingerprint=request.request_fingerprint, state="valid",
            execution_id=_uid("exec"), reservation_id=reservation_id, valid_until=expiry,
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
def claim(authorization_id: str) -> bool:
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
    blocker = _recheck_record(auth, decision, timezone.now(), deadline)
    if blocker is not None:
        if auth.state == "valid" and rc.EXEC_DECISION_EXPIRED in blocker.reason_codes:
            auth.state = "expired"
            auth.save(update_fields=["state"])
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
    """Invalidate a decision without overwriting its historical bindings."""
    status = "superseded" if superseded_by else "invalidated"
    RiskDecision.objects.filter(decision_id=decision_id).update(status=status)
