"""Failure-closure drill in a fresh formal process; no source or data rollback."""
import asyncio
from dataclasses import replace
import json
import os
from pathlib import Path
from unittest.mock import patch

import requests

from tools.data_security.network_guard import install
from data_security.tests.phase3_fixtures import configuration


def main():
    install()
    assert os.environ.get('DATA_SECURITY_ISOLATED_TEST') == '1'
    with configuration(('deepseek',)) as (path, config, refs, material, binding):
        os.environ['DATA_SECURITY_CONFIG'] = str(path)
        import django
        django.setup()
        from ai_providers import Message, get_manager
        from ai_providers.deepseek import DeepSeekProvider
        from ctf_backend.security_bootstrap import framework_startup
        from ctfsafe.encryption import encrypt_field, decrypt_field, EncryptionError
        from data_security.adapters.django.content import protect_text, ContentProtectionError
        from data_security.contracts import Environment, ObjectContext
        from data_security.tests.fixtures import examples
        from rest_framework.authentication import TokenAuthentication
        from rest_framework.views import APIView
        from challenges.views import proxy_challenge_view
        from django.contrib.auth.hashers import make_password, check_password
        from django.core.management import call_command
        import io

        context = replace(examples()[ObjectContext], environment=Environment.EVALUATION)
        envelope = encrypt_field('ordinary input', object_context=context)
        assert decrypt_field(envelope, object_context=context) == 'ordinary input'
        # Only test-owned files are removed: revoked references cannot reopen plaintext paths.
        (path.parent / 'data_key.key').unlink()
        Path(config['policy_file']).unlink()
        with patch.object(requests.Session, 'send') as send:
            try:
                asyncio.run(get_manager().get_provider('deepseek').chat([Message('user', 'ordinary input')]))
            except RuntimeError:
                pass
            else:
                raise AssertionError('MODEL_FAILURE_OPEN')
            try:
                protect_text('ordinary input')
            except ContentProtectionError:
                pass
            else:
                raise AssertionError('CONTENT_FAILURE_OPEN')
            send.assert_not_called()
        try:
            encrypt_field('ordinary input', object_context=context)
        except EncryptionError as error:
            assert str(error) == 'KEY_UNAVAILABLE'
        else:
            raise AssertionError('FIELD_FAILURE_OPEN')
        try:
            DeepSeekProvider()
        except RuntimeError:
            pass
        else:
            raise AssertionError('DIRECT_PROVIDER_OPEN')
        assert TokenAuthentication not in APIView.authentication_classes
        assert TokenAuthentication not in proxy_challenge_view.cls.authentication_classes
        assert framework_startup().encode() == material['framework_key']
        assert check_password('isolated-nonsecret-probe', make_password('isolated-nonsecret-probe'))
        output = io.StringIO()
        call_command('check', stdout=output, stderr=output)
        print(json.dumps({'formal_failure_closure': True, 'external_sends': 0,
            'content_and_field_fail_closed': True, 'legacy_provider_and_token_stay_disabled': True,
            'independent_framework_key_and_password_hashing_retained': True, 'django_check': True,
            'git_reset_or_reverse_patch': False, 'real_data_or_key_version_rollback': False,
            'unknown_delivery_or_quota_release': False, 'production_operations': False,
            'rollback_action': 'stop affected external sends and writes; retain encrypted formats and key references',
            'limitation': 'synthetic missing-policy/missing-data-key drill, not a production restore'}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
