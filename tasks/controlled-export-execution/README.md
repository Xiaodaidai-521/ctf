# Controlled Export Execution Service

This is an isolated reference service for controlled CSV/XLSX export execution. It is deliberately not wired into the parent repository's URL configuration, settings, models, or public media paths. Integration must be an explicit, separately reviewed change.

## Delivered behavior

- Accepts only HMAC-signed execution authorizations from a trusted internal caller.
- Keeps `NotExecutable` dispositions separate by rejecting anything other than `allow` or `mask`.
- Binds input bytes, asset version, scope, plan, environment, data domain, subject, and caller to the execution.
- Rebuilds CSV/XLSX protected copies from the authorized scope; it never overwrites or returns the input file.
- Rejects unknown mandatory obligations, unsupported transformations, hidden XLSX rows/columns/sheets, formulas, comments, hyperlinks, external links, embedded content, path traversal, and resource-limit violations.
- Applies formula neutralization to output headers as well as data cells. XLSX header cells that are real formulas, comments, or hyperlinks are rejected before the protected copy is built, including headers outside the authorized column scope. Headers that collide after neutralization are rejected.
- Enforces signed `share_creation` obligations when a share is created, replayed, admitted, or has its token rotated: `bind_recipient` must equal the normalized recipient, and `set_expiry` is an absolute upper bound that a share may undercut but never exceed. Shares persisted before these obligations were defined are refused rather than repaired.
- Records `record_receipt` obligations on every terminal delivery result (stream exhaustion, failure, or external receipt) by linking the obligation IDs to the delivery outbox event and keeping the full external evidence reference. Recording an `unknown` result is not a claim that the recipient read or stored the file.
- Uses short database transactions for claim and result registration. File processing occurs outside row locks. Each attempt gets a lease and monotonically increasing fencing token.
- Separates execution, attempt, immutable protected artifact, share grant, delivery attempt, idempotency record, and outbox event state.
- Stores artifacts below a private, non-web-served root and returns no storage path through the API.
- Creates recipient-bound shares only outside evaluation mode. A share needs both the authenticated recipient and a random token whose HMAC digest is stored.
- Serializes share revocation and delivery admission on the same `ShareGrant` row.
- Records `admitted_at`, `response_started_at`, and `completed_at` separately. Server stream exhaustion stays `unknown` until an evidence-bearing receipt confirms completion.
- Creates outbox events in the same database transaction as state changes. Events contain no raw token, sensitive file content, or private storage reference.

## Local setup

Python 3.12 or newer is required by Django 6.0.

```powershell
cd tasks/controlled-export-execution
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Load `.env` values into the process using the deployment's secret manager or shell. The service intentionally does not parse `.env` itself. Configure all four secrets before running a non-debug server.

```powershell
.\.venv\Scripts\python.exe manage.py migrate --noinput
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8010
```

The supplied `scripts/run-dev.ps1` performs migration and starts the same loopback-only development server. Do not expose Django's development server to a network.

## API boundary

Internal endpoints require both headers:

```text
X-Internal-Authorization: Bearer <service credential>
X-Caller-Id: <stable trusted service id>
```

Execution additionally requires `X-Authorization-Signature` and `Idempotency-Key`. The signature is lowercase HMAC-SHA256 over deterministic JSON (`sort_keys=true`, compact separators, UTF-8) using the execution authority secret.

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/controlled-export/executions/` | Submit signed authorization, JSON plan, and file as multipart data |
| POST | `/api/controlled-export/shares/` | Create a recipient-bound share outside evaluation mode |
| POST | `/api/controlled-export/shares/{id}/rotate-token/` | Issue a new token and invalidate the old digest |
| POST | `/api/controlled-export/shares/{id}/revoke/` | Revoke future admissions |
| POST | `/api/controlled-export/deliveries/{id}/result/` | Record evidence-bearing terminal delivery result |
| GET | `/api/controlled-export/shares/{id}/preview/` | Authenticated recipient preview with `X-Share-Token` |
| GET | `/api/controlled-export/shares/{id}/download/` | Authenticated recipient download with `X-Share-Token` |

The initial share response contains the raw token exactly once. An idempotent replay returns the stable `share_id` with `token_recovery=rotate_required`; it cannot recover the secret because only its digest is stored.

## Transformation plan

Example fixtures are in `fixtures/`. Supported operations are:

- `mask_columns` with the `fixed` strategy;
- `drop_columns`;
- `sanitize_formulas` (formula-like CSV/string cells are prefixed with an apostrophe).

The service always projects only the declared columns and, for XLSX, only declared worksheets. XLSX output is a new workbook, so unselected sheets, styles, macros, metadata, and hidden package members are not copied.

### Share and delivery obligations

`bind_recipient`, `set_expiry`, and `record_receipt` accept only version `"1"` (the default when omitted) and reject unknown parameters:

```json
{"obligation_id": "bind-1", "type": "bind_recipient", "phase": "share_creation",
 "parameters": {"recipient_id": "42"}, "version": "1"}
{"obligation_id": "expiry-1", "type": "set_expiry", "phase": "share_creation",
 "parameters": {"expires_at": "2026-10-20T12:00:00+00:00"}, "version": "1"}
{"obligation_id": "receipt-1", "type": "record_receipt", "phase": "post_delivery",
 "parameters": {}, "version": "1"}
```

`redact` and `sanitize_formulas` keep their existing `before_publish` semantics. Multiple `set_expiry` obligations are all enforced by using the earliest bound; conflicting `bind_recipient` recipients are rejected at authorization validation.

The delivery outbox payload for a terminal result carries `obligation_ids` and the full `evidence_ref`. `measurement_basis` remains a truncated human-readable summary and is not the authoritative evidence value.

## Operations and recovery

```powershell
.\.venv\Scripts\python.exe manage.py expire_stale_attempts
.\.venv\Scripts\python.exe manage.py reconcile_private_storage
.\.venv\Scripts\python.exe manage.py reconcile_orphan_candidates --grace-seconds 3600
```

The orphan command scans both candidate and finalized private areas and is dry-run by default. Add `--delete` only after review. Its grace period cannot be shorter than the attempt lease.

After restoring an old backup, keep all sharing endpoints unavailable until the database, artifact hashes, signing/pepper key versions, stale attempts, outbox state, and every pre-restore share have been reconciled. Rotate or invalidate pre-restore share tokens before reopening access. See `docs/RECOVERY.md`.

## Tests

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py test controlled_export -v 2
```

Set `CONTROLLED_EXPORT_DATABASE_URL` to a disposable PostgreSQL database to run the real row-lock test. SQLite results do not establish PostgreSQL locking, lock-wait, or isolation behavior.

## Integration status

The HMAC authority and internal caller authentication are concrete adapters, but they are not connected to the parent repository's `export_risk`, `export_quota`, `audit`, or `resources` modules. Outbox publication and upstream reservation settlement remain downstream integration work. No production storage, production identity provider, or deployment has been tested.
