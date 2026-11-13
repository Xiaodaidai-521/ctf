"""Bounded memory uploads: private plaintext never spills to Django temp files."""
from django.conf import settings
from django.core.exceptions import RequestDataTooBig
from django.core.files.uploadhandler import MemoryFileUploadHandler


class PrivateMemoryUploadHandler(MemoryFileUploadHandler):
    def handle_raw_input(self, input_data, META, content_length, boundary, encoding=None):
        self.activated = True
        self._received = 0
        self._limit = settings.DATA_PROTECTION_MAX_UPLOAD_BYTES
        if content_length is not None and content_length > self._limit:
            raise RequestDataTooBig('The upload exceeds the configured size limit.')

    def receive_data_chunk(self, raw_data, start):
        self._received += len(raw_data)
        if self._received > self._limit:
            # Abort the whole request, including earlier completed files. A
            # StopUpload here would return a partially parsed multipart request.
            raise RequestDataTooBig('The upload exceeds the configured size limit.')
        return super().receive_data_chunk(raw_data, start)
