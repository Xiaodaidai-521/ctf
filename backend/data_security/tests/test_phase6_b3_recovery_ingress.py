"""Recovery admission before body reception; no database, restore or real network."""
import asyncio
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import AsyncMock, Mock

from data_security.adapters.django.recovery_ingress import (
    bind_recovery_admission, guard_recovery_asgi, recovery_middleware,
)
from data_security.contracts import ProtectionError, ReasonCode


class RecoveryIngressTests(TestCase):
    def setUp(self):
        self.addCleanup(bind_recovery_admission)
        self.denied = ProtectionError(schema_version=ProtectionError.SCHEMA,
            code=ReasonCode.SOURCE_NOT_APPROVED, retryable=False, trace_id='recovery/closed')

    def test_closed_asgi_blocks_all_http_paths_without_receiving_body_or_calling_django(self):
        admission = Mock(return_value=self.denied)
        bind_recovery_admission(admission)
        app, receive, send = AsyncMock(), AsyncMock(), AsyncMock()
        for path in ('/api/resources/upload/', '/api/data-security/files/shares/id/',
                     '/api/data-security/exports/recovery/reconcile/', '/api/users/'):
            asyncio.run(guard_recovery_asgi(app)({'type': 'http', 'path': path}, receive, send))
            self.assertEqual(send.call_args_list[-2].args[0]['status'], 503)
        receive.assert_not_called()
        app.assert_not_called()
        self.assertEqual(admission.call_count, 4)

    def test_asgi_admission_is_checked_once_and_is_not_cached_between_requests(self):
        admission = Mock(side_effect=[True, self.denied])
        bind_recovery_admission(admission)
        downstream = Mock(return_value='application-response')
        middleware = recovery_middleware(downstream)

        async def app(scope, receive, send):
            self.assertEqual(middleware(SimpleNamespace(scope=scope)), 'application-response')

        receive, send = AsyncMock(), AsyncMock()
        gate = guard_recovery_asgi(app)
        asyncio.run(gate({'type': 'http'}, receive, send))
        asyncio.run(gate({'type': 'http'}, receive, send))
        downstream.assert_called_once()
        self.assertEqual(admission.call_count, 2)
        self.assertEqual(send.call_args_list[0].args[0]['status'], 503)
        receive.assert_not_called()

    def test_wsgi_rejects_before_owner_or_body_access(self):
        bind_recovery_admission(lambda: self.denied)
        downstream = Mock()
        response = recovery_middleware(downstream)(SimpleNamespace())
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response['Cache-Control'], 'no-store')
        downstream.assert_not_called()

    def test_no_opt_in_keeps_existing_entry_and_websocket_close_is_not_a_restore(self):
        bind_recovery_admission()
        app, receive, send = AsyncMock(), AsyncMock(), AsyncMock()
        scope = {'type': 'http'}
        asyncio.run(guard_recovery_asgi(app)(scope, receive, send))
        app.assert_awaited_once_with(scope, receive, send)
        bind_recovery_admission(lambda: self.denied)
        asyncio.run(guard_recovery_asgi(app)({'type': 'websocket'}, receive, send))
        self.assertEqual(send.call_args.args[0], {'type': 'websocket.close', 'code': 1013})
        self.assertEqual(app.await_count, 1)
