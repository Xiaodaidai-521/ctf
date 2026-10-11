"""Quota reserve/commit/release/reconcile over a shared bucket lock (R2).

Atomicity: every mutation locks the shared QuotaBucket row first
(``select_for_update``), then the reservation — a consistent lock order. On
PostgreSQL this serialises concurrent reservations against the same bucket; on
SQLite ``select_for_update`` is a no-op, so the concurrency guarantee is only
asserted under real PostgreSQL (see tests, ``@skipUnless``).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from django.db import transaction
from django.utils import timezone

from .models import QuotaBucket, QuotaReservation

DEFAULT_TTL_SECONDS = 300


class QuotaError(Exception):
    """Base quota error."""


class QuotaExceeded(QuotaError):
    """Reservation would exceed the bucket limit."""


class QuotaStateError(QuotaError):
    """Reservation is not in a state that allows the requested transition."""


class QuotaConflict(QuotaError):
    """Idempotent reuse with a different binding, or an invalid delivered amount."""


def _validated_delivery(delivered_amount: int, reserved: int) -> int:
    """Reject negative or over-reservation delivery; never silently clamp (F8)."""
    if delivered_amount is None or delivered_amount < 0:
        raise ValueError(f"delivered_amount must be a non-negative integer, got {delivered_amount!r}")
    if delivered_amount > reserved:
        raise QuotaConflict(f"delivered {delivered_amount} exceeds reserved {reserved}")
    return delivered_amount


@dataclass(frozen=True)
class ReservationResult:
    reservation_id: str
    bucket_id: int
    amount: int
    idempotent_replay: bool = False
    expires_at: Optional[datetime] = None


def _locked_reservation(reservation_id: str):
    """Lock bucket before reservation; callers must hold an atomic transaction."""
    original = QuotaReservation.objects.get(reservation_id=reservation_id)
    bucket = QuotaBucket.objects.select_for_update().get(pk=original.bucket_id)
    reservation = QuotaReservation.objects.select_for_update().get(reservation_id=reservation_id)
    return bucket, reservation


def _require_active(reservation, now):
    """Check execution eligibility only; expired holds are NOT released."""
    if reservation.state != 'reserved':
        raise QuotaStateError(f"reservation {reservation.reservation_id} is {reservation.state}")
    if (reservation.expires_at is None or reservation.expires_at.utcoffset() is None
            or now >= reservation.expires_at):
        raise QuotaStateError(f"reservation {reservation.reservation_id} has expired or unknown expiry")


class QuotaService:
    """Reference quota authority (non-production)."""

    @staticmethod
    @transaction.atomic
    def reserve(*, subject_id: str, data_domain: str, window_key: str, amount: int,
                request_fingerprint: str, reservation_id: str, limit: int,
                ttl_seconds: int = DEFAULT_TTL_SECONDS) -> ReservationResult:
        if amount < 0:
            raise ValueError(f"reservation amount must be non-negative, got {amount!r}")
        # First-create race is safe via the unique constraint + get_or_create.
        bucket, _ = QuotaBucket.objects.get_or_create(
            subject_id=subject_id, data_domain=data_domain, window_key=window_key,
            defaults={'limit': limit},
        )
        # Lock the SHARED bucket row — not the per-reservation row.
        bucket = QuotaBucket.objects.select_for_update().get(pk=bucket.pk)

        existing = QuotaReservation.objects.select_for_update().filter(reservation_id=reservation_id).first()
        if existing is not None:
            # Idempotent replay only when the full binding matches; a reused id
            # with a different bucket/fingerprint/amount is a conflict (F6). The
            # replay reports the reservation's ACTUAL bucket, not this call's.
            if (existing.bucket_id != bucket.pk
                    or existing.request_fingerprint != request_fingerprint
                    or existing.amount != amount):
                raise QuotaConflict(
                    f"reservation {reservation_id} already bound to a different "
                    f"(bucket={existing.bucket_id}, amount={existing.amount})"
                )
            # One source of truth for "still an active, unexpired hold".
            _require_active(existing, timezone.now())
            return ReservationResult(existing.reservation_id, existing.bucket_id, existing.amount, True,
                                     existing.expires_at)

        if bucket.available < amount:
            raise QuotaExceeded(
                f"available {bucket.available} < requested {amount} for {bucket}"
            )

        reservation = QuotaReservation.objects.create(
            reservation_id=reservation_id, bucket=bucket, amount=amount, state='reserved',
            request_fingerprint=request_fingerprint,
            expires_at=timezone.now() + timedelta(seconds=ttl_seconds),
        )
        bucket.active_reserved += amount
        bucket.save(update_fields=['active_reserved', 'updated_at'])
        return ReservationResult(reservation.reservation_id, bucket.pk, amount, False, reservation.expires_at)

    @staticmethod
    @transaction.atomic
    def require_active(*, reservation_id: str, request_fingerprint: str,
                       amount: Optional[int] = None, now: Optional[datetime] = None) -> ReservationResult:
        """Validate a live hold under bucket -> reservation locks, without release.

        Used by execution preparation/claim. A reservation in unknown, released
        or committed state, or past its exclusive expiry, is not executable.
        """
        try:
            _, reservation = _locked_reservation(reservation_id)
        except QuotaReservation.DoesNotExist as exc:
            raise QuotaStateError(f"missing reservation {reservation_id}") from exc
        if (reservation.request_fingerprint != request_fingerprint
                or (amount is not None and reservation.amount != amount)):
            raise QuotaConflict(f"reservation {reservation_id} binding mismatch")
        _require_active(reservation, now if now is not None else timezone.now())
        return ReservationResult(reservation.reservation_id, reservation.bucket_id,
                                 reservation.amount, True, reservation.expires_at)

    @staticmethod
    def commit(*, reservation_id: str, delivered_amount: int) -> None:
        """Move a reservation to settled using the actual delivered amount."""
        with transaction.atomic():
            bucket, res = _locked_reservation(reservation_id)
            if res.state != 'reserved':
                raise QuotaStateError(f"cannot commit from state {res.state}")
            delivered = _validated_delivery(delivered_amount, res.amount)
            bucket.active_reserved -= res.amount
            bucket.settled += delivered
            bucket.save(update_fields=['active_reserved', 'settled', 'updated_at'])
            res.state = 'committed'
            res.settled_amount = delivered
            res.save(update_fields=['state', 'settled_amount'])

    @staticmethod
    def release(*, reservation_id: str) -> None:
        """Release an active reservation back to the bucket."""
        with transaction.atomic():
            bucket, res = _locked_reservation(reservation_id)
            if res.state != 'reserved':
                raise QuotaStateError(f"cannot release from state {res.state}")
            bucket.active_reserved -= res.amount
            bucket.save(update_fields=['active_reserved', 'updated_at'])
            res.state = 'released'
            res.save(update_fields=['state'])

    @staticmethod
    def reconcile(*, reservation_id: str, delivered_amount: Optional[int] = None) -> None:
        """Reconcile an expired/uncertain reservation.

        From ``reserved``: delivered_amount=None moves the hold to
        ``unknown_reserved`` (not released) so capacity is not handed back until
        delivery is confirmed (review R2 / I6); a delivered amount settles it.
        From ``unknown`` (review F7): a later confirmed receipt settles the hold
        out of ``unknown_reserved``; a repeated unknown result is an idempotent
        no-op. From ``committed``: identical confirmed amounts are also no-ops;
        a different amount conflicts and cannot rewrite the settled evidence.
        Capacity is never released without a confirmed delivered amount.
        """
        with transaction.atomic():
            bucket, res = _locked_reservation(reservation_id)

            if res.state == 'reserved':
                if delivered_amount is None:
                    bucket.active_reserved -= res.amount
                    bucket.unknown_reserved += res.amount
                    bucket.save(update_fields=['active_reserved', 'unknown_reserved', 'updated_at'])
                    res.state = 'unknown'
                    res.save(update_fields=['state'])
                    return
                delivered = _validated_delivery(delivered_amount, res.amount)
                bucket.active_reserved -= res.amount
                bucket.settled += delivered
                bucket.save(update_fields=['active_reserved', 'settled', 'updated_at'])
                res.state = 'committed'
                res.settled_amount = delivered
                res.save(update_fields=['state', 'settled_amount'])
                return

            if res.state == 'unknown':
                if delivered_amount is None:
                    return  # idempotent: the result is still unknown
                delivered = _validated_delivery(delivered_amount, res.amount)
                bucket.unknown_reserved -= res.amount
                bucket.settled += delivered
                bucket.save(update_fields=['unknown_reserved', 'settled', 'updated_at'])
                res.state = 'committed'
                res.settled_amount = delivered
                res.save(update_fields=['state', 'settled_amount'])
                return

            if res.state == 'committed':
                if delivered_amount == res.settled_amount:
                    return  # confirmed receipt replay: no second accounting
                raise QuotaConflict(
                    f"reservation {reservation_id} already settled at {res.settled_amount}, "
                    f"not {delivered_amount}"
                )

            raise QuotaStateError(f"cannot reconcile from state {res.state}")
