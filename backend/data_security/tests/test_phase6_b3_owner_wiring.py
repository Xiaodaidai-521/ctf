"""Database-free owner wiring checks; persistence and source deletion remain PG tests."""
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from data_security.contracts import BASELINE_LIMITS, Environment, ReasonCode
from feedback_center.private_uploads import FeedbackPrivateUploads
from resources.private_uploads import ResourcePrivateUploads


class LegacyOwnerWiringTests(TestCase):
    def setUp(self):
        self.actor = SimpleNamespace(pk=7, role='teacher', is_active=True, is_authenticated=True)
        self.maintenance = Mock()
        self.options = dict(prepare=Mock(), object_id=lambda: '00000000-0000-0000-0000-000000000002',
            project_ref='ctf', environment=Environment.TEST, limits=BASELINE_LIMITS,
            audit=Mock(), policy_binding=None, clock=Mock(), data_key_ref='enc-data/v1', read_event=Mock(),
            operations=object(), maintenance=self.maintenance)
        self.operation_id = '00000000-0000-0000-0000-000000000003'
        self.resource = SimpleNamespace(pk=12, uploader_id=7, title='Synthetic legacy', description='',
            resource_type='document', category='security', tags='', is_tutoring_reserved=False,
            file_size=4, private_files={}, status='pending', file=SimpleNamespace(name='resources/old.txt'),
            cover_image=None)
        self.attachment = SimpleNamespace(attachment_id='00000000-0000-0000-0000-000000000004',
            uploaded_by_id=7, ticket=SimpleNamespace(feedback_id='00000000-0000-0000-0000-000000000005'),
            original_name='old.txt', content_type='text/plain', size=4, sha256='0' * 64,
            visibility='student', private_file={}, file=SimpleNamespace(name='feedback_evidence/old.txt'))

    def test_resource_stage_reuses_existing_owner_and_injected_maintenance(self):
        owner = ResourcePrivateUploads(**self.options)
        # FileField's empty value still exposes .name.
        self.resource.cover_image = SimpleNamespace(name='resource_covers/old.png')
        with patch('resources.private_uploads.CTFUser.objects.filter') as users, \
             patch('resources.private_uploads.Resource.objects.filter') as resources, \
             patch('resources.private_uploads.connection.get_autocommit', return_value=True):
            users.return_value.first.return_value = self.actor
            resources.return_value.first.return_value = self.resource
            result = owner.maintain_legacy(user=self.actor, resource_id=12,
                operation_id=self.operation_id, action='stage')
        self.assertIs(result, self.maintenance.stage.return_value)
        values = self.maintenance.stage.call_args.kwargs
        self.assertEqual(values['owner_ref'], 'resources/12')
        self.assertEqual(values['actor_ref'], 'user/7')
        self.assertEqual(values['names'], {'resources/file': 'resources/old.txt',
                                         'resources/cover_image': 'resource_covers/old.png'})
        self.assertEqual(self.resource.file.name, 'resources/old.txt')
        self.options['prepare'].assert_not_called()
        self.options['audit'].record.assert_not_called()

    def test_feedback_stage_reuses_original_uploader_and_ticket_owner(self):
        owner = FeedbackPrivateUploads(**self.options)
        with patch('feedback_center.private_uploads.CTFUser.objects.filter') as users, \
             patch('feedback_center.private_uploads.FeedbackAttachment.objects') as attachments, \
             patch('feedback_center.private_uploads.connection.get_autocommit', return_value=True):
            users.return_value.first.return_value = self.actor
            attachments.select_related.return_value.filter.return_value.first.return_value = self.attachment
            result = owner.maintain_legacy(user=self.actor, ticket_id=self.attachment.ticket.feedback_id,
                attachment_id=self.attachment.attachment_id, operation_id=self.operation_id, action='stage')
        self.assertIs(result, self.maintenance.stage.return_value)
        self.assertEqual(self.maintenance.stage.call_args.kwargs['names'],
                         {'feedback/attachment': 'feedback_evidence/old.txt'})
        self.assertEqual(self.attachment.file.name, 'feedback_evidence/old.txt')
        self.options['audit'].record.assert_not_called()

    def test_maintenance_is_disabled_without_explicit_injection(self):
        options = {**self.options, 'maintenance': None}
        resource = ResourcePrivateUploads(**options).maintain_legacy(user=self.actor, resource_id=12,
            operation_id=self.operation_id, action='stage')
        feedback = FeedbackPrivateUploads(**options).maintain_legacy(user=self.actor, ticket_id='ticket',
            attachment_id='attachment', operation_id=self.operation_id, action='stage')
        self.assertEqual(resource.code, ReasonCode.AUTHORIZATION_DENIED)
        self.assertEqual(feedback.code, ReasonCode.AUTHORIZATION_DENIED)
        self.maintenance.stage.assert_not_called()

    def test_other_resource_owner_cannot_stage_through_cached_user(self):
        self.resource.uploader_id = 8
        with patch('resources.private_uploads.CTFUser.objects.filter') as users, \
             patch('resources.private_uploads.Resource.objects.filter') as resources, \
             patch('resources.private_uploads.connection.get_autocommit', return_value=True):
            users.return_value.first.return_value = self.actor
            resources.return_value.first.return_value = self.resource
            result = ResourcePrivateUploads(**self.options).maintain_legacy(user=self.actor, resource_id=12,
                operation_id=self.operation_id, action='stage')
        self.assertEqual(result.code, ReasonCode.AUTHORIZATION_DENIED)
        self.maintenance.stage.assert_not_called()

    def test_b2_record_count_fixes_are_preserved_in_all_three_owners(self):
        backend = Path(__file__).resolve().parents[2]
        for path, expected in (
                ('resources/private_uploads.py', "counts=(('records', len(operation.field_refs)),)"),
                ('feedback_center/private_uploads.py', "counts=(('records', 1),)"),
                ('data_security/adapters/persistence/file_shares.py', "counts=(('records', 1),)")):
            with self.subTest(path=path):
                source = (backend / path).read_text()
                self.assertIn(expected, source)
                self.assertNotIn("counts=(('files',", source)
