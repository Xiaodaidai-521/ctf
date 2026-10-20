"""Opt-in bounded PostgreSQL adapter. Never opens or migrates a database itself."""
from copy import deepcopy
from dataclasses import fields
import json

from .classification import require
from .review import ReviewState


def encode_state(state):
    value = {}
    for f in fields(state):
        obj = deepcopy(getattr(state, f.name))
        if f.name == 'bundles':
            for bundle in obj.values():
                bundle['_cells'] = [[list(k), v] for k, v in bundle['_cells'].items()]
        if f.name in ('heads', 'keys'):
            obj = [[list(k), v] for k, v in obj.items()]
        value[f.name] = obj
    return value


def decode_state(value):
    value = deepcopy(value)
    for bundle in value['bundles'].values():
        bundle['_cells'] = {tuple(k): v for k, v in bundle['_cells']}
    for key in ('heads', 'keys'):
        value[key] = {tuple(k): v for k, v in value[key]}
    return ReviewState(**value)


class DjangoReviewRepository:
    """One locked aggregate enforces uniqueness atomically, including other scopes.

    Limited to 16 MiB, intended for internal validation/small deployments ONLY.
    Not a throughput design. Durable outbox acknowledgement uses the same row;
    transport runs outside transactions and may duplicate delivery after crashes.
    """
    def read(self, operation):
        from django.db import connection
        from .models import ReviewLedger
        require(connection.vendor == 'postgresql', 'REVIEW_REPOSITORY_UNSUPPORTED')
        payload = ReviewLedger.objects.filter(pk=1).values_list('state', flat=True).first()
        state = ReviewState() if payload is None else decode_state(payload)
        return deepcopy(operation(state))

    def atomic(self, operation):
        from django.db import connection, transaction
        from .models import ReviewLedger
        require(connection.vendor == 'postgresql', 'REVIEW_REPOSITORY_UNSUPPORTED')
        with transaction.atomic():
            ReviewLedger.objects.get_or_create(pk=1, defaults={'state': encode_state(ReviewState())})
            row = ReviewLedger.objects.select_for_update().get(pk=1)
            state = decode_state(row.state)
            result = deepcopy(operation(state))
            payload = encode_state(state)
            require(len(json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8')) <= 16 * 1024 * 1024,
                    'RESOURCE_LIMIT')
            if payload != row.state:
                row.state = payload
                row.save(update_fields=['state'])
            return result
