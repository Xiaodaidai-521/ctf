"""Real M6/M1 rows, deliberately independent of data_lab.submissions.deliver."""
from copy import deepcopy
from datetime import timedelta
from unittest.mock import patch
from uuid import UUID, uuid4

from django.db import DatabaseError
from django.test import override_settings
from django.utils import timezone

from data_lab.catalog import TASK_B, digest
from data_lab.handoff import ingest_fact
from data_lab.tests.base import LabTestCase
from learning_analytics.models import LearningEvent
from learning_map.models import Capability, CapabilityState, PathChangeLog, VerificationFact
from learning_map.services.handoff import FactConflict
from skill_review.models import (
    DownstreamNotice, ResultCorrection, RetestAssignment, SubmissionSnapshot, VerificationResult,
)
from skill_review.services.handoff import dispatch_result, retry_module1_notice


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class HandoffTests(LabTestCase):
    def make_result(self, *, lab=None, first_effective=True, **overrides):
        lab = lab or self.lab
        attempt = lab.attempt
        submission = SubmissionSnapshot.objects.create(
            client_submission_id=str(uuid4()), attempt=attempt, student=attempt.student,
            task=attempt.task, catalog=attempt.catalog, task_version=attempt.task_version,
            sequence=attempt.submissions.count() + 1,
            payload={'schema': 'data-lab-evidence-v1', 'synthetic': True},
            payload_hash=digest({'synthetic': True}), first_effective=first_effective,
            independence=overrides.get('independence', 'independent'),
            assistance_snapshot=overrides.get('assistance_snapshot', {}),
        )
        fields = {
            'program_status': 'passed', 'manual_status': 'not_applicable',
            'overall_status': 'passed', 'independence': 'independent',
            'verifier_version': 'data-lab-test-v1',
        }
        fields.update(overrides)
        return VerificationResult.objects.create(
            submission=submission, attempt=attempt, student=attempt.student,
            task=attempt.task, catalog=attempt.catalog, **fields,
        )

    def counts(self):
        return (VerificationFact.objects.count(), CapabilityState.objects.count(),
                PathChangeLog.objects.count(), LearningEvent.objects.count(), DownstreamNotice.objects.count())

    def test_first_delivery_repeat_and_sent_retry_are_idempotent_and_bounded(self):
        capability = Capability.objects.create(
            catalog=self.catalog, stable_id='D' * 64, title='Long capability identity',
            track='data_security', observable_objective='Evidence', dimension='identify', status='open',
        )
        self.lab.case.task.capabilities.add(capability)
        result = self.make_result()
        with patch('export_risk.decisions.service.prepare_execution') as prepare, \
                patch('export_risk.decisions.service.claim') as claim, \
                patch('export_risk.decisions.service.consume') as consume:
            sent, notices = dispatch_result(result)
            self.assertTrue(sent, notices[0].last_error)
            self.assertEqual(notices[0].attempts, 1)
            frozen = deepcopy(notices[0].payload)
            counts = self.counts()
            with patch('django.utils.timezone.now', return_value=timezone.now() + timedelta(days=1)):
                self.assertTrue(dispatch_result(result)[0])
                retried = retry_module1_notice(notices[0])
            self.assertEqual(counts, self.counts())
            self.assertEqual(retried.attempts, 1)
            self.assertEqual(retried.payload, frozen)
            for sentinel in (prepare, claim, consume):
                sentinel.assert_not_called()
        self.assertEqual(VerificationFact.objects.count(), 2)
        self.assertEqual(len(result.module1_fact_ids), 2)
        for fact in VerificationFact.objects.all():
            self.assertLessEqual(len(fact.fact_id), 56)
            self.assertEqual(fact.occurred_at, result.created_at)
            self.assertEqual(fact.payload['result_revision'], 1)
        for event in LearningEvent.objects.all():
            self.assertLessEqual(len(event.event_id), 64)
        for notice in notices:
            self.assertLessEqual(len(notice.notice_key), 160)

    def test_same_fact_id_rejects_all_changed_content_including_first_attempt_and_json(self):
        sent, notices = dispatch_result(self.make_result())
        self.assertTrue(sent)
        frozen = notices[0].payload['facts'][0]
        original = VerificationFact.objects.get()
        changes = {
            'first_attempt': False,
            'payload': {**frozen['payload'], 'result_revision': 99},
            'outcome': 'failed',
            'occurred_at': (original.occurred_at + timedelta(seconds=1)).isoformat(),
        }
        for field, value in changes.items():
            with self.subTest(field=field):
                changed = {**deepcopy(frozen), field: value}
                with self.assertRaises(FactConflict):
                    ingest_fact(changed)
        # JSON equality must not silently treat true and 1 as identical content.
        changed = deepcopy(frozen)
        changed['payload']['result_revision'] = True
        with self.assertRaises(FactConflict):
            ingest_fact(changed)
        original.refresh_from_db()
        self.assertTrue(original.first_attempt)
        self.assertEqual(original.payload, frozen['payload'])
        self.assertEqual(VerificationFact.objects.count(), 1)

    def test_uuid_strings_and_objects_are_equivalent_including_retest(self):
        original = self.make_result()
        lab = self.new_lab(task_key=TASK_B)
        result = self.make_result(lab=lab)
        RetestAssignment.objects.create(
            student=self.student, catalog=self.catalog, original_attempt=original.attempt,
            original_submission=original.submission, selected_task=result.task,
            started_attempt=result.attempt, pool_snapshot={}, capability_ids=['DS-005'],
        )
        sent, notices = dispatch_result(result)
        self.assertTrue(sent, notices[0].last_error)
        payload = deepcopy(notices[0].payload['facts'][0])
        before = self.counts()
        for transform in (lambda value: UUID(value), lambda value: UUID(value).hex.upper()):
            candidate = deepcopy(payload)
            for field in ('attempt_id', 'retest_of_attempt_id'):
                candidate[field] = transform(candidate[field])
            fact, _, changed, created = ingest_fact(candidate)
            self.assertFalse(created)
            self.assertFalse(changed)
            self.assertEqual(fact.retest_of_attempt_id, original.attempt.attempt_id)
        self.assertEqual(before, self.counts())
        self.assertEqual(notices[0].payload['facts'][0], payload)

    def test_m1_fact_event_failure_keeps_failed_notice_and_recovers(self):
        result = self.make_result()
        with patch('learning_map.services.handoff.emit_event', side_effect=DatabaseError('M1 event unavailable')):
            sent, notices = dispatch_result(result)
        self.assertFalse(sent)
        self.assertEqual(notices[0].status, 'failed')
        self.assertIn('M1 event unavailable', notices[0].last_error)
        self.assertEqual(notices[0].attempts, 1)
        self.assertEqual(self.counts(), (0, 0, 0, 0, 3))
        result.refresh_from_db()
        self.assertEqual(result.overall_status, 'passed')
        self.assertEqual(result.module1_fact_ids, {})
        frozen = deepcopy(notices[0].payload)
        recovered = retry_module1_notice(notices[0])
        self.assertEqual(recovered.status, 'sent', recovered.last_error)
        self.assertEqual(recovered.attempts, 2)
        self.assertEqual(recovered.payload, frozen)
        self.assertIsNotNone(recovered.sent_at)
        result.refresh_from_db()
        self.assertEqual(result.module1_fact_ids['DS-005'], VerificationFact.objects.get().fact_id)
        before = self.counts()
        retry_module1_notice(recovered)
        self.assertEqual(before, self.counts())

    def test_path_event_failure_also_rolls_back_and_can_retry(self):
        with patch('learning_map.services.pathing.emit_event', side_effect=DatabaseError('path event unavailable')):
            sent, notices = dispatch_result(self.make_result())
        self.assertFalse(sent)
        self.assertEqual(self.counts(), (0, 0, 0, 0, 3))
        self.assertEqual(notices[0].status, 'failed')
        self.assertEqual(retry_module1_notice(notices[0]).status, 'sent')

    def test_dispatch_event_failure_rolls_back_whole_batch_and_recovers(self):
        result = self.make_result()
        with patch('data_lab.handoff.events.emit_event', side_effect=DatabaseError('M6 event unavailable')):
            sent, notices = dispatch_result(result)
        self.assertFalse(sent)
        self.assertEqual(self.counts(), (0, 0, 0, 0, 3))
        self.assertEqual(notices[0].status, 'failed')
        self.assertEqual(retry_module1_notice(notices[0]).status, 'sent')
        self.assertEqual(LearningEvent.objects.filter(event_type='verification_result').count(), 2)

    def test_conflicting_dispatch_event_fails_without_overwriting_and_can_recover(self):
        result = self.make_result()
        sent, notices = dispatch_result(result)
        self.assertTrue(sent)
        notice = notices[0]
        event = LearningEvent.objects.get(event_id=notice.payload['event_id'])
        metadata = deepcopy(event.metadata)
        event.metadata = {**metadata, 'overall_status': 'different-content'}
        event.save(update_fields=['metadata'])
        notice.status = 'failed'
        notice.save(update_fields=['status'])
        failed = retry_module1_notice(notice)
        self.assertEqual(failed.status, 'failed')
        self.assertIn('ID内容冲突', failed.last_error)
        event.refresh_from_db()
        self.assertEqual(event.metadata['overall_status'], 'different-content')
        self.assertEqual(VerificationFact.objects.count(), 1)
        event.metadata = metadata
        event.save(update_fields=['metadata'])
        self.assertEqual(retry_module1_notice(failed).status, 'sent')
        self.assertEqual(LearningEvent.objects.filter(event_id=event.event_id).count(), 1)

    def test_retry_uses_frozen_content_not_mutated_result(self):
        result = self.make_result()
        with patch('learning_map.services.handoff.emit_event', side_effect=DatabaseError('offline')):
            _, notices = dispatch_result(result)
        frozen = deepcopy(notices[0].payload)
        result.overall_status = 'failed'
        result.save(update_fields=['overall_status'])
        retry = retry_module1_notice(notices[0])
        self.assertEqual(retry.status, 'sent')
        self.assertEqual(retry.payload, frozen)
        self.assertEqual(VerificationFact.objects.get().outcome, 'passed')
        self.assertEqual(LearningEvent.objects.get(event_id=frozen['event_id']).metadata['overall_status'], 'passed')

    def test_redispatch_different_first_attempt_is_failed_without_replacing_payload(self):
        result = self.make_result()
        _, notices = dispatch_result(result)
        frozen = deepcopy(notices[0].payload)
        result.submission.first_effective = False
        result.submission.save(update_fields=['first_effective'])
        sent, repeated = dispatch_result(result)
        self.assertFalse(sent)
        self.assertEqual(repeated[0].status, 'failed')
        self.assertEqual(repeated[0].payload, frozen)
        self.assertTrue(VerificationFact.objects.get().first_attempt)
        self.assertEqual(DownstreamNotice.objects.count(), 3)

    def test_revision_appends_facts_and_notices_without_overwriting_old_evidence(self):
        result = self.make_result(overall_status='pending_manual', manual_status='pending')
        _, notices = dispatch_result(result)
        old = VerificationFact.objects.get()
        old_payload = deepcopy(old.payload)
        old_notice_payload = deepcopy(notices[0].payload)
        result.revision += 1
        result.manual_status = 'passed'
        result.overall_status = 'passed'
        result.save()
        sent, revised = dispatch_result(result)
        self.assertTrue(sent, revised[0].last_error)
        self.assertEqual(VerificationFact.objects.count(), 2)
        self.assertEqual(DownstreamNotice.objects.count(), 6)
        self.assertNotEqual(revised[0].pk, notices[0].pk)
        self.assertNotEqual(old.fact_id, result.module1_fact_ids['DS-005'])
        old.refresh_from_db()
        notices[0].refresh_from_db()
        self.assertEqual(old.outcome, 'pending_review')
        self.assertEqual(old.payload, old_payload)
        self.assertEqual(notices[0].payload, old_notice_payload)
        self.assertEqual(CapabilityState.objects.get().state, 'independent')
        before = self.counts()
        self.assertTrue(dispatch_result(result)[0])
        self.assertEqual(before, self.counts())

    def test_failed_old_revision_retry_does_not_replace_current_fact_id_map(self):
        result = self.make_result(overall_status='pending_manual', manual_status='pending')
        with patch('learning_map.services.handoff.emit_event', side_effect=DatabaseError('offline')):
            _, old_notices = dispatch_result(result)
        result.revision = 2
        result.overall_status = 'passed'
        result.manual_status = 'passed'
        result.save()
        self.assertTrue(dispatch_result(result)[0])
        current_ids = dict(result.module1_fact_ids)
        self.assertEqual(retry_module1_notice(old_notices[0]).status, 'sent')
        result.refresh_from_db()
        self.assertEqual(result.module1_fact_ids, current_ids)
        self.assertEqual(VerificationFact.objects.count(), 2)
        self.assertEqual(CapabilityState.objects.get().state, 'independent')

    def test_teacher_assisted_zero_level_is_at_least_one_never_independent(self):
        result = self.make_result(
            independence='assisted', assistance_snapshot={'level': 0, 'source': 'teacher', 'shown': True},
        )
        sent, notices = dispatch_result(result)
        self.assertTrue(sent, notices[0].last_error)
        fact = VerificationFact.objects.get()
        self.assertEqual((fact.independence, fact.assistance_level, fact.assistance_source), ('assisted', 1, 'teacher'))
        self.assertTrue(fact.assistance_shown)
        self.assertEqual(CapabilityState.objects.get().state, 'assisted_pass')
        self.assertEqual(result.assistance_snapshot['level'], 0)

    def test_modules_seven_and_eight_are_not_connected_and_never_retried(self):
        _, notices = dispatch_result(self.make_result())
        self.assertEqual([notice.target for notice in notices], ['module1', 'module7', 'module8'])
        for notice in notices[1:]:
            self.assertEqual(notice.status, 'not_connected')
            self.assertFalse(notice.target_connected)
            self.assertEqual(notice.attempts, 0)
            self.assertIsNone(notice.sent_at)
            with patch('learning_map.services.handoff.ingest_verification_fact') as ingest:
                retry_module1_notice(notice)
                ingest.assert_not_called()
        self.assertEqual(notices[2].payload['reason'], 'not_connected')

    def test_no_capabilities_is_failed_not_vacuously_sent(self):
        self.lab.case.task.capabilities.clear()
        sent, notices = dispatch_result(self.make_result())
        self.assertFalse(sent)
        self.assertEqual(notices[0].status, 'failed')
        self.assertEqual(retry_module1_notice(notices[0]).status, 'failed')
        self.assertEqual(VerificationFact.objects.count(), 0)

    def test_correction_links_old_fact_without_overwriting_it(self):
        original = self.make_result(overall_status='failed')
        self.assertTrue(dispatch_result(original)[0])
        old_id = original.module1_fact_ids['DS-005']
        original.is_current = False
        original.save(update_fields=['is_current'])
        corrected = VerificationResult.objects.create(
            submission=original.submission, attempt=original.attempt, student=self.student,
            task=original.task, catalog=self.catalog, version=2, supersedes=original,
            program_status='passed', manual_status='passed', overall_status='passed',
            independence='independent', verifier_version='data-lab-test-v1',
        )
        correction = ResultCorrection.objects.create(
            submission=original.submission, original_result=original, corrected_result=corrected,
            corrected_by=self.teacher, source='teacher_review', reason='Evidence reviewed',
        )
        sent, notices = dispatch_result(corrected, correction=correction)
        self.assertTrue(sent, notices[0].last_error)
        new_fact = VerificationFact.objects.get(fact_id=corrected.module1_fact_ids['DS-005'])
        self.assertEqual(new_fact.payload['correction_of_fact_id'], old_id)
        self.assertEqual(VerificationFact.objects.get(fact_id=old_id).outcome, 'failed')
        self.assertEqual(notices[0].correction_id, correction.pk)

    def test_other_validator_keeps_legacy_dispatch(self):
        result = self.make_result(first_effective=False)
        result.task.validator = {'type': 'existing_module'}
        result.task.save(update_fields=['validator'])
        with patch('data_lab.handoff.dispatch_result') as dispatch:
            self.assertEqual(dispatch_result(result), (False, []))
            dispatch.assert_not_called()
