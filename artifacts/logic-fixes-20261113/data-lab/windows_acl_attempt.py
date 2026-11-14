"""Try real owner-only Windows ACLs on the 44 blocked synthetic fixtures.

Application permission checks and assertions remain intact. This is a test-only
fixture adapter; it never touches production configuration or key material.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
from contextlib import contextmanager
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
LABEL = sys.argv[sys.argv.index('--label') + 1] if '--label' in sys.argv else 'windows-acl'
sys.path[:0] = [str(ROOT), str(ROOT / 'backend')]


def entry():
    import django
    django.setup()
    from data_security.adapters.private_permissions import is_private_path
    from data_security.runtime.crypto import restrict_path
    from feedback_center.tests import test_phase6_private_uploads as fixtures
    from resources import test_phase6_private_uploads as resource_fixtures
    original = fixtures.configuration
    observations = []
    active_roots = {}
    original_mkdir = Path.mkdir

    def native_mkdir(path, mode=0o777, parents=False, exist_ok=False):
        original_mkdir(path, mode=mode, parents=parents, exist_ok=exist_ok)
        resolved = path.resolve()
        if mode == 0o700:
            for root, observation in active_roots.items():
                if resolved.is_relative_to(root):
                    restrict_path(resolved, directory=True)
                    observation['requested_private_subdirectories'].append({
                        'name': path.name, 'native_private': is_private_path(resolved, directory=True),
                        'posix_mode': oct(resolved.stat().st_mode & 0o777),
                    })

    @contextmanager
    def private_configuration(*args, **kwargs):
        with original(*args, **kwargs) as values:
            source, config, refs, keys, binding = values
            source = source.resolve()
            directory = source.parent
            # Correct the test fixture's drive-relative /tmp paths as well as
            # the actual NTFS ACLs. No permission predicate is patched.
            for field in ('key_manifest', 'policy_file'):
                config[field] = str(Path(config[field]).resolve())
            source.write_text(json.dumps(config), encoding='utf-8')
            restrict_path(directory, directory=True)
            for path in directory.iterdir():
                restrict_path(path, directory=path.is_dir())
            observation = {
                'directory_native_private': is_private_path(directory, directory=True),
                'configuration_native_private': is_private_path(source),
                'key_native_private': is_private_path(directory / 'data_key.key'),
                'manifest_native_private': is_private_path(directory / 'manifest.json'),
                'configuration_absolute': source.is_absolute(),
                'configuration_posix_mode': oct(source.stat().st_mode & 0o777),
                'bootstrap_posix_group_other_write_bits': oct(source.stat().st_mode & 0o022),
                'business_permission_checks_unchanged': True,
                'requested_private_subdirectories': [],
            }
            observations.append(observation)
            active_roots[directory] = observation
            try:
                yield source, config, refs, keys, binding
            finally:
                active_roots.pop(directory, None)

    fixtures.configuration = private_configuration
    resource_fixtures.configuration = private_configuration
    data = json.loads((ROOT / 'artifacts/full-audit-20261113/logic-fix-data-lab-joint.json').read_text())
    selected = data['errors']
    if '--resource-fixtures-only' in sys.argv:
        selected = [item for item in selected if 'resources' in item['traceback']]
        assert len(selected) == 15
    targets = [item['id'] for item in selected]
    assert len(targets) in (15, 44) and all(name.startswith('feedback_center.') for name in targets)
    from django.test.utils import get_runner
    from django.conf import settings
    try:
        with patch.object(Path, 'mkdir', native_mkdir):
            failures = get_runner(settings)(verbosity=1, interactive=False).run_tests(targets)
    finally:
        (OUT / (LABEL + '-observations.json')).write_text(
            json.dumps({'native_acl_attempted': True, 'business_checks_unchanged': True,
                        'fixture_attempts': observations}, indent=2), encoding='utf-8')
    raise SystemExit(bool(failures))


if '--entry' in sys.argv:
    entry()
else:
    from tools.full_audit.run import clean_env, config_and_identity
    config = config_and_identity()
    env = clean_env()
    env.update(FULL_AUDIT_LEGACY='1', FULL_AUDIT_TEST_DB='test_logic_fix_' + LABEL.replace('-', '_'),
               FULL_AUDIT_RESULT=str(OUT / (LABEL + '-tests.json')),
               MAINLINE1_TEST_PORT=str(config['port']))
    with (OUT / (LABEL + '-tests.log')).open('w', encoding='utf-8') as output:
        extra = ['--resource-fixtures-only'] if '--resource-fixtures-only' in sys.argv else []
        result = subprocess.run([sys.executable, '-B', str(Path(__file__).resolve()), '--entry', '--label', LABEL, *extra],
            env=env, cwd=ROOT / 'backend', stdout=output, stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW)
    print(json.dumps({'synthetic_only': True, 'exit_code': result.returncode,
                      'log': str(OUT / (LABEL + '-tests.log'))}))
    raise SystemExit(result.returncode)
