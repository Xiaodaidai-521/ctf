"""Audit detail protection and legacy-chain read protection without payload rewrites."""
import json

from django.db import connection
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from audit.models import AuditEvent, AuditLedgerEntry, SecurityAuditRecord
from audit.serializers import AuditEventSerializer, AuditLedgerEntrySerializer
from audit.views import AuditEventListView
from ctf_backend.security_bootstrap import assemble
from data_security.adapters.persistence.fields import bind_field_storage
from data_security.tests.phase4_fixtures import field_configuration
from users.models import CTFUser


class AuditFieldStorageTests(TestCase):
    def setUp(self):
        self.assertEqual(connection.vendor, 'postgresql')
        fixture = field_configuration()
        path, *_ = fixture.__enter__()
        self.addCleanup(fixture.__exit__, None, None, None)
        self.components = assemble(config_path=path)
        bind_field_storage(self.components['fields'])
        self.addCleanup(bind_field_storage, None)

    def test_hundred_details_and_metadata_gateway_do_not_recurse(self):
        for number in range(100):
            event = AuditEvent.objects.create(category='data_processing', summary='Synthetic event',
                detail={'note': f'Audit{number}@example.invalid', 'count': number}, ip_address='192.0.2.6')
            self.assertNotIn('@example.invalid', json.dumps(event.detail))
            self.assertEqual(event.detail['count'], number)
            self.assertEqual(event.ip_address, '192.0.2.6')
        self.assertEqual(SecurityAuditRecord.objects.count(), 100)
        self.assertEqual(AuditEvent.objects.count(), 200)
        with connection.cursor() as cursor:
            cursor.execute('SELECT detail::text FROM audit_auditevent')
            self.assertNotIn('@example.invalid', json.dumps(cursor.fetchall()))

    def test_ai_audit_direct_writes_are_minimal_and_sql_bulk_cannot_retain_bodies(self):
        from django.db import IntegrityError, transaction
        from audit.models import AIAuditLog
        for number in range(100):
            token = f'AIAudit{number}@example.invalid'
            row = AIAuditLog.objects.create(provider=token, model=token, user_message=token,
                ai_response=token, mode=token, error_message=token, success=False,
                duration_ms=11, token_estimate=12, ip_address='192.0.2.42')
            for name, value in AIAuditLog.minimized_fields.items():
                self.assertEqual(getattr(row, name), value)
            self.assertFalse(row.success)
        with connection.cursor() as cursor:
            cursor.execute('SELECT row_to_json(item)::text FROM audit_aiauditlog item')
            self.assertNotIn('@example.invalid', json.dumps(cursor.fetchall()))
        with self.assertRaisesRegex(RuntimeError, 'FIELD_UPDATE'):
            AIAuditLog.objects.filter(pk=row.pk).update(user_message='Raw@example.invalid')
        row.ai_response = 'Raw@example.invalid'
        with self.assertRaisesRegex(RuntimeError, 'FIELD_BULK_UPDATE'):
            AIAuditLog.objects.bulk_update([row], ['ai_response'])
        with self.assertRaises(IntegrityError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute('UPDATE audit_aiauditlog SET user_message=%s WHERE id=%s',
                               ['Raw@example.invalid', row.pk])

    def test_legacy_ledger_payload_is_not_rewritten_on_read(self):
        payload = {'note': 'Legacy@example.invalid', 'count': 1}
        entry = AuditLedgerEntry.objects.create(event_category='data_processing', payload=payload,
            payload_hash='a' * 64, current_hash='b' * 64)
        wire = AuditLedgerEntrySerializer(entry).data
        self.assertNotIn('Legacy@example.invalid', json.dumps(wire))
        entry.refresh_from_db()
        self.assertEqual(entry.payload, payload)
        self.assertEqual(entry.current_hash, 'b' * 64)

    def test_admin_role_alone_cannot_read_ungranted_user_events(self):
        admin = CTFUser.objects.create_user(username='synthetic-audit-admin', role='admin')
        other = CTFUser.objects.create_user(username='synthetic-audit-other')
        event = AuditEvent.objects.create(user=other, category='data_processing', summary='Synthetic',
            detail={'note': 'Other@example.invalid'})
        request = APIRequestFactory().get('/api/audit/events/')
        force_authenticate(request, user=admin)
        response = AuditEventListView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        rows = response.data.get('results', []) if isinstance(response.data, dict) else response.data
        self.assertNotIn(event.pk, [row['id'] for row in rows])
        self.assertNotIn('Other@example.invalid', json.dumps(AuditEventSerializer(event).data))
