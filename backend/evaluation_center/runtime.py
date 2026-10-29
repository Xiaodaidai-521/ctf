"""Allowlisted reads from module two. No tutoring or context-creation calls."""

from collections import defaultdict
from math import ceil

from django.db.models import Prefetch
from teaching_agent.models import TeachingRun, TutorRequest

from .metrics import metric
from .provenance import excluded_student_ids


def runtime_summary(*, student_id=None, task_key=None, catalog_version=None,
                    knowledge_point_id=None, start=None, end=None):
    runs = TeachingRun.objects.select_related('attempt__task').exclude(
        student_id__in=excluded_student_ids(),
    ).filter(student__role='student')
    if student_id:
        runs = runs.filter(student_id=student_id)
    if task_key:
        runs = runs.filter(attempt__task__task_key=task_key)
    if catalog_version:
        runs = runs.filter(catalog_version=catalog_version)
    if knowledge_point_id:
        runs = runs.filter(attempt__task__capabilities__knowledge_points__stable_id=knowledge_point_id).distinct()
    requests = TutorRequest.objects.prefetch_related('model_calls')
    if start:
        requests = requests.filter(created_at__gte=start)
    if end:
        requests = requests.filter(created_at__lt=end)
    runs = runs.prefetch_related(Prefetch('requests', queryset=requests, to_attr='window_requests'))
    window = {'start': start.isoformat() if start else None, 'end': end.isoformat() if end else None}
    groups, records = defaultdict(list), []
    for run in runs:
        if not run.window_requests and ((start and run.created_at < start) or (end and run.created_at >= end)):
            continue
        versions = {'task_key': run.attempt.task.task_key, 'task_version': run.task_version,
                    'catalog_version': run.catalog_version, 'mode': run.mode}
        groups[tuple(versions.values())].extend(run.window_requests)
        records.append({
            'run_id': str(run.run_id), 'attempt_id': str(run.attempt.attempt_id),
            'student_id': run.student_id, 'state': run.state, 'versions': versions,
            'created_at': run.created_at.isoformat(),
            'requests': [{
                'request_id': request.request_id, 'status': request.status,
                'late_response_discarded': request.late_response_discarded,
                'calls': [{
                    'call_id': call.call_id, 'provider': call.provider, 'model': call.model,
                    'template_version': call.template_version, 'status': call.status,
                    'error_category': call.error_category, 'latency_ms': call.latency_ms,
                    'input_tokens': call.input_tokens, 'output_tokens': call.output_tokens,
                    'retry_count': call.retry_count,
                    'cost_amount': str(call.cost_amount) if call.cost_amount is not None else None,
                    'cost_currency': call.cost_currency or None, 'price_version': call.cost_basis,
                } for call in request.model_calls.all()],
            } for request in run.window_requests],
        })
    summaries = []
    for key, batch in sorted(groups.items()):
        versions = dict(zip(('task_key', 'task_version', 'catalog_version', 'mode'), key))
        calls = [call for request in batch for call in request.model_calls.all()]

        def measure(numerator, denominator, missing=0):
            return metric(numerator, denominator, missing, window=window, versions=versions)

        latency = sorted(call.latency_ms for call in calls if call.latency_ms is not None)
        percentiles = {}
        for name, fraction in [('p50_ms', .5), ('p95_ms', .95)]:
            envelope = measure(len(latency), len(calls), len(calls) - len(latency))
            envelope.update(value=latency[max(0, ceil(len(latency) * fraction) - 1)] if latency else None,
                            statistic=name, counts_describe='latency_observation_coverage')
            percentiles[name] = envelope
        currencies = defaultdict(list)
        for call in calls:
            currencies[(call.cost_currency or 'unknown', call.cost_basis or 'unknown')].append(call)
        costs = []
        for (currency, price_version), entries in sorted(currencies.items()):
            known = [float(call.cost_amount) for call in entries if call.cost_amount is not None]
            missing = len(entries) - len(known)
            total = None if missing or currency == 'unknown' else sum(known)
            costs.append({'currency': currency, 'price_version': price_version,
                          'total': measure(total, 1 if entries else 0, missing),
                          'coverage': measure(len(known), len(entries), missing)})
        summaries.append({'versions': versions, 'metrics': {
            'ai_request_success': measure(sum(r.status == 'succeeded' for r in batch), len(batch),
                                          sum(r.status == 'pending' for r in batch)),
            'degraded_requests': measure(sum(r.status == 'degraded' for r in batch), len(batch)),
            'model_call_success': measure(sum(c.status == 'succeeded' for c in calls), len(calls),
                                          sum(c.status == 'pending' for c in calls)),
            'call_count': measure(len(calls), len(batch)),
            'retries': measure(sum(c.retry_count for c in calls), len(calls)),
            'input_tokens': measure(sum(c.input_tokens for c in calls) if calls and all(c.input_tokens is not None for c in calls) else None,
                                    len(calls), sum(c.input_tokens is None for c in calls)),
            **percentiles,
        }, 'costs': costs})
    return {'source': 'formal', 'status': 'available' if records else 'no_data',
            'window': window, 'records': records, 'version_groups': summaries,
            'legacy_ai_assistant': 'partial_summary_only_not_a_call_ledger',
            'tool_execution': 'not_connected'}
