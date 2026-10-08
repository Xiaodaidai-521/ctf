"""Tests for audit ledger services and audit API access."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import AuditEvent, AuditLedgerEntry
from .services import AuditLedgerService, GENESIS_HASH, compute_payload_hash


User = get_user_model()


class AuditLedgerServiceTests(TestCase):
    """Hash-chain behavior should be deterministic and tamper-evident."""

    def setUp(self):
        self.admin = User.objects.create_user(
            username='admin',
            password='pass12345',
            role='admin',
            is_staff=True,
        )

    def test_append_entry_links_to_genesis_hash(self):
        entry = AuditLedgerService.append_entry(
            event_category='consent_sign',
            object_type='legal.UserConsentRecord',
            object_id='1',
            actor=self.admin,
            payload={'protocol': 'privacy', 'version': 1},
        )

        self.assertEqual(entry.previous_hash, GENESIS_HASH)
        self.assertEqual(entry.payload_hash, compute_payload_hash({
            'protocol': 'privacy',
            'version': 1,
        }))
        self.assertEqual(entry.actor, self.admin)
        self.assertEqual(AuditLedgerService.verify_chain().is_valid, True)

    def test_append_entry_links_to_previous_current_hash(self):
        first = AuditLedgerService.append_entry(
            event_category='consent_sign',
            payload={'step': 1},
        )
        second = AuditLedgerService.append_entry(
            event_category='report_export',
            payload={'step': 2},
        )

        self.assertEqual(second.previous_hash, first.current_hash)
        self.assertEqual(AuditLedgerService.verify_chain().checked_count, 2)
        self.assertEqual(AuditLedgerService.verify_chain().is_valid, True)

    def test_verify_chain_detects_payload_tampering(self):
        entry = AuditLedgerService.append_entry(
            event_category='violation_record',
            payload={'status': 'open'},
        )
        AuditLedgerEntry.objects.filter(pk=entry.pk).update(payload={'status': 'closed'})

        result = AuditLedgerService.verify_chain()

        self.assertFalse(result.is_valid)
        self.assertEqual(result.errors[0].entry_id, entry.id)
        self.assertEqual(result.errors[0].field, 'payload_hash')


class AuditApiTests(TestCase):
    """Audit APIs should be admin-only and expose read models."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username='admin',
            password='pass12345',
            role='admin',
            is_staff=True,
        )
        self.student = User.objects.create_user(
            username='student',
            password='pass12345',
            role='student',
        )
        AuditEvent.objects.create(
            user=self.admin,
            category='legal_analysis',
            level='INFO',
            summary='Compliance task completed',
            detail={'task_id': 1},
        )
        AuditLedgerService.append_entry(
            event_category='legal_analysis',
            object_type='legal.LegalAnalysisTask',
            object_id='1',
            actor=self.admin,
            payload={'task_id': 1},
        )

    def test_student_cannot_list_audit_events(self):
        self.client.force_authenticate(self.student)
        response = self.client.get('/api/audit/events/')

        self.assertEqual(response.status_code, 403)

    def test_admin_can_list_audit_events(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get('/api/audit/events/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['results'][0]['category'], 'legal_analysis')

    def test_admin_can_verify_ledger(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get('/api/audit/ledger/verify/')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['is_valid'])
        self.assertEqual(response.data['total_entries'], response.data['checked_count'])
        self.assertEqual(response.data['checked_count'], 1)
