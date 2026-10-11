"""Quota reserve/commit/release/reconcile over a shared bucket lock (R2).

Atomicity: every mutation locks the shared QuotaBucket row first
(``select_for_update``), then the reservation — a consistent lock order. On
PostgreSQL this serialises concurrent reservations against the same bucket; on
SQLite ``select_for_update`` is a no-op, so the concurrency guarantee is only
asserted under real PostgreSQL (see tests, ``@skipUnless``).
"""

from dataclasses import dataclass
from datetime import timedelta
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


@dataclass(frozen=True)
class ReservationResult:
    reservation_id: str
    bucket_id: int
    amount: int
    idempotent_replay: bool = False


class QuotaService:
    """Reference quota authority (non-production)."""

    @staticmethod
    @transaction.atomic
    def reserve(*, subject_id: str, data_domain: str, window_key: str, amount: int,
                request_fingerprint: str, reservation_id: str, limit: int,
                ttl_seconds: int = DEFAULT_TTL_SECONDS) -> ReservationResult:
        # First-create race is safe via the unique constraint + get_or_create.
        bucket, _ = QuotaBucket.objects.get_or_create(
            subject_id=subject_id, data_domain=data_domain, window_key=window_key,
            defaults={'limit': limit},
        )
        # Lock the SHARED bucket row — not the per-reservation row.
        bucket = QuotaBucket.objects.select_for_update().get(pk=bucket.pk)

        existing = QuotaReservation.objects.filter(reservation_id=reservation_id).first()
        if existing is not None:  # idempotent reserve: no double increment
            return ReservationResult(existing.reservation_id, bucket.pk, existing.amount, True)

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
        return ReservationResult(reservation.reservation_id, bucket.pk, amount)

    @staticmethod
    def commit(*, reservation_id: str, delivered_amount: int) -> None:
        """Move a reservation to settled using the actual delivered amount."""
        with transaction.atomic():
            res0 = QuotaReservation.objects.get(reservation_id=reservation_id)
            bucket = QuotaBucket.objects.select_for_update().get(pk=res0.bucket_id)
            res = QuotaReservation.objects.select_for_update().get(reservation_id=reservation_id)
            if res.state != 'reserved':
                raise QuotaStateError(f"cannot commit from state {res.state}")
            delivered = max(0, min(delivered_amount, res.amount))
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
            res0 = QuotaReservation.objects.get(reservation_id=reservation_id)
            bucket = QuotaBucket.objects.select_for_update().get(pk=res0.bucket_id)
            res = QuotaReservation.objects.select_for_update().get(reservation_id=reservation_id)
            if res.state != 'reserved':
                raise QuotaStateError(f"cannot release from state {res.state}")
            bucket.active_reserved -= res.amount
            bucket.save(update_fields=['active_reserved', 'updated_at'])
            res.state = 'released'
            res.save(update_fields=['state'])

    @staticmethod
    def reconcile(*, reservation_id: str, delivered_amount: Optional[int] = None) -> None:
        """Reconcile an expired/uncertain reservation.

        delivered_amount=None means the result is UNKNOWN: the hold is moved to
        ``unknown_reserved`` (not released), so the capacity is not handed back
        to a new request until delivery is confirmed (review R2 / I6).
        """
        with transaction.atomic():
            res0 = QuotaReservation.objects.get(reservation_id=reservation_id)
            bucket = QuotaBucket.objects.select_for_update().get(pk=res0.bucket_id)
            res = QuotaReservation.objects.select_for_update().get(reservation_id=reservation_id)
            if res.state != 'reserved':
                raise QuotaStateError(f"cannot reconcile from state {res.state}")
            if delivered_amount is None:
                bucket.active_reserved -= res.amount
                bucket.unknown_reserved += res.amount
                bucket.save(update_fields=['active_reserved', 'unknown_reserved', 'updated_at'])
                res.state = 'unknown'
                res.save(update_fields=['state'])
            else:
                delivered = max(0, min(delivered_amount, res.amount))
                bucket.active_reserved -= res.amount
                bucket.settled += delivered
                bucket.save(update_fields=['active_reserved', 'settled', 'updated_at'])
                res.state = 'committed'
                res.settled_amount = delivered
                res.save(update_fields=['state', 'settled_amount'])
