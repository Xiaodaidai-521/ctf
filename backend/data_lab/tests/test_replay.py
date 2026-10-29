from dataclasses import replace
from unittest.mock import patch
from rest_framework.exceptions import ValidationError
from export_risk.contracts import SourceMode
from export_risk.models import ExecutionAuthorizationRecord, RiskDecision, DeliveryRecord
from export_quota.models import QuotaReservation
from data_lab.common import Conflict
from data_lab.replay import start_replay, save_judgment, replay_dto, EVALUATION_TIME
from data_lab.services import submit_review
from data_lab.teacher_material import EXPECTED_REPLAYS
from .base import LabTestCase


class ReplayTests(LabTestCase):
    def prepare(self):
        scan = self.scan()
        submit_review(self.student, scan.current_profile_id, {'expected_state_version': 1, 'idempotency_key': 'review',
            'action': 'confirm', 'reason': '业务事实核查', 'finding_id': scan.original['findings'][0]['finding_id'],
            'fact_ids': ['F-PERSON'], 'basis_ids': ['BC-DS-001']})
        return scan

    def test_four_rounds_frozen_and_readonly_sentinels(self):
        with patch('export_risk.decisions.service.prepare_execution', side_effect=AssertionError('prepare')) as prepare, \
             patch('export_risk.decisions.service.claim', side_effect=AssertionError('claim')) as claim, \
             patch('export_risk.decisions.service.consume', side_effect=AssertionError('consume')) as consume, \
             patch('requests.sessions.Session.request', side_effect=AssertionError('network')) as network:
            self.prepare()
            for variant, actions in EXPECTED_REPLAYS.items():
                replay = start_replay(self.student, self.lab.attempt.attempt_id,
                    {'scenario_variant': variant, 'idempotency_key': variant})
                self.assertNotIn('frozen', replay_dto(replay))
                replay = save_judgment(self.student, replay.replay_id, {'actions': actions, 'reason': '先判断后比较',
                    'fact_ids': ['F-AUTH'], 'basis_ids': ['BC-DS-001'], 'idempotency_key': variant})
                frozen = replay_dto(replay)['frozen']
                self.assertEqual([s['result']['recommended_action'] for s in frozen['steps']], actions)
                self.assertEqual(frozen['evaluation_time'], EVALUATION_TIME)
                self.assertEqual(frozen['policy_status'], 'draft')
                if variant == 'A2':
                    self.assertIn('hard.recipient_forbidden', frozen['steps'][0]['result']['reason_codes'])
                if variant == 'A4':
                    self.assertEqual([s['inputs']['features']['values']['req_count_long'] for s in frozen['steps']], [50, 51])
                if variant in ('A1', 'A4'):
                    self.assertTrue(all(s['result']['obligations'] for s in frozen['steps']))
            for sentinel in (prepare, claim, consume, network):
                sentinel.assert_not_called()
        for model in (ExecutionAuthorizationRecord, RiskDecision, DeliveryRecord, QuotaReservation):
            self.assertEqual(model.objects.count(), 0)

    def test_trusted_fields_cannot_be_overridden(self):
        self.prepare()
        for field in ('source_mode', 'environment', 'authorization', 'asset_digest', 'policy_version', 'url', 'path'):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                start_replay(self.student, self.lab.attempt.attempt_id,
                    {'scenario_variant': 'A1', 'idempotency_key': field, field: 'production'})

    def test_replay_idempotency_and_judgment_freeze(self):
        self.prepare()
        data = {'scenario_variant': 'A1', 'idempotency_key': 'same'}
        replay = start_replay(self.student, self.lab.attempt.attempt_id, data)
        self.assertEqual(start_replay(self.student, self.lab.attempt.attempt_id, data).pk, replay.pk)
        with self.assertRaises(Conflict):
            start_replay(self.student, self.lab.attempt.attempt_id, {**data, 'scenario_variant': 'A2'})
        answer = {'actions': ['allow'], 'reason': '我先作判断', 'fact_ids': ['F-AUTH'], 'basis_ids': ['BC-DS-001'], 'idempotency_key': 'judge'}
        save_judgment(self.student, replay.replay_id, answer)
        with self.assertRaises(Conflict):
            save_judgment(self.student, replay.replay_id, {**answer, 'actions': ['mask']})
