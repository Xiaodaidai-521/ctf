# Recovery runbook

## Routine reconciliation

1. Run `reconcile_private_storage`. Any failure means affected access must remain denied.
2. Run `expire_stale_attempts`; it fences expired workers but does not delete candidates.
3. Run `reconcile_orphan_candidates` without `--delete` and review every candidate.
4. Confirm no active lease, registered artifact, or share references a candidate before using `--delete` with a grace period at least as long as the configured lease.
5. Retry pending outbox publication by `event_id`; never rerun file execution merely to recreate an event.

## Backup restore

1. Pause execution admission, share creation, preview, and download at the trusted ingress.
2. Verify database revision, artifact inventory and hashes, authorization signing key version, and share-token pepper version.
3. Expire or reconcile stale leases and mark in-progress transmissions `unknown` unless evidence proves a stronger outcome.
4. Replay outbox events with stable `event_id`; downstream consumers must deduplicate.
5. Treat every restored share as untrusted. Revalidate authorization and recipient binding, or invalidate all old token digests and issue new grants/tokens.
6. Reconcile quota reservations with the upstream authority. Do not reconstruct or double-settle its ledger locally.
7. Reopen access only after isolation, cross-domain references, expiration, revocation, and artifact integrity checks pass.

## Rollback

This service has no parent-project integration to disable. Stop its process and keep its private storage inaccessible. Preserve execution, delivery, idempotency, and outbox evidence according to the approved retention policy. Schema rollback is not authorized because dropping evidence tables is destructive; use a forward migration after review.
