"""Prove old application wiring does not require the not-yet-connected M0 package."""
import importlib.abc
import io
import json
import os
from pathlib import Path
import sys


class DisconnectedSecurity(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'data_security' or fullname.startswith('data_security.'):
            raise ModuleNotFoundError('PHASE1_CONTRACT_DISCONNECTED', name=fullname)
        return None


def main():
    root = Path(__file__).resolve().parents[2]
    if root != Path('/home/hatch/workspace/ctf-data-security') or Path.cwd() != root:
        raise RuntimeError('ISOLATED_WORKTREE_REQUIRED')
    if os.environ.get('DATA_SECURITY_ISOLATED_TEST') != '1':
        raise RuntimeError('ISOLATED_TEST_OPT_IN_REQUIRED')
    if any(name == 'data_security' or name.startswith('data_security.') for name in sys.modules):
        raise RuntimeError('PROBE_REQUIRES_FRESH_PROCESS')
    sys.meta_path.insert(0, DisconnectedSecurity())
    try:
        __import__('data_security.contracts')
    except ModuleNotFoundError as error:
        if error.name != 'data_security':
            raise
    else:
        raise RuntimeError('DISCONNECTION_NOT_ACTIVE')

    import django
    django.setup()
    from django.conf import settings
    from django.core.management import call_command
    from django.urls import URLPattern, URLResolver, get_resolver

    output = io.StringIO()
    call_command('check', stdout=output, stderr=output)
    forbidden_domains = {'data_security', 'mainline1', 'controlled_export', 'export_risk', 'export_quota'}

    def verify_routes(patterns):
        checked = 0
        for pattern in patterns:
            if isinstance(pattern, URLResolver):
                checked += verify_routes(pattern.url_patterns)
            elif isinstance(pattern, URLPattern):
                callback = pattern.callback
                view = getattr(callback, 'cls', getattr(callback, 'view_class', callback))
                if view.__module__.split('.')[0] in forbidden_domains:
                    raise RuntimeError('UNEXPECTED_PUBLIC_ROUTE')
                checked += 1
        return checked

    routes = verify_routes(get_resolver().url_patterns)
    expected = {'django.contrib.sessions.middleware.SessionMiddleware',
                'django.middleware.csrf.CsrfViewMiddleware',
                'django.contrib.auth.middleware.AuthenticationMiddleware'}
    if not expected.issubset(settings.MIDDLEWARE):
        raise RuntimeError('BASELINE_MIDDLEWARE_MISSING')
    from django.contrib.auth.hashers import check_password, make_password
    if not check_password('isolated-nonsecret-password-probe', make_password('isolated-nonsecret-password-probe')):
        raise RuntimeError('BASELINE_HASHING_UNAVAILABLE')
    assert not any(name == 'data_security' or name.startswith('data_security.') for name in sys.modules)
    print(json.dumps({'contracts_disconnected_in_probe': True, 'django_check_passed': True,
                      'routes_checked': routes, 'new_public_routes': 0, 'baseline_auth_middleware_retained': True,
                      'baseline_password_hashing_passed': True, 'files_moved_or_deleted': 0,
                      'production_data_changes': 0, 'full_regression_status': 'blocked; not substituted by this probe'}))


if __name__ == '__main__':
    main()
