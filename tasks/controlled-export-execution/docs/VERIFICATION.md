# Verification record

Environment: Windows, Python 3.12.10, Django 6.0.3, DRF 3.16.1, openpyxl 3.1.5, SQLite in-memory test database, local temporary private storage. All fixtures are synthetic.

Commands actually run:

```text
python -m compileall -q controlled_export controlled_export_service manage.py
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test controlled_export -v 2
python manage.py migrate --plan
```

The latest recorded test run is updated only after a successful final verification. PostgreSQL behavior is not inferred from SQLite.

Latest suite result: 57 tests discovered, 56 passed, and the single PostgreSQL-only locking test was skipped on SQLite.

## Header and obligation remediation (2026-10-20)

Two gaps found in review are closed and covered by tests:

- Output headers now go through the same formula neutralization as data cells (CSV and XLSX). XLSX header cells holding a real formula, comment, or hyperlink are rejected with `XLSX_ACTIVE_CONTENT` before any protected copy is written, including header cells for columns outside the authorized scope. Headers that become duplicates after neutralization are rejected (`CSV_HEADER_COLLISION`, `XLSX_HEADER_COLLISION`).
- `bind_recipient`, `set_expiry`, and `record_receipt` now have a versioned parameter contract and are enforced when shares are created, replayed, admitted, or re-tokenized. Terminal delivery events carry `obligation_ids` and the full external `evidence_ref`.

Evidence for this remediation: `controlled_export.tests.test_transformations.HeaderFormulaTests` (7 tests), `ObligationContractTests` (10 tests), `ShareObligationEnforcementTests` (9 tests), and `ShareApiObligationTests` (4 tests). The full suite ran 57 tests with 56 passing and 1 PostgreSQL-only skip. No migration was required (`makemigrations --check --dry-run` reported no changes).

Limits unchanged: PostgreSQL row-lock, lock-wait, and isolation behavior is still unverified; there is no upstream obligation source, receipt authenticity verification, or downstream outbox consumer.

## Acceptance cases

