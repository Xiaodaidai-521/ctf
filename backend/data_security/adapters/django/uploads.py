"""Explicit, request-scoped multipart memory boundary; never a disk fallback.

Install before anything reads POST/FILES. This does not protect an ASGI server's
pre-middleware body spool, provide swap protection, or authorize file storage.
"""
from io import BytesIO

from django.core.exceptions import RequestDataTooBig, TooManyFilesSent
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.core.files.uploadhandler import FileUploadHandler, StopFutureHandlers
from django.http.multipartparser import MultiPartParserError

from data_security.contracts import Limits, ReasonCode
from data_security.contracts.schema import require


class BoundedUploadHandler(FileUploadHandler):
    def __init__(self, request, *, limits: Limits):
        super().__init__(request)
        require(type(limits) is Limits, ReasonCode.INVALID_TYPE)
        self.limits = limits
        self.buffers = []

    def new_file(self, *args, **kwargs):
        super().new_file(*args, **kwargs)
        # Completed parts still occupy memory until the view finishes.
        if len(self.buffers) >= self.limits.max_inflight_objects:
            raise TooManyFilesSent('同时处理的文件过多。')
        self.file = BytesIO()
        self.buffers.append(self.file)
        self.size = 0
        raise StopFutureHandlers()

    def receive_data_chunk(self, raw_data, start):
        size = self.size + len(raw_data)
        if size > self.limits.max_bytes:
            raise RequestDataTooBig('上传文件超过大小限制。')
        self.file.write(raw_data)
        self.size = size

    def file_complete(self, file_size):
        self.file.seek(0)
        return InMemoryUploadedFile(self.file, self.field_name, self.file_name,
            self.content_type, self.size, self.charset, self.content_type_extra)

    def upload_interrupted(self):
        raise MultiPartParserError('文件上传未完成。')

    def close(self):
        for buffer in self.buffers:
            buffer.close()


class PrivateUploadBoundary:
    """B must inject limits and install this before request-body consumers.

    The view consumes uploads synchronously before returning. A returned upload
    is not a streaming response or a durable/private object reference.
    """
    def __init__(self, get_response, *, limits: Limits):
        self.get_response, self.limits = get_response, limits

    def __call__(self, request):
        handler = BoundedUploadHandler(request, limits=self.limits)
        request.upload_handlers = [handler]
        try:
            return self.get_response(request)
        finally:
            # Django closes completed parts on parser errors, not the active one.
            handler.close()
