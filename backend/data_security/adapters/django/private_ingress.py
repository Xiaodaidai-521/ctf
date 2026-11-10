"""Explicitly closed or opt-in private uploads, before request-body consumers."""
from io import BytesIO

from django.core.exceptions import RequestAborted, RequestDataTooBig
from django.core.handlers.asgi import ASGIHandler, get_script_prefix
from django.http import HttpResponse

from data_security.adapters.django.uploads import PrivateUploadBoundary
from data_security.contracts import Limits


class ClosedPrivateUploadIngress:
    def __init__(self, application, *, paths, patterns=()):
        self.application, self.paths, self.patterns = application, paths, patterns

    def __call__(self, request):
        if request.path_info in self.paths or any(pattern.fullmatch(request.path_info) for pattern in self.patterns):
            return HttpResponse(status=503, headers={'Cache-Control': 'no-store'})
        return self.application(request)

    async def asgi(self, scope, receive, send):
        if scope['type'] == 'http':
            # Match Django's path_info, including mounted/FORCE_SCRIPT_NAME apps.
            path = scope['path'].removeprefix(get_script_prefix(scope))
            if path in self.paths or any(pattern.fullmatch(path) for pattern in self.patterns):
                await send({'type': 'http.response.start', 'status': 503,
                            'headers': [(b'cache-control', b'no-store'), (b'content-length', b'0')]})
                await send({'type': 'http.response.body', 'body': b''})
                return
        await self.application(scope, receive, send)


class _MemoryUploadASGIHandler(ASGIHandler):
    def __init__(self, *, limits: Limits):
        # The byte budget includes text, boundaries and multipart metadata too.
        self.max_body_bytes = limits.max_bytes * limits.max_inflight_objects + limits.max_text_chars
        super().__init__()

    async def read_body(self, receive):
        body_file = BytesIO()
        try:
            while True:
                message = await receive()
                if message['type'] == 'http.disconnect':
                    raise RequestAborted()
                body = message.get('body', b'')
                if body_file.tell() + len(body) > self.max_body_bytes:
                    raise RequestDataTooBig('上传请求超过大小限制。')
                body_file.write(body)
                if not message.get('more_body', False):
                    break
            body_file.seek(0)
            # Django's handle() owns and closes a successfully received body.
            return body_file
        except BaseException:
            # Includes interrupted receive and cancellation, not only size errors.
            body_file.close()
            raise


class OpenPrivateUploadIngress:
    """B explicitly installs both entry points with the same paths and limits.

    __call__ is the first request middleware on both WSGI and ASGI. asgi wraps
    the Django ASGI application and replaces its handler on selected paths only;
    that handler loads the configured middleware, including this request boundary.
    No proxy buffering, swap protection or authorization is provided here.
    """
    def __init__(self, application, *, paths, patterns=(), limits: Limits):
        self.application, self.paths, self.patterns = application, paths, patterns
        self.limits = limits
        self._boundary = PrivateUploadBoundary(application, limits=limits)
        self._asgi_handler = None

    def __call__(self, request):
        if request.path_info in self.paths or any(pattern.fullmatch(request.path_info) for pattern in self.patterns):
            return self._boundary(request)
        return self.application(request)

    async def asgi(self, scope, receive, send):
        if scope['type'] == 'http':
            path = scope['path'].removeprefix(get_script_prefix(scope))
            if path in self.paths or any(pattern.fullmatch(path) for pattern in self.patterns):
                # Lazy construction avoids loading middleware recursively when
                # this class is itself being installed as request middleware.
                if self._asgi_handler is None:
                    self._asgi_handler = _MemoryUploadASGIHandler(limits=self.limits)
                try:
                    await self._asgi_handler(scope, receive, send)
                except RequestDataTooBig:
                    await send({'type': 'http.response.start', 'status': 413,
                                'headers': [(b'cache-control', b'no-store'), (b'content-length', b'0')]})
                    await send({'type': 'http.response.body', 'body': b''})
                return
        await self.application(scope, receive, send)
