import json
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from evaluation_center.projections import attempt_detail, query_learning, retest_payload
from learning_analytics.models import LearningEvent
from learning_map.models import CatalogVersion, KnowledgePoint, TaskAttempt, VerificationFact
from skill_review.models import AssistanceRecord, SubmissionSnapshot, VerificationResult
from skill_review.services import correction, retest, submissions
from skill_review.tests.test_module6 import (
    DATA_VALIDATOR, RETEST_VALIDATOR, good_payload, make_attempt, make_capability,
    make_catalog, make_task,
)
from users.models import CTFUser


class ProjectionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.student = CTFUser.objects.create_user(username='m8-reader', role='student')
        cls.other = CTFUser.objects.create_user(username='m8-other', role='student')
        cls.teacher = CTFUser.objects.create_user(username='m8-teacher', role='teacher')
        cls.catalog = make_catalog()
        cls.capability = make_capability(cls.catalog)
        cls.point = KnowledgePoint.objects.create(
            catalog=cls.catalog, stable_id='KP-1', track='data', name='合成知识点',
        )
        cls.capability.knowledge_points.add(cls.point)
        cls.task = make_task(cls.catalog, cls.capability, validator=RETEST_VALIDATOR)

    def submit(self, *, attempt=None, task=None, student=None, payload=None, tracking='complete', now=None):
        student = student or self.student
        attempt = attempt or make_attempt(task or self.task, student, self.catalog)
        submission, _ = submissions.create_submission(
            student=student, attempt=attempt,
            client_submission_id=f'm8-sub-{SubmissionSnapshot.objects.count()}',
            payload=good_payload() if payload is None else payload,
            assistance_tracking=tracking, now=now,
        )
        return attempt, submission

    def metrics(self, **filters):
        return query_learning(**filters)['version_groups'][0]['metrics']

    def test_real_result_fact_versions_are_expandable(self):
        attempt, submission = self.submit()
        detail = attempt_detail(attempt)
        self.assertEqual(detail['overall_status'], 'passed')
        self.assertEqual(detail['versions']['catalog_version'], self.catalog.version)
        self.assertEqual(detail['submissions'][0]['submission_id'], str(submission.submission_id))
        self.assertTrue(detail['facts'])
        self.assertEqual(detail['current_result']['fact_ids'][0], detail['facts'][0]['fact_id'])
        self.assertTrue(all(row['binding_valid'] for row in detail['facts']))

    def test_frontend_event_cannot_create_grade(self):
        attempt = make_attempt(self.task, self.student, self.catalog)
        LearningEvent.objects.create(
            event_id='untrusted-pass', user=self.student, event_type='verification_result',
            event_time=timezone.now(), metadata={
                'attempt_id': str(attempt.attempt_id), 'passed': True, 'result_id': 'invented',
                'source': 'skill_review',
            },
        )
        detail = attempt_detail(attempt)
        self.assertIsNone(detail['current_result'])
        self.assertEqual(detail['overall_status'], 'not_submitted')
        self.assertEqual(detail['reconciliation']['unbacked_result_events'], ['invented'])
        self.assertEqual(self.metrics()['core_pass']['denominator'], 0)

    def test_requested_not_displayed_is_independent(self):
        attempt = make_attempt(self.task, self.student, self.catalog)
        submissions.request_hint(student=self.student, attempt=attempt, level=4, source='card')
        self.submit(attempt=attempt)
        detail = attempt_detail(attempt)
        self.assertEqual(detail['independence'], 'independent')
        self.assertEqual(detail['current_result']['help']['requested_not_shown'], 1)
        self.assertEqual(self.metrics()['independent_completion']['numerator'], 1)

    def test_ai_and_card_each_level_are_assistance(self):
        for source in ('ai', 'card'):
            for level in range(1, 5):
                with self.subTest(source=source, level=level):
                    attempt = make_attempt(self.task, self.student, self.catalog)
                    hint = submissions.request_hint(student=self.student, attempt=attempt, level=level, source=source)
                    submissions.show_hint(record=hint)
                    self.submit(attempt=attempt)
                    self.assertEqual(attempt_detail(attempt)['independence'], 'assisted')

    def test_teacher_help_is_not_event_count_heuristic(self):
        attempt = make_attempt(self.task, self.student, self.catalog)
        submissions.record_teacher_help(teacher=self.teacher, attempt=attempt, summary='受控教学说明')
        self.submit(attempt=attempt)
        self.assertEqual(attempt_detail(attempt)['independence'], 'assisted')

    def test_manual_review_event_does_not_count_as_help(self):
        attempt, _ = self.submit()
        LearningEvent.objects.create(
            event_id='sampling-not-help', user=self.student, event_type='teacher_help',
            event_time=timezone.now(), metadata={'attempt_id': str(attempt.attempt_id), 'source': 'skill_review'},
        )
        self.assertEqual(attempt_detail(attempt)['independence'], 'independent')

    def test_completed_result_is_frozen_after_help_and_analysis(self):
        attempt, _ = self.submit()
        submissions.record_analysis_view(student=self.student, task=self.task, attempt=attempt)
        submissions.record_teacher_help(teacher=self.teacher, attempt=attempt, summary='复盘')
        detail = attempt_detail(attempt)
        self.assertEqual(detail['independence'], 'independent')
        self.assertEqual(len(detail['assistance']), 2)

    def test_answer_exposure_makes_repeat_unknown(self):
        first, _ = self.submit()
        submissions.record_analysis_view(student=self.student, task=self.task, attempt=first)
        repeat, _ = self.submit()
        self.assertEqual(attempt_detail(first)['independence'], 'independent')
        self.assertEqual(attempt_detail(repeat)['independence'], 'unknown')
        self.assertEqual(self.metrics()['first_effective_attempts']['numerator'], 1)

    def test_resubmission_never_replaces_first_failure(self):
        attempt, _ = self.submit(payload={})
        self.submit(attempt=attempt)
        detail = attempt_detail(attempt)
        self.assertEqual(detail['overall_status'], 'failed')
        self.assertEqual(detail['submission_count'], 2)
        self.assertEqual(detail['submissions'][1]['current_result']['overall_status'], 'passed')
        self.assertEqual(self.metrics()['core_pass']['numerator'], 0)

    def test_new_attempt_never_replaces_first_failure(self):
        self.submit(payload={})
        self.submit()
        data = query_learning()
        self.assertEqual(sum(row['first_effective_attempt'] for row in data['rows']), 1)
        self.assertEqual(data['version_groups'][0]['metrics']['core_pass']['numerator'], 0)

    def test_window_cannot_reclassify_repeat_as_first(self):
        now = timezone.now()
        self.submit(payload={}, now=now - timedelta(days=7))
        self.submit(now=now)
        data = query_learning(start=now - timedelta(days=1))
        self.assertEqual(len(data['rows']), 1)
        self.assertFalse(data['rows'][0]['first_effective_attempt'])
        self.assertEqual(data['version_groups'][0]['metrics']['core_pass']['denominator'], 0)

    def test_unknown_pending_manual_environment_are_separate(self):
        self.submit(tracking='missing')
        manual = make_task(self.catalog, self.capability, task_key='manual', validator=DATA_VALIDATOR)
        self.submit(task=manual)
        attempt, submission = self.submit(student=self.other)
        correction.create_correction(
            submission=submission, actor=self.teacher, source='teacher_review', reason='环境故障',
            changes={'overall_status': 'environment_affected', 'verification_error': 'environment_unavailable'},
        )
        data = query_learning()
        rows = {row['attempt_id']: row for row in data['rows']}
        self.assertEqual(rows[str(attempt.attempt_id)]['overall_status'], 'environment_affected')
        self.assertEqual({row['overall_status'] for row in data['rows']}, {'passed', 'pending_manual', 'environment_affected'})
        group = next(group for group in data['version_groups'] if group['versions']['task_key'] == self.task.task_key)
        self.assertEqual(group['metrics']['independent_completion']['denominator'], 0)
        self.assertEqual(group['metrics']['independent_completion']['missing'], 2)

    def test_current_correction_not_original_snapshot_controls_metric(self):
        attempt, submission = self.submit()
        old = submission.results.get(is_current=True)
        change = correction.create_correction(
            submission=submission, actor=self.teacher, source='teacher_review', reason='更正帮助记录',
            changes={'independence': 'assisted', 'assistance_snapshot': {
                'shown': True, 'level': 2, 'source': 'teacher', 'reason': 'help_shown',
            }},
        )
        detail = attempt_detail(attempt)
        self.assertEqual(detail['submissions'][0]['original_independence'], 'independent')
        self.assertEqual(detail['independence'], 'assisted')
        self.assertEqual(len(detail['submissions'][0]['result_history']), 2)
        self.assertEqual(detail['corrections'][0]['original_result_id'], str(old.result_id))
        self.assertEqual(detail['corrections'][0]['corrected_result_id'], str(change.corrected_result.result_id))
        self.assertEqual(self.metrics()['independent_completion']['numerator'], 0)

    def test_correction_can_establish_assistance_despite_missing_old_tracking(self):
        attempt, submission = self.submit(tracking='missing')
        self.assertEqual(attempt_detail(attempt)['independence'], 'unknown')
        correction.create_correction(
            submission=submission, actor=self.teacher, source='late_event', reason='补到已展示帮助证据',
            changes={'independence': 'assisted', 'assistance_snapshot': {
                'shown': True, 'level': 2, 'source': 'teacher', 'reason': 'help_shown',
            }},
        )
        self.assertEqual(attempt_detail(attempt)['independence'], 'assisted')
        self.assertEqual(self.metrics()['independent_completion']['denominator'], 1)

    def test_missing_result_snapshot_is_not_independence_evidence(self):
        attempt, submission = self.submit()
        submission.results.update(assistance_snapshot={})
        self.assertEqual(attempt_detail(attempt)['independence'], 'unknown')
        submission.results.update(assistance_snapshot={'shown': False})
        self.assertEqual(attempt_detail(attempt)['independence'], 'unknown')

    def test_unmapped_history_is_excluded(self):
        attempt, _ = self.submit()
        TaskAttempt.objects.filter(pk=attempt.pk).update(capability_ids=['unmapped-legacy'])
        data = query_learning()
        self.assertEqual(data['rows'][0]['mapping_status'], 'unmapped')
        self.assertEqual(data['version_groups'][0]['metrics']['core_pass']['denominator'], 0)
        self.assertEqual(data['version_groups'][0]['metrics']['unmapped']['numerator'], 1)

    def test_distinct_versions_are_not_combined(self):
        self.submit()
        catalog2 = CatalogVersion.objects.create(version='v2', label='v2', status='published')
        capability2 = make_capability(catalog2)
        task2 = make_task(catalog2, capability2, task_key='versioned', validator=RETEST_VALIDATOR)
        self.submit(attempt=make_attempt(task2, self.student, catalog2))
        data = query_learning()
        self.assertEqual(len(data['version_groups']), 2)
        self.assertEqual({row['versions']['catalog_version'] for row in data['version_groups']}, {'v1-test', 'v2'})

    def test_student_task_knowledge_and_source_filters(self):
        self.submit()
        self.submit(student=self.other)
        self.assertEqual(len(query_learning(student_id=self.student.pk)['rows']), 1)
        self.assertEqual(len(query_learning(excluded_student_ids=[self.other.pk])['rows']), 1)
        self.assertEqual(len(query_learning(knowledge_point_id='KP-1')['rows']), 2)
        self.assertEqual(query_learning(knowledge_point_id='not-mapped')['rows'], [])
        self.assertEqual(query_learning(task_key='does-not-exist')['rows'], [])
        self.assertEqual(query_learning(catalog_version='v2')['rows'], [])

    def test_missing_events_are_reported_without_repair_writes(self):
        attempt, submission = self.submit()
        LearningEvent.objects.filter(event_id=f'm6-submit-{submission.submission_id}').delete()
        before = LearningEvent.objects.count()
        detail = attempt_detail(attempt)
        self.assertEqual(detail['reconciliation']['missing_submission_events'], [str(submission.submission_id)])
        self.assertEqual(LearningEvent.objects.count(), before)
        self.assertEqual(detail['overall_status'], 'passed')

    def test_detail_is_allowlisted_and_queries_are_read_only(self):
        attempt, _ = self.submit(payload={**good_payload(), 'answer': 'SECRET_STUDENT_ANSWER'})
        submissions.record_teacher_help(teacher=self.teacher, attempt=attempt, summary='SECRET_TEACHER_NOTES')
        models = [TaskAttempt, SubmissionSnapshot, VerificationResult, VerificationFact, AssistanceRecord, LearningEvent]
        before = {model: list(model.objects.order_by('pk').values()) for model in models}
        detail = attempt_detail(attempt)
        query_learning()
        self.assertNotIn('SECRET', json.dumps(detail))
        for model in models:
            self.assertEqual(before[model], list(model.objects.order_by('pk').values()))

    def test_real_retest_and_correction_ignores_cached_outcome(self):
        new_task = make_task(self.catalog, self.capability, task_key='new-scenario', purpose='retest', validator=RETEST_VALIDATOR)
        self.task.retest_task_keys = [new_task.task_key]
        self.task.save(update_fields=['retest_task_keys'])
        attempt, submission = self.submit()
        assignment, _ = retest.schedule_retest(submission, due_days=0)
        started, _ = retest.claim_retest(assignment, self.student)
        _, completed = self.submit(attempt=started)
        assignment.refresh_from_db()
        self.assertEqual(retest_payload(assignment)['outcome'], 'passed')
        correction.create_correction(
            submission=completed, actor=self.teacher, source='teacher_review', reason='复核未通过',
            changes={'overall_status': 'failed', 'program_status': 'failed'},
        )
        assignment.refresh_from_db()
        self.assertEqual(assignment.outcome, 'passed')
        self.assertEqual(retest_payload(assignment)['outcome'], 'failed')
        detail = attempt_detail(attempt)
        self.assertEqual(detail['retests'][0]['current_result']['version'], 2)
        metrics = self.metrics(task_key=self.task.task_key)
        self.assertEqual(metrics['independent_retest_pass']['numerator'], 0)
        self.assertEqual(metrics['independent_retest_pass']['denominator'], 1)

    def test_missing_external_evidence_never_implies_success(self):
        data = query_learning()
        self.assertEqual(data['status'], 'no_data')
        self.assertEqual(data['source_status']['module3'], 'not_connected')
        self.assertEqual(data['source_status']['module4'], 'not_connected')
        self.assertEqual(data['source_status']['module5'], 'not_connected')
        self.assertEqual(data['source_status']['execution'], 'not_started')
        self.assertEqual(data['source_status']['actual_protection'], 'not_evaluated')

    def test_every_metric_contains_denominator_missing_and_scope(self):
        self.submit()
        for value in self.metrics().values():
            self.assertTrue({'numerator', 'denominator', 'missing', 'window', 'versions', 'source'} <= set(value))
            self.assertEqual(value['versions']['task_version'], self.task.version)
