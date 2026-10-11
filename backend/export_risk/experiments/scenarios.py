"""Synthetic scenarios for the four-arm comparison (regex spec I2).

Each step carries the request plus the inputs known **at that step's virtual
time** (profile, authorization, newly-observed behaviour events). Labels mostly
validate policy conformance, not discovery of unknown malice (disclosed per I2).
All data here is synthetic and non-production.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Sequence

from ..contracts import AuthorizationResult, AuthorizationSnapshot, ExportRequestSnapshot
from ..contracts import SensitivityProfileRef, SourceMode, QualityState
from ..baselines import Observation
from ..features import EventRecord

T0 = datetime(2026, 10, 11, 0, 0, 0, tzinfo=timezone.utc)


@dataclass(frozen=True)
class Step:
    as_of: datetime
    request: ExportRequestSnapshot
    profile: SensitivityProfileRef
    authorization: AuthorizationSnapshot
    new_events: Sequence[EventRecord] = field(default_factory=tuple)
    label: str = "normal"           # normal | violation | needs_review | insufficient
    expect_restrict: bool = False


@dataclass(frozen=True)
class Scenario:
    name: str
    subject_id: str
    cohort_key: str
    steps: Sequence[Step]
    baseline_observations: Sequence[Observation] = field(default_factory=tuple)
    description: str = ""


def _auth(result=AuthorizationResult.AUTHORIZED, recipients=("rc1",), scope=("o1",)):
    return AuthorizationSnapshot(
        authority_source="src", snapshot_id="s", subject_id="u1", data_domain="d1",
        result=result, allowed_recipients=recipients, allowed_operations=("export",),
        allowed_scope=scope, environment="test", source_mode=SourceMode.SYNTHETIC,
    )


def _profile(level="medium", categories=()):
    return SensitivityProfileRef(profile_id="p1", asset_version="v1", protection_level=level,
                                 categories=categories, coverage=QualityState.OK, status="complete",
                                 source_mode=SourceMode.SYNTHETIC)


def _req(i, records=10, scope=("o1",), recipient="rc1"):
    return ExportRequestSnapshot(
        request_id=f"r{i}", revision="1", subject_id="u1", asset_version="v1", scope=scope,
        operation="export", recipient_id=recipient, record_count=records,
        request_fingerprint=f"fp{i}", environment="test", source_mode=SourceMode.SYNTHETIC,
    )


def _ev(i, at, objects=("o1",)):
    return EventRecord(event_id=f"e{i}", event_type="export_request", occurred_at=at,
                       received_at=at, recipient_id="rc1", object_scope=objects)


def _baseline_obs(n=30, values=(2.0, 3.0, 4.0)):
    # A quiet prior history with mild spread (median 3, IQR 1) so robust
    # deviation is well-defined (a zero-IQR baseline cannot rank anything).
    return tuple(Observation("u1", "cohortA", T0 - timedelta(days=d + 1),
                             {"req_count_long": values[d % len(values)]})
                 for d in range(n))


def normal_bulk() -> Scenario:
    steps = []
    for i in range(3):
        at = T0 + timedelta(minutes=10 * (i + 1))
        steps.append(Step(as_of=at, request=_req(i, records=800), profile=_profile(),
                          authorization=_auth(), new_events=(_ev(i, at),),
                          label="normal", expect_restrict=False))
    return Scenario("normal_bulk", "u1", "cohortA", tuple(steps), _baseline_obs(),
                    "Authorized moderate bulk; should not be restricted.")


def continuous_batch(n=60) -> Scenario:
    steps = []
    for i in range(n):
        at = T0 + timedelta(minutes=5 * (i + 1))
        obj = (f"o{i}",)  # a new object each time -> scope accumulates
        allowed_scope = tuple(f"o{j}" for j in range(n))  # all authorized individually
        steps.append(Step(
            as_of=at, request=_req(i, records=10, scope=obj),
            profile=_profile(), authorization=_auth(scope=allowed_scope),
            new_events=(_ev(i, at, objects=obj),),
            label="needs_review" if i >= 40 else "normal",
            expect_restrict=i >= 40,
        ))
    return Scenario("continuous_batch", "u1", "cohortA", tuple(steps), _baseline_obs(),
                    "Many small authorized requests; cumulative volume/scope grows.")


def unapproved_recipient() -> Scenario:
    at = T0 + timedelta(minutes=10)
    step = Step(as_of=at, request=_req(0, records=10, recipient="outsider"),
                profile=_profile(), authorization=_auth(recipients=("rc1",)),
                new_events=(_ev(0, at),), label="violation", expect_restrict=True)
    return Scenario("unapproved_recipient", "u1", "cohortA", (step,), _baseline_obs(),
                    "Recipient outside the authorized set -> hard deny in every arm.")


def new_account() -> Scenario:
    at = T0 + timedelta(minutes=10)
    step = Step(as_of=at, request=_req(0, records=50), profile=_profile(),
                authorization=_auth(), new_events=(_ev(0, at),),
                label="insufficient", expect_restrict=False)
    return Scenario("new_account", "u1", "cohortA", (step,), tuple(),  # no baseline history
                    "No personal history; cold-start fallback, not treated as normal.")


def all_scenarios() -> List[Scenario]:
    return [normal_bulk(), continuous_batch(), unapproved_recipient(), new_account()]
