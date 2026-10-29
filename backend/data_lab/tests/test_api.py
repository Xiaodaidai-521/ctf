from unittest.mock import patch
from django.db import DatabaseError
from data_lab.catalog import TASK_A, TASK_B
from data_lab.models import HelpRequest
from skill_review.models import AssistanceRecord
from skill_review.services.submissions import assistance_snapshot
from django.utils import timezone
from .base import LabTestCase


class ApiTests(LabTestCase):
    def url(self, suffix=''):
        return '/api/data-lab/' + suffix

    def post(self, suffix, data=None):
        return self.client.post(self.url(suffix), data or {}, format='json')

    def test_authentication_and_private_material(self):
        response = self.client.get(self.url(f'cases/{TASK_A}/'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'no-store, private')
        for key in ('teacher_answer', 'grading_secret', 'hints', 'answer_version'):
            self.assertNotIn(key, response.data)
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(self.url('cases/')).status_code, (401, 403))

    def test_claim_pause_resume_withdrawal(self):
        response = self.post(f'cases/{TASK_A}/claim/', {'version': self.catalog.version})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['attempt_id'], str(self.lab.attempt.attempt_id))
        case = self.cases[TASK_A]
        case.paused = True
        case.save()
        self.assertEqual(self.post(f'cases/{TASK_A}/claim/').status_code, 409)
        self.assertEqual(self.post(f'attempts/{self.lab.attempt.attempt_id}/').status_code, 200)
        case.withdrawn = True
        case.save()
        self.assertEqual(self.client.get(self.url(f'attempts/{self.lab.attempt.attempt_id}/')).status_code, 409)

    def test_retest_and_draft_gates(self):
        self.assertEqual(self.post(f'cases/{TASK_B}/claim/').status_code, 409)
        case = self.cases[TASK_A]
        case.status = 'draft'
        case.save()
        self.assertEqual(self.post(f'cases/{TASK_A}/claim/').status_code, 409)

    def test_student_and_teacher_object_isolation(self):
        other_lab = self.new_lab(self.other)
        index = self.client.get(self.url('cases/')).data
        self.assertNotIn(str(other_lab.attempt.attempt_id), str(index['attempts']))
        self.assertEqual(self.client.get(self.url(f'attempts/{other_lab.attempt.attempt_id}/')).status_code, 404)
        path = f'teacher/cases/{TASK_A}/attempts/'
        self.assertEqual(self.client.get(self.url(path)).status_code, 404)
        attachment = f'teacher/cases/{TASK_A}/material/'
        self.assertEqual(self.client.get(self.url(attachment)).status_code, 404)
        self.client.force_authenticate(self.reviewer)
        self.assertEqual(self.client.get(self.url(path)).status_code, 404)
        self.client.force_authenticate(self.teacher)
        response = self.client.get(self.url(path))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('teacher_answer', response.data)
        material = self.client.get(self.url(attachment))
        self.assertEqual(material.status_code, 200)
        self.assertEqual(material['Cache-Control'], 'no-store, private')
        self.assertIn('teacher_answer', material.data)
        self.assertEqual(self.post(path, {'paused': True}).status_code, 200)
        self.assertEqual(self.post(path, {'paused': 'yes'}).status_code, 400)

    def test_scan_pagination_and_unknown_fields(self):
        scan = self.scan()
        for query in ('limit=0', 'offset=-1', 'limit=bad'):
            self.assertEqual(self.client.get(self.url(f'scans/{scan.scan_id}/?{query}')).status_code, 400)
        self.assertEqual(self.client.get(self.url(f'scans/{scan.scan_id}/?limit=1')).status_code, 200)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(self.url(f'scans/{scan.scan_id}/')).status_code, 404)
        self.client.force_authenticate(self.student)
        self.assertEqual(self.post(f'attempts/{self.lab.attempt.attempt_id}/scans/',
            {'fixture_id': 'customer-v1', 'idempotency_key': 'bad', 'environment': 'production'}).status_code, 400)

    def test_hint_request_display_and_exposure_acl(self):
        aid = self.lab.attempt.attempt_id
        request = self.post(f'attempts/{aid}/help/', {'level': 1, 'source': 'card', 'idempotency_key': 'h'})
        self.assertEqual(request.status_code, 200, request.data)
        self.assertFalse(request.data['shown'])
        before = assistance_snapshot(attempt=self.lab.attempt, before=timezone.now())
        self.assertEqual(before['independence'], 'independent')
        self.client.force_authenticate(self.other)
        path = f"help/{request.data['request_id']}/display/"
        self.assertEqual(self.post(path).status_code, 404)
        self.client.force_authenticate(self.student)
        self.assertEqual(self.post(path).status_code, 200)
        self.assertEqual(self.post(path).status_code, 200)
        self.assertEqual(HelpRequest.objects.count(), 1)
        self.assertEqual(AssistanceRecord.objects.count(), 1)
        self.assertEqual(assistance_snapshot(attempt=self.lab.attempt, before=timezone.now())['independence'], 'assisted')
        self.assertEqual(self.client.get(self.url(f'attempts/{aid}/analysis/')).status_code, 409)

    def test_database_failure_is_retryable(self):
        with patch('data_lab.views.own_lab', side_effect=DatabaseError('unavailable')):
            response = self.client.get(self.url(f'attempts/{self.lab.attempt.attempt_id}/'))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data['detail'], '保存待重试')

    def test_execution_urls_absent_and_missing_evidence_rejected(self):
        for action in ('prepare', 'claim', 'consume', 'export'):
            self.assertEqual(self.post(action + '/').status_code, 404)
        response = self.post(f'attempts/{self.lab.attempt.attempt_id}/submissions/', {})
        self.assertEqual(response.status_code, 400)
