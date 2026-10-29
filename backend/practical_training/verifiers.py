"""Fixed, bounded server verifiers. No arbitrary code, URL or model execution."""

import json

import requests


class VerifierUnavailable(ValueError):
    pass


def observe_challenge(endpoint, challenge_key):
    try:
        with requests.Session() as session:
            session.trust_env = False
            with session.get(f'{endpoint}/api/Challenges', timeout=(2, 5),
                             allow_redirects=False, stream=True) as response:
                if response.status_code != 200:
                    raise VerifierUnavailable('upstream_status')
                body = bytearray()
                for chunk in response.iter_content(chunk_size=8192):
                    body.extend(chunk)
                    if len(body) > 1024 * 1024:
                        raise VerifierUnavailable('upstream_too_large')
        payload = json.loads(body)
        if not isinstance(payload, dict) or not isinstance(payload.get('data'), list):
            raise VerifierUnavailable('upstream_schema')
        matches = [item for item in payload['data'] if isinstance(item, dict) and item.get('key') == challenge_key]
        if len(matches) != 1 or type(matches[0].get('solved')) is not bool:
            raise VerifierUnavailable('challenge_state_missing')
        return {'challenge_key': challenge_key, 'solved': matches[0]['solved']}
    except (requests.RequestException, ValueError, TypeError) as exc:
        if isinstance(exc, VerifierUnavailable):
            raise
        raise VerifierUnavailable('upstream_unavailable') from exc


def policy_allows(policy, principal, resource):
    """Execute the student's declarative proposal against synthetic identities."""
    rule = policy['rules'].get(resource['visibility'], policy['default'])
    if rule in ('allow', 'public'):
        return True
    if rule == 'deny' or principal is None:
        return False
    same_tenant = principal['tenant'] == resource['tenant']
    if rule == 'tenant':
        return same_tenant
    return same_tenant and principal['id'] == resource['owner']


def verify_policy(policy):
    # Independent expected decisions, including positive controls: deny-all is not a fix.
    principals = [None, {'id': 'owner', 'tenant': 'alpha'}, {'id': 'peer', 'tenant': 'alpha'},
                  {'id': 'owner', 'tenant': 'beta'}, {'id': 'outsider', 'tenant': 'beta'}]
    expected = {
        'public': [True, True, True, True, True],
        'internal': [False, True, True, False, False],
        'private': [False, True, False, False, False],
        'unknown': [False, False, False, False, False],
    }
    cases = []
    for visibility, decisions in expected.items():
        resource = {'visibility': visibility, 'tenant': 'alpha', 'owner': 'owner'}
        for index, (principal, decision) in enumerate(zip(principals, decisions)):
            actual = policy_allows(policy, principal, resource)
            cases.append({'id': f'{visibility}-{index}', 'passed': actual == decision})
    return {'suite': 'synthetic-document-acl-v1', 'passed': all(case['passed'] for case in cases), 'cases': cases}
