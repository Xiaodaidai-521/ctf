"""Deterministic teacher sampling for feedback review.

The batch records its scope, population snapshot, random seed, selected IDs and
selection reasons.  Re-running the same scope and seed on the same population
produces the same random sample.  High-risk items are recorded separately and
are never presented as a random estimate of the population error rate.
"""

import hashlib
import math
import random
import secrets
import uuid
from datetime import datetime, time as datetime_time

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from .. import constants
from ..models import FeedbackSamplingBatch, FeedbackSamplingItem, FeedbackTicket


class SamplingError(ValueError):
    def __init__(self, detail, *, code='invalid_sampling'):
        super().__init__(detail)
        self.detail = detail
        self.code = code


def _parse_dt(value):
    if value in (None, ''):
        return None
    parsed = parse_datetime(str(value)) if 'T' in str(value) else None
    if parsed is None:
        date_value = parse_date(str(value))
        if date_value is None:
            raise SamplingError('时间筛选必须为 ISO 8601 日期或时间。', code='invalid_datetime')
        parsed = timezone.make_aware(
            datetime.combine(date_value, datetime_time.min),
            timezone.get_current_timezone(),
        )
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _normalize_scope(scope):
    scope = scope or {}
    statuses = scope.get('statuses') or []
    categories = scope.get('categories') or []
    issue_types = scope.get('issue_types') or []
    for value in statuses:
        if value not in dict(constants.STATUS_CHOICES):
            raise SamplingError(f'未知工单状态：{value}', code='invalid_status')
    for value in categories:
        if value not in dict(constants.CATEGORY_CHOICES):
            raise SamplingError(f'未知反馈类别：{value}', code='invalid_category')
    return {
        'statuses': list(statuses),
        'categories': list(categories),
        'issue_types': list(issue_types),
        'created_from': scope.get('created_from') or '',
        'created_to': scope.get('created_to') or '',
        'owner_id': scope.get('owner_id') or None,
        'include_duplicates': bool(scope.get('include_duplicates')),
        'exclude_prior': bool(scope.get('exclude_prior', True)),
    }


def _population(scope):
    queryset = FeedbackTicket.objects.all()
    if not scope['include_duplicates']:
        queryset = queryset.exclude(status=constants.STATUS_DUPLICATE).exclude(duplicate_of__isnull=False)
    if scope['statuses']:
        queryset = queryset.filter(status__in=scope['statuses'])
    else:
        queryset = queryset.exclude(status__in=[
            constants.STATUS_SUBMITTED, constants.STATUS_DEDUPLICATING,
        ])
    if scope['categories']:
        queryset = queryset.filter(category__in=scope['categories'])
    if scope['issue_types']:
        queryset = queryset.filter(issue_type__in=scope['issue_types'])
    created_from = _parse_dt(scope['created_from'])
    created_to = _parse_dt(scope['created_to'])
    if created_from:
        queryset = queryset.filter(created_at__gte=created_from)
    if created_to:
        queryset = queryset.filter(created_at__lte=created_to)
    if scope['owner_id']:
        queryset = queryset.filter(owner_id=scope['owner_id'])
    if scope['exclude_prior']:
        queryset = queryset.exclude(sampling_items__isnull=False)
    # Sort in Python by the public UUID string.  SQLite and PostgreSQL may store
    # UUIDs differently, and a reproducible sample must not depend on the
    # database's internal UUID ordering.
    return sorted(queryset, key=lambda ticket: str(ticket.feedback_id))


