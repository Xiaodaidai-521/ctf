"""Synchronous managed worker unit; no web thread, model, queue dependency or public API."""
import json
import time
import unicodedata
from dataclasses import asdict

from .parsing import (AssetRef, InputError, Limits, PARSER_VERSION, ParserConfig, Scope, Selection,
                      normalize_scope, parse_table, read_private)
from .tasks import ParseTasks


def parse_snapshot(asset, *, config=ParserConfig(), limits=Limits(), scope=None):
    return dict(kind='parse-v1', asset=asdict(asset), config=asdict(config), limits=asdict(limits),
                parser_version=PARSER_VERSION, unicode_version=unicodedata.unidata_version,
                scope=asdict(normalize_scope(scope)) if scope else None)


def execute_one(repository, run_id, source, *, clock=lambda: int(time.time())):
    tasks = ParseTasks(repository)
    initial = repository.get(run_id)
    data = json.loads(initial.snapshot_json)
    try:
        if (data.get('kind') != 'parse-v1' or data.get('parser_version') != PARSER_VERSION
                or data.get('unicode_version') != unicodedata.unidata_version):
            raise InputError('CONFIG_UNSUPPORTED')
        asset, config, limits = AssetRef(**data['asset']), ParserConfig(**data['config']), Limits(**data['limits'])
        raw_scope = data['scope']
        scope = None if raw_scope is None else normalize_scope(Scope(raw_scope['asset_version_id'], tuple(
            Selection(s['sheet_id'], tuple(map(tuple, s['rows'])), tuple(map(tuple, s['columns'])))
            for s in raw_scope['selections']), raw_scope['include_header']))
    except (InputError, KeyError, TypeError, ValueError, AttributeError):
        rejected = tasks.claim(run_id, now=clock(), lease_seconds=30)
        return tasks.finish(run_id, token=rejected.attempts[-1].token, now=clock(), error_code='CONFIG_INVALID')
    # Lease covers the cooperative read + parse budgets and a bounded finalization margin.
    run = tasks.claim(run_id, now=clock(), lease_seconds=2 * limits.max_seconds + 30)
    token = run.attempts[-1].token
    last_check = 0.0
    def cancelled():
        nonlocal last_check
        monotonic = time.monotonic()
        if monotonic - last_check < 0.1:
            return False
        last_check = monotonic
        current = repository.get(run_id)
        return (current.cancel_requested or current.status != 'running'
                or current.attempts[-1].token != token or clock() >= current.attempts[-1].lease_expires)
    try:
        content = read_private(source, asset, principal=run.key[3], domain_id=run.key[0],
                               limits=limits, cancelled=cancelled)
        tasks.record_progress(run_id, token=token, now=clock(), stage='parse', processed_count=0, total_count=None)
        result = parse_table(content, asset, config=config, limits=limits, scope=scope, cancelled=cancelled)
        tasks.record_progress(run_id, token=token, now=clock(), stage='finalize',
                              processed_count=len(result.cells), total_count=len(result.cells))
        return repository.publish(run_id, token=token, now=clock(), result=result)
    except InputError as exc:
        if exc.code in ('STALE_ATTEMPT', 'TASK_VERSION_CONFLICT'):
            raise  # Recovery owns this attempt; a stale worker must not publish failure either.
        return tasks.finish(run_id, token=token, now=clock(), error_code=exc.code)
    except Exception:
        # No raw source, storage/SQL details or exception payload in task state.
        return tasks.finish(run_id, token=token, now=clock(), error_code='PARSE_FAILED')
