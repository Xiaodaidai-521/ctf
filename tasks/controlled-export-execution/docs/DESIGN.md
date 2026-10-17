# Design and evidence record

## Repository observations

| Observation | Evidence | Status | What it does not prove |
| --- | --- | --- | --- |
| Parent application uses Django/DRF and supports PostgreSQL with a SQLite development option | `backend/ctf_backend/settings.py`, `backend/requirements.txt` | Verified code fact | Production database configuration or availability |
| Upstream has separate `NotExecutable` and `ExecutionAuthorization` contracts | `backend/export_risk/contracts/execution.py`, `backend/export_risk/decisions/service.py` | Verified code fact | That this isolated service is already integrated with it |
| Upstream persists execution authorization and an event outbox | `backend/export_risk/models.py` | Verified code fact | Cross-service delivery or exactly-once publication |
| Quota code uses shared-bucket locks and distinguishes unknown reservations | `backend/export_quota/services.py` | Verified code fact | This service settles a real quota reservation |
| Existing resource download requires authentication but increments count before response transmission completes | `backend/resources/views.py` | Verified code fact | Existing resource download is controlled delivery |
| Parent media settings define `/media/`; this service exposes no media/static route | `backend/ctf_backend/settings.py`, `controlled_export_service/urls.py` | Verified code fact | Deployment proxy configuration remains private |
| Audit has a database-backed hash-chain append service | `backend/audit/services.py` | Verified code fact | This service's outbox is consumed by that audit service |

## Ownership and contracts

- Risk and approval decisions remain upstream. This service accepts only a signed, bounded authorization; it does not infer an `allow` decision.
- Redaction category selection and plan generation remain upstream. This service validates and executes only approved plan operations.
- Quota reservation and settlement remain upstream. `reservation_id` is retained as a reference; no local quota ledger is invented.
- This service owns actual execution attempts, protected artifact registration, share grants, delivery attempts, and its factual outbox events.
- Audit consumers own durable downstream event ingestion and deduplication by `event_id`.

## State and transaction model

```text
ExportExecution: queued -> running -> succeeded | failed | cancelled | repair_required
ExecutionAttempt: running -> succeeded | failed | cancelled | stale
DeliveryAttempt: not_started -> started -> unknown -> completed | failed
ShareGrant: active -> revoked (expiry is evaluated at admission, not by a clock-dependent index)
```

1. A short transaction validates idempotency, consumes the unique authorization, locks the execution, increments `fencing_token`, and creates an attempt.
2. Transformation and private candidate writing happen outside database locks.
3. A short transaction confirms active attempt plus fencing token and records the candidate reference.
4. The candidate is atomically renamed within the configured local private filesystem.
5. A short transaction rechecks the fence, registers the immutable artifact, completes the attempt/execution, and records an outbox event.

This does not make the database and filesystem atomically consistent. A crash between steps 4 and 5 can leave an orphan; reconciliation detects and, only after a grace period, optionally removes it.

## Database constraints and deletion

- Authorization IDs are unique, which prevents changing the idempotency key to consume a one-use authorization twice.
- Idempotency uniqueness is `(environment, data_domain, caller_id, operation, idempotency_key)`; the request fingerprint is compared separately.
- `(execution, attempt_no)` and `(execution, fencing_token)` are unique.
- Active token digests and artifact storage references are unique.
- Core evidence foreign keys use `PROTECT`; deleting a user or source reference cannot cascade through this isolated schema because external identities are stored as bounded identifiers, not foreign keys.
- Indexes support execution state scans, attempt lease expiry, token lookup, recipient listing, delivery timeline, and pending outbox scans.
- JSON is limited to versioned obligation/operation payloads and outbox facts. Authoritative state, counts, identities, timestamps, and hashes use explicit columns.

## Security decisions

- Internal API authentication and execution authority signing use separate secrets.
- Share tokens are generated using `secrets.token_urlsafe(32)` and persisted only as a peppered HMAC digest.
- Recipient authentication never derives from the share token; both factors are compared at every admission.
- Files are referenced by normalized relative paths under a configured root. Absolute paths, `..`, and symlinked storage directories are rejected.
- Artifact digest and file existence are checked before admission. Failure changes execution to `repair_required` and blocks access.
- All delivery responses are private/no-store and contain no public or presigned storage URL.
- Evaluation mode cannot create shares.

## Failure matrix

| Failure | Result | Recovery |
| --- | --- | --- |
| Partial candidate write | File is removed by the writer; execution fails | Retry requires an upstream-authorized new logical attempt |
| Candidate complete, DB reference write fails | Candidate remains private | Orphan reconciliation after lease/grace checks |
| Final file complete, artifact registration fails | Private orphan remains; execution fails | Orphan scan covers finalized and candidate areas, followed by reviewed cleanup |
| DB state committed, scheduling signal lost | Durable state remains queryable | Worker scans persistent state; do not re-execute completed work |
| Business commit succeeds, event publication fails | Pending outbox row remains | Retry only event publication; consumer deduplicates `event_id` |
| Registered artifact missing or hash differs | Access denied; execution becomes `repair_required` | Keep sharing paused and restore/verify artifact |
| Worker lease expires | Attempt becomes `stale`; old fence cannot register | Reauthorize/requeue through an approved scheduler policy |
| Stream ends without client/sink acknowledgement | Delivery remains `unknown` | Evidence-bearing receipt or manual reconciliation |
| Share response lost | Stable share exists; raw token is unrecoverable | Authenticated token rotation invalidates the old digest |
| Old database backup restored | Service may contain obsolete grants | Pause access, reconcile, invalidate/rotate grants, then reopen |

## Decisions still required

- Exact compatibility adapter from the parent `ExecutionAuthorization` Python object to the signed wire form.
- Recipient identity mapping between the parent user model and this service's stable string identifier.
- Production private storage backend and its atomicity/revocation semantics.
- Upstream quota settlement and unknown-delivery reconciliation contract.
- Outbox transport and audit consumer schema/version acceptance.
- Whether an admission committed before revocation may continue streaming. This reference permits an already admitted stream to continue and does not claim it can recall bytes already delivered.
- Retention periods and legal deletion/anonymization rules.