| # | Scenario | Expected | Actual evidence | Status / gap |
| --- | --- | --- | --- | --- |
| 1 | `allow` outputs authorized scope only | No extra columns/sheets | Transformer always projects `scope.columns` and selected worksheets | Passed in shared transformation path; explicit mask test covers projection |
| 2 | `mask` waits for all pre-publish obligations | Protected copy only after validation | CSV/XLSX tests verify mask and output registration follows transform validation | Passed |
| 3 | `deny` has no accessible output | Reject before execution | `test_not_executable_dispositions_are_rejected` | Passed |
| 4 | `require_approval` and `defer` do not deliver | Reject before execution | Same parameterized test | Passed |
| 5 | Data, scope, recipient, or plan changes invalidate binding | Reject mismatch | Hash/signature checks; wrong recipient and plan/input binding tests | Passed locally; real upstream adapter untested |
| 6 | Same idempotency key/content does not re-execute | Stable existing result | `test_same_idempotency_key_and_content_returns_existing_result` | Passed |
| 7 | Same idempotency key/different content conflicts | Conflict | `test_same_idempotency_key_with_different_binding_conflicts` | Passed |
| 8 | Only current concurrent worker registers | Old fence rejected | `test_stale_worker_cannot_overwrite_newer_execution_generation` | Passed logical fence; PostgreSQL lock test skipped |
| 9 | Unsupported obligation rejects execution | Explicit failure | `test_unknown_mandatory_obligation_is_rejected` | Passed |
| 10 | Transformation failure never falls back to input | No artifact/output | `test_transform_failure_never_registers_or_returns_original` | Passed |
| 11 | Non-recipient with valid link/token is denied | Deny | `test_recipient_token_expiry_and_revocation_are_checked_at_admission` | Passed |
| 12 | Expired/revoked share cannot start access | Deny at admission | Same test covers expiry and revocation | Passed |
| 13 | Repeated downloads have separate receipts | Different `delivery_id` | `test_repeated_downloads_receive_distinct_delivery_ids` | Passed |
| 14 | Interrupted/unconfirmed stream is not completed | `unknown` | `test_stream_exhaustion_is_unknown_until_external_receipt` | Passed for server-observable stream exhaustion |
| 15 | Unknown result does not release full quota | Preserve upstream hold | No quota mutation exists in this isolated service | Blocked pending upstream settlement adapter |
| 16 | Replayed outbox does not duplicate settlement/statistics | Consumer deduplicates `event_id` | Stable unique `event_id` produced; no downstream consumer supplied | Partial / downstream untested |
| 17 | Evaluation run creates no production share | Reject | `test_evaluation_execution_cannot_create_share` | Passed |
| 18 | Input and protected copy have no auth bypass URL | No public/static storage route | Isolated URL config plus private relative storage references | Passed at code/config level; deployment proxy untested |
| 19 | Changed request fingerprint with same key conflicts | Conflict | Idempotency binding test | Passed |
| 20 | New key cannot reuse one-use authorization | Unique authorization consumption | `test_switching_idempotency_key_cannot_reconsume_authorization` | Passed |
| 21 | Expired old worker cannot overwrite new result/file | Fence mismatch blocks write | Stale-worker test and per-attempt paths | Passed logical fence; remote storage behavior untested |
| 22 | File succeeds but DB registration fails | Private orphan, no access | Separate candidate/final paths and reconciliation command | Partial; failure-injection crash window not automated |
| 23 | Cleanup preserves active attempts and referenced files | Grace/lease-aware cleanup | Orphan command scans both private areas, excludes active/registered references, and its dry-run/delete behavior is tested | Passed locally; concurrent cleanup on PostgreSQL untested |
| 24 | Revoke/admit race follows commit order | Same-row serialization | Both operations lock `ShareGrant` | Untested on real PostgreSQL; lock test skipped on SQLite |
| 25 | Lost first share response is recoverable without token storage | Stable ID plus rotation | `test_token_is_returned_once_and_replay_requires_rotation` | Passed |
| 26 | Subject removal does not cascade-delete evidence | Evidence retained | Core evidence uses `PROTECT`; external IDs are scalar | Passed for isolated schema; parent identity lifecycle unintegrated |
| 27 | Cross-domain/environment valid ID is denied | Scope mismatch rejected | Environment checks and execution-owned share/artifact FKs | Partial; multi-domain integration test not supplied |
| 28 | Restored backup does not reopen revoked share | Pause, reconcile, invalidate | `docs/RECOVERY.md` runbook | Untested operational procedure |
| 29 | Repeated event has no downstream side effect | Consumer dedupe | Unique outbox IDs and at-least-once contract documented | Blocked pending downstream consumer |
| 30 | Migration, unique conflict, lock wait and old worker on target DB | Verify on PostgreSQL | Migration and unique/fence behavior verified on SQLite; PostgreSQL test is present and skipped | Partial / PostgreSQL required |

## Security checks

- CSV formula neutralization: passed for data cells and output headers.
- XLSX formula, hyperlink and hidden-row/column rejection: passed for data cells and header cells.
- XLSX output reconstruction and selected-sheet projection: passed.
- Path traversal rejection: passed. Symlink defense is implemented but remains platform-dependent and untested on this Windows environment.
- Token absence from outbox payloads: passed.
- Recipient plus token dual check: passed.
- Artifact tamper detection and `repair_required` transition: passed.
- Production enabling of an implicit mock authority: not possible; missing HMAC secret rejects requests and non-debug `runserver` refuses startup without required secrets.

## Verification limits

- No production deployment, proxy, object storage, identity provider, upstream risk service, quota authority, audit consumer, or evaluation orchestrator was available.
- No claim is made about PostgreSQL transaction isolation, lock timeout, deadlock handling, or concurrent correctness beyond the unexecuted PostgreSQL-specific test and the locally verified fencing logic.
- Server-side stream exhaustion cannot prove client persistence or reading; it remains `unknown` until a trusted external receipt is recorded.
