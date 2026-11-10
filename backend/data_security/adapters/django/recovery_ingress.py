"""Deployment-wide recovery closure. B supplies admission; no restore or filesystem I/O here."""
from django.http import HttpResponse


_admission = None
_BODY = b'{"code":"SOURCE_NOT_APPROVED"}'


def bind_recovery_admission(admission=None):
    global _admission
    _admission = admission


def recovery_middleware(get_response):
    if _admission is None:
        return get_response

    def handle(request):
        # The outer ASGI gate has already checked this request before receiving its body.
        checked = getattr(request, 'scope', {}).get('data_security.recovery_checked', False)
        if not checked and _admission is not None and _admission() is not True:
            return HttpResponse(_BODY, status=503, content_type='application/json',
                headers={'Cache-Control': 'no-store'})
        return get_response(request)
    return handle


def guard_recovery_asgi(application):
    if _admission is None:
        return application

    async def handle(scope, receive, send):
        if scope['type'] in ('http', 'websocket') and _admission is not None:
            if _admission() is not True:
                if scope['type'] == 'websocket':
                    await send({'type': 'websocket.close', 'code': 1013})
                else:
                    await send({'type': 'http.response.start', 'status': 503, 'headers': [
                        (b'content-type', b'application/json'), (b'cache-control', b'no-store')]})
                    await send({'type': 'http.response.body', 'body': _BODY})
                return
            scope = {**scope, 'data_security.recovery_checked': True}
        await application(scope, receive, send)
    return handle
