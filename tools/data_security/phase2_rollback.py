"""Disconnect phase-2 implementations in memory; retain accepted M0 and guards."""
import importlib.abc
import io
import json
import os
from pathlib import Path
import subprocess
import sys


class DisconnectedCore(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('data_security.core', 'data_security.application')) or fullname == 'ctf_backend.security_bootstrap':
            raise ModuleNotFoundError('PHASE2_IMPLEMENTATION_DISCONNECTED', name=fullname)
        return None


def main():
    root = Path(__file__).resolve().parents[2]
    assert Path.cwd() == root == Path('/home/hatch/workspace/ctf-data-security')
    assert os.environ.get('DATA_SECURITY_ISOLATED_TEST') == '1'
    assert not any(n.startswith('data_security') for n in sys.modules)
    sys.meta_path.insert(0, DisconnectedCore())
    try:
        __import__('data_security.core.redaction')
    except ModuleNotFoundError as error:
        assert error.name.startswith('data_security.core')
    else:
        raise AssertionError('DISCONNECTION_NOT_ACTIVE')
    from data_security.contracts import CONTRACT_TYPES, PORT_TYPES
    assert (len(CONTRACT_TYPES), len(PORT_TYPES)) == (39, 19)
    import django
    django.setup()
    from django.core.management import call_command
    from django.conf import settings
    from django.urls import URLPattern, URLResolver, get_resolver
    output = io.StringIO()
    call_command('check', stdout=output, stderr=output)
    forbidden = {'data_security', 'mainline1', 'controlled_export', 'export_risk', 'export_quota'}
    def routes(patterns):
        count = 0
        for pattern in patterns:
            if isinstance(pattern, URLResolver):
                count += routes(pattern.url_patterns)
            elif isinstance(pattern, URLPattern):
                view = getattr(pattern.callback, 'cls', getattr(pattern.callback, 'view_class', pattern.callback))
                assert view.__module__.split('.')[0] not in forbidden
                count += 1
        return count
    count = routes(get_resolver().url_patterns)
    assert {'django.contrib.sessions.middleware.SessionMiddleware', 'django.middleware.csrf.CsrfViewMiddleware',
            'django.contrib.auth.middleware.AuthenticationMiddleware'}.issubset(settings.MIDDLEWARE)
    from django.contrib.auth.hashers import make_password, check_password
    assert check_password('isolated-nonsecret-probe', make_password('isolated-nonsecret-probe'))
    from ai_assistant.security import OutputSanitizer
    from legal.services.fact_redactor import redact_manual_notes
    from mainline1.rules import candidates
    from mainline1.parsing import InputError
    from data_security.adapters.django import legacy
    assert legacy._confidentiality is None
    assert OutputSanitizer().sanitize('ordinary input') == ('ordinary input', [])
    assert OutputSanitizer().sanitize('connect 10.0.0.1.') == (
        'connect [内网地址 已过滤].', ['检测到内网IP段 10.x.x.x，已过滤'])
    assert redact_manual_notes('ordinary input') == 'ordinary input'
    assert redact_manual_notes('token=fixture flag{fixture}') == 'token=[REDACTED] flag{[REDACTED]}'
    try:
        tuple(candidates('email_ascii_v1', 'a@example.invalid'))
    except InputError:
        pass
    else:
        raise AssertionError('LEGACY_FALLBACK_OPEN')
    baseline = '2970a4cb18103b8de4ac7f04a4ea1aa6322b5989'
    protected = ['backend/data_security/contracts', 'backend/ctfsafe/encryption.py',
        'backend/challenges/access.py', 'backend/challenges/views.py',
        'backend/feedback_center/services/submission.py',
        'tasks/controlled-export-execution/controlled_export/services.py']
    assert subprocess.run(['git', 'diff', '--quiet', baseline, '--', *protected], cwd=root).returncode == 0
    changed = ['backend/mainline1/rules.py', 'backend/ai_assistant/security.py', 'backend/legal/services/fact_redactor.py']
    patch = subprocess.check_output(['git', 'diff', baseline, '--', *changed], cwd=root)
    assert subprocess.run(['git', 'apply', '--reverse', '--check', '-'], input=patch, cwd=root,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode == 0
    assert not any(n.startswith(('data_security.core', 'data_security.application')) for n in sys.modules)
    print(json.dumps({'phase2_core_disconnected': True, 'm0_retained': [39, 19], 'django_check': True,
        'routes_checked': count, 'new_public_routes': 0, 'auth_middleware_and_hashing': True,
        'unbound_output_legal_baseline_retained': True, 'unbound_candidates_fail_closed': True,
        'accepted_baseline_security_sources_unchanged': True,
        'reverse_patch_check': True, 'reverse_patch_applied': False,
        'files_deleted_or_moved': 0, 'data_format_or_key_rollback': False,
        'unknown_delivery_or_quota_release': False, 'production_operations': False,
        'limitation': 'in-memory disconnection plus code reversibility check; not a production restore'}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