def create_batch(actor, *, scope, sample_size=None, sample_ratio=None, random_seed=None,
                 risk_ticket_ids=None, notes=''):
    normalized = _normalize_scope(scope)
    population = _population(normalized)
    if len(population) > 5000:
        raise SamplingError('首期单批总体超过 5000 条，请缩小范围。', code='population_too_large')
    if sample_size is None and sample_ratio is None:
        raise SamplingError('必须提供 sample_size 或 sample_ratio。', code='sample_size_required')
    if sample_size is not None:
        try:
            sample_size = int(sample_size)
        except (TypeError, ValueError):
            raise SamplingError('sample_size 必须为整数。', code='invalid_sample_size')
        if sample_size <= 0:
            raise SamplingError('sample_size 必须大于 0。', code='invalid_sample_size')
    else:
        try:
            sample_ratio = float(sample_ratio)
        except (TypeError, ValueError):
            raise SamplingError('sample_ratio 必须为 0—1 之间的小数。', code='invalid_sample_ratio')
        if not 0 < sample_ratio <= 1:
            raise SamplingError('sample_ratio 必须为 0—1 之间的小数。', code='invalid_sample_ratio')
        sample_size = max(1, math.ceil(len(population) * sample_ratio))

    population_ids = [str(ticket.feedback_id) for ticket in population]
    population_set = set(population_ids)
    risk_ids = []
    for raw in risk_ticket_ids or []:
        try:
            value = str(uuid.UUID(str(raw)))
        except (TypeError, ValueError):
            raise SamplingError('高风险样本 ID 必须为反馈 UUID。', code='invalid_risk_id')
        if value not in population_set:
            raise SamplingError('高风险样本不在当前抽样总体中。', code='risk_not_in_population')
        if value not in risk_ids:
            risk_ids.append(value)
    risk_ids = sorted(risk_ids)

    seed = int(random_seed) if random_seed is not None else secrets.randbits(63)
    if seed < 0:
        raise SamplingError('随机种子必须为非负整数。', code='invalid_seed')

    candidates = [value for value in population_ids if value not in set(risk_ids)]
    target_random = max(0, sample_size - len(risk_ids))
    if len(candidates) <= target_random:
        random_ids = list(candidates)
        random_reason = constants.SAMPLING_CENSUS
        method = constants.SAMPLING_CENSUS if not risk_ids else constants.SAMPLING_RANDOM
    else:
        rng = random.Random(seed)
        random_ids = sorted(rng.sample(candidates, target_random))
        random_reason = constants.SAMPLING_RANDOM
        method = constants.SAMPLING_RANDOM
    if risk_ids and not random_ids:
        method = constants.SAMPLING_HIGH_RISK

    population_hash = hashlib.sha256(','.join(population_ids).encode('utf-8')).hexdigest()
    actual_sample_size = len(risk_ids) + len(random_ids)
    scope_payload = dict(normalized)
    scope_payload['sample_size'] = sample_size
    scope_payload['sample_ratio'] = sample_ratio
    scope_payload['random_seed'] = seed
    scope_payload['risk_ticket_ids'] = risk_ids
    scope_payload['population_count'] = len(population)
    scope_payload['actual_sample_size'] = actual_sample_size

    with transaction.atomic():
        batch = FeedbackSamplingBatch.objects.create(
            scope=scope_payload,
            population_count=len(population),
            population_hash=population_hash,
            population_ids=population_ids,
            sample_size=sample_size,
            random_seed=seed,
            method=method,
            exclude_prior=normalized['exclude_prior'],
            notes=notes or '',
            created_by=actor,
        )
        tickets = {
            str(ticket.feedback_id): ticket
            for ticket in FeedbackTicket.objects.filter(feedback_id__in=population_ids)
        }
        rank = 0
        for feedback_id in risk_ids:
            FeedbackSamplingItem.objects.create(
                batch=batch, ticket=tickets[feedback_id],
                selected_reason=constants.SAMPLING_HIGH_RISK,
                ticket_version=tickets[feedback_id].version, rank=rank,
            )
            rank += 1
        for feedback_id in random_ids:
            FeedbackSamplingItem.objects.create(
                batch=batch, ticket=tickets[feedback_id],
                selected_reason=random_reason,
                ticket_version=tickets[feedback_id].version, rank=rank,
            )
            rank += 1
    return batch


def batch_payload(batch, *, include_items=True):
    payload = {
        'batch_id': str(batch.batch_id),
        'scope': batch.scope,
        'population_count': batch.population_count,
        'population_hash': batch.population_hash,
        'population_ids': batch.population_ids,
        'sample_size': batch.sample_size,
        'random_seed': batch.random_seed,
        'method': batch.method,
        'exclude_prior': batch.exclude_prior,
        'notes': batch.notes,
        'created_by': batch.created_by_id,
        'created_at': batch.created_at.isoformat(),
        'reproducible': {
            'seed': batch.random_seed,
            'population_hash': batch.population_hash,
            'method': batch.method,
            'note': '相同总体、相同范围与相同种子应产生相同随机样本；高风险样本单列。',
        },
    }
    if include_items:
        payload['items'] = [
            {
                'ticket_id': str(item.ticket.feedback_id),
                'ticket_version': item.ticket_version,
                'selected_reason': item.selected_reason,
                'selected_reason_label': constants.SAMPLING_REASON_LABELS.get(
                    item.selected_reason, item.selected_reason,
                ),
                'rank': item.rank,
                'status': item.ticket.status,
                'status_label': constants.STATUS_LABELS.get(item.ticket.status, item.ticket.status),
                'category': item.ticket.category,
                'priority_reason': item.ticket.priority_reason,
            }
            for item in batch.items.select_related('ticket').all()
        ]
    return payload
