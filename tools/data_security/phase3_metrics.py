"""Frozen synthetic corpus through formal file policy/keys and final-send captures."""
from dataclasses import replace
import json
from unittest.mock import patch

import requests

from data_security.contracts import AIResponse, Category, EmbeddingResult, Outlet, canonical_bytes
from data_security.tests.synthetic import samples, dataset_fingerprint
from data_security.tests.test_phase3_official import OfficialTests, ENDPOINTS
from tools.data_security.network_guard import install
from tools.data_security.phase2_metrics import ratio


def main():
    install()
    dataset = samples()
    rows, issues = [], []
    for endpoint, embedding in [(name, False) for name in ENDPOINTS] + [('qwen', True), ('volcano', True)]:
        fixture = OfficialTests()
        fixture.setUp()
        current, captured = None, None

        def send(session, prepared, **kwargs):
            nonlocal captured
            response = requests.Response()
            response.status_code = 200
            if '/oauth/' in prepared.url:
                result = {'access_token': 'synthetic-metrics-oauth'}
            else:
                body = json.loads(prepared.body)
                if embedding:
                    captured = body['input'][0]
                    result = {'data': [{'index': 0, 'embedding': [0.1, 0.2]}]}
                else:
                    captured = body['messages'][0]['content']
                    result = ({'result': current.text} if endpoint == 'wenxin' else
                              {'choices': [{'message': {'content': current.text}}]})
            response._content = json.dumps(result).encode()
            response._content_consumed = True
            return response

        class Socket:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def send(self, value):
                nonlocal captured
                captured = json.loads(value)['payload']['message']['text'][0]['content']
            def recv(self, **kwargs):
                return json.dumps({'header': {'code': 0}, 'payload': {'choices':
                    {'text': [{'content': current.text}], 'status': 2}}})

        counts = {family: dict(positive=0, negative=0, protected=0, false_positive=0,
                              leaked=0, failed=0, response_leaked=0)
                  for family in (*(category.value for category in Category), 'teaching-source')}
        try:
            adapter = fixture.adapter(endpoint)
            with patch.object(requests.Session, 'send', autospec=True, side_effect=send), \
                 patch('data_security.adapters.llm.official.connect', return_value=Socket()):
                for current in dataset:
                    # The frozen fourth family is retained, but automatic credential
                    # detection is explicitly outside the approved three categories.
                    if current.category is Category.SECRET:
                        continue
                    family = 'teaching-source' if current.teaching else current.category.value
                    row = counts[family]
                    row['positive' if current.positive else 'negative'] += 1
                    captured = None
                    before = len(fixture.audit.events)
                    request = fixture.request(endpoint, {'input': [current.text]} if embedding else
                        {'messages': [{'role': 'user', 'content': current.text}]}, embedding=embedding)
                    context = replace(fixture.context, outlet=Outlet.EMBEDDING) if embedding else fixture.context
                    result = (adapter.embed if embedding else adapter.chat)(request, context, fixture.binding)
                    if not isinstance(result, EmbeddingResult if embedding else AIResponse) or captured is None:
                        row['failed'] += 1
                        issues.append(endpoint + ':' + family + ':request-failed')
                        continue
                    # No corpus values leave memory. Compare only the known synthetic sensitive span.
                    sensitive = current.text.split('=', 1)[1] if current.category is Category.SECRET and current.positive else current.text.split()[-1]
                    audit_surface = ''.join(canonical_bytes(event).decode() for event in fixture.audit.events[before:])
                    if current.positive:
                        row['protected'] += sensitive not in captured
                        row['leaked'] += sensitive in captured or sensitive in audit_surface
                        if not embedding:
                            row['response_leaked'] += sensitive in result.content.text
                    else:
                        row['false_positive'] += captured != current.text
        finally:
            fixture.doCleanups()
        for family, count in counts.items():
            if family == Category.SECRET.value:
                rows.append({'endpoint': endpoint, 'outlet': 'embedding' if embedding else 'model',
                    'family': family, 'dataset_rows_retained': 100, 'not_applicable': 100,
                    'automatic_detector': False, 'protection_recall': ratio(0, 0, 'automatic fourth category prohibited'),
                    'forbidden_original_exposures': None,
                    'scope': 'known credential values/fields and legacy matched shapes tested separately'})
                continue
            if count['failed'] or count['leaked'] or count['response_leaked'] or count['false_positive']:
                issues.append(endpoint + ':' + family + ':metric')
            rows.append({'endpoint': endpoint, 'outlet': 'embedding' if embedding else 'model', 'family': family,
                'protection_recall': ratio(count['protected'], count['positive']),
                'false_positive': ratio(count['false_positive'], count['negative'], 'no negative teaching rows'),
                'forbidden_original_exposures': count['leaked'], 'api_response_exposures': count['response_leaked'],
                'coverage': {'total': count['positive'] + count['negative'],
                             'processed': count['positive'] + count['negative'] - count['failed'],
                             'failed': count['failed'], 'excluded': 0, 'unknown': 0, 'unscanned': 0},
                'automatic_detector': family not in ('secret_credential', 'teaching-source')})
    print(json.dumps({'version': 'ds.phase3.metrics.v1', 'dataset_count': len(dataset),
        'dataset_sha256': dataset_fingerprint(), 'teaching_exceptions': 0,
        'approved_teaching_damage': ratio(0, 0, 'no approved teaching exception in phase 3'),
        'measurements': rows, 'real_provider_calls': 0, 'payloads_persisted': False,
        'scope': 'file policy/keys, M4 and M7 final-send captures; test audit sink, not PostgreSQL B integration',
        'enabled_capture_coverage': {'model': ratio(6, 6), 'embedding': ratio(2, 2), 'api_response': ratio(6, 6)},
        'other_outlets': {'log': 'separate allowlist tests', 'audit': 'separate PostgreSQL receipt tests',
                          'export': 'disabled', 'rag': 'full pipeline deferred; embedding included'},
        'production_coverage': ratio(0, 0, 'not authorized or measured'), 'issues': issues}, indent=2))
    return int(bool(issues))


if __name__ == '__main__':
    raise SystemExit(main())
