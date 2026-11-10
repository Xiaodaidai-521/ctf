"""Fresh-process startup probes for unfinished private-upload ingress.

Uses isolated settings and repository-external synthetic configuration only.
No migrations, publication, private-file deletion or model-provider calls.
"""
import argparse
import asyncio
import json
import os
from unittest.mock import AsyncMock, patch

from tools.data_security.network_guard import install


def check(formal, owner):
    import django
    django.setup()
    from django.conf import settings
    from django.core.handlers.asgi import ASGIHandler
    from django.test import Client
    from django.urls import resolve, reverse
    from ctf_backend.asgi import application
    from data_security.adapters.django.private_ingress import ClosedPrivateUploadIngress

    middleware = 'ctf_backend.security_bootstrap.private_upload_middleware'
    if owner == 'feedback':
        from feedback_center.views import FeedbackAttachmentUploadView
        ticket = '00000000-0000-0000-0000-000000000001'
        path = reverse('feedback-upload-attachment', kwargs={'feedback_id': ticket})
        assert path == f'/api/feedback/{ticket}/attachments/'
        assert resolve(path).func.view_class is FeedbackAttachmentUploadView
    else:
        from resources.views import ResourceUploadView
        path = reverse('resources:upload')
        assert path == '/api/resources/upload/'
        assert resolve(path).func.view_class is ResourceUploadView
    if not formal:
        assert middleware not in settings.MIDDLEWARE
        assert isinstance(application, ASGIHandler)
        return {'formal': False, 'original_asgi_handler': True, 'closed_middleware_installed': False}

    assert settings.MIDDLEWARE[0] == middleware
    assert settings.MIDDLEWARE.count(middleware) == 1
    assert isinstance(application.__self__, ClosedPrivateUploadIngress)
    from rest_framework.authentication import SessionAuthentication
    from rest_framework.settings import api_settings
    from data_security.adapters.django.authentication import DisabledTokenAuthentication
    assert api_settings.DEFAULT_AUTHENTICATION_CLASSES == (SessionAuthentication, DisabledTokenAuthentication)
    client = Client(enforce_csrf_checks=True)
    with patch('django.http.request.HttpRequest.read', side_effect=AssertionError('HTTP body read')), \
         patch('django.core.files.uploadhandler.TemporaryUploadedFile', side_effect=AssertionError('upload spool')):
        for target in (path, path.rstrip('/')):
            response = client.post(target, b'synthetic private body', content_type='application/octet-stream')
            assert response.status_code == 503 and response.content == b''
            assert response['Cache-Control'] == 'no-store'

    async def asgi_checks():
        for prefix in ('', '/mounted'):
            for target in (path, path.rstrip('/')):
                receive = AsyncMock(side_effect=AssertionError('ASGI body received'))
                send = AsyncMock()
                await application({'type': 'http', 'method': 'POST', 'path': prefix + target,
                                   'root_path': prefix}, receive, send)
                receive.assert_not_awaited()
                assert [call.args[0]['type'] for call in send.await_args_list] == [
                    'http.response.start', 'http.response.body']
                assert send.await_args_list[0].args[0]['status'] == 503
                assert send.await_args_list[1].args[0]['body'] == b''

    with patch('django.core.handlers.asgi.tempfile.SpooledTemporaryFile',
               side_effect=AssertionError('pre-middleware disk spool')):
        asyncio.run(asgi_checks())
    return {'formal': True, 'real_start_application': True, 'original_route_resolved': True,
            'wsgi_denials': 2, 'asgi_denials': 4, 'body_consumed': False,
            'private_upload_enabled': False, 'production_authorization': False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('formal', 'unbound'))
    parser.add_argument('--owner', choices=('resources', 'feedback'), default='resources')
    args = parser.parse_args()
    install()
    assert os.environ['DJANGO_SETTINGS_MODULE'] == 'tools.data_security.test_settings'
    assert 'DATA_SECURITY_CONFIG' not in os.environ
    if args.mode == 'formal':
        from data_security.tests.phase3_fixtures import configuration
        with configuration(providers=()) as files:
            os.environ['DATA_SECURITY_CONFIG'] = str(files[0])
            result = check(True, args.owner)
    else:
        result = check(False, args.owner)
    print(json.dumps({'owner': args.owner, **result}, sort_keys=True))


if __name__ == '__main__':
    main()
