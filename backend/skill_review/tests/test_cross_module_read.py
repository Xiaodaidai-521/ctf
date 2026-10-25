"""Cross-module read verification: module 7 must see real module-6 records.

This test lives in module 6 because it asserts module 6's own tables are
readable through module 7's documented read-only adapter.  It writes nothing
to module 7's tables.
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from feedback_center.services.module6 import collect_attempt_context
from learning_map import constants as map_constants
from learning_map.models import Capability, CatalogVersion, TaskAttempt, TaskPackage
from skill_review import constants
from skill_review.models import RetestAssignment
from skill_review.services import submissions as submission_service
from skill_review.services import verification
from users.models import CTFUser
from skill_review.tests.test_module6 import DATA_VALIDATOR, good_payload, make_attempt, make_catalog, make_capability, make_task


class Module7ReadsModule6Tests(TestCase):
    def setUp(self):
        self.student = CTFUser.objects.create_user(username='m6s', password='Passw0rd!', role='student')
        self.teacher = CTFUser.objects.create_user(username='m6t', password='Passw0rd!', role='teacher')
        self.catalog = make_catalog()
        self.capability = make_capability(self.catalog)
        self.task = make_task(self.catalog, self.capability)
        self.retest_task = make_task(
            self.catalog, self.capability, task_key='TASK-DS-RETEST', purpose='retest',
            validator={
                'version': 'm6-rules-v1-candidate',
                'type': 'structured_rules',
                'manual_required': False,
                'checks': [{'id': 'basis', 'field': 'basis_clause', 'required': True}],
            },
        )
        self.task.retest_task_keys = ['TASK-DS-RETEST']
        self.task.save(update_fields=['retest_task_keys'])
        self.attempt = make_attempt(self.task, self.student, self.catalog)

    def test_module7_sees_assistance_result_and_retest(self):
        record = submission_service.request_hint(
            student=self.student, attempt=self.attempt, level=3,
            source=constants.ASSISTANCE_SOURCE_AI,
        )
        submission_service.show_hint(record=record)
        submission, _ = submission_service.create_submission(
            student=self.student, attempt=self.attempt,
            client_submission_id='m7-see-1', payload=good_payload(),
        )
        manual = submission.manual_tasks.first()
        scores = {
            key: {'score': 2, 'evidence': '定位', 'reason': '理由'}
            for key, _ in constants.RUBRIC_ITEMS
        }
        verification.review_manual_task(
            manual, reviewer=self.teacher, scores=scores,
            decision='pass', remarks='解释完整',
        )
        from skill_review.services import review

        review.upsert_review_card(
            student=self.student, submission=submission,
            data={
                'original_task_summary': '客户表', 'error_evidence': '漏标',
                'judgment_at_time': '只看字段名', 'correct_basis': '个保法',
                'next_verification': '换场景', 'student_reflection': '先核对',
            },
            complete=True,
        )

        context = collect_attempt_context(self.attempt)

        self.assertTrue(context['skill_review_connected'])
        self.assertEqual(context['hint_record_status'], 'present')
        self.assertTrue(context['help_shown'])
        self.assertTrue(context['assistance_records'])
        self.assertEqual(context['assistance_records'][0]['level'], 3)
        self.assertTrue(context['verification_results'])
        self.assertEqual(
            context['verification_results'][0]['overall_status'],
            constants.OVERALL_PASSED,
        )
        self.assertEqual(
            context['verification_results'][0]['independence'],
            constants.INDEPENDENCE_ASSISTED,
        )
        self.assertTrue(context['retest_present'])
        self.assertTrue(context['retest_assignments'])
        self.assertEqual(context['retest_assignments'][0]['status'], constants.RETEST_SCHEDULED)
        self.assertTrue(context['verification_facts'])
        self.assertEqual(context['verification_facts'][0]['independence'], 'assisted')

    def test_module7_reports_not_connected_when_no_records(self):
        context = collect_attempt_context(self.attempt)
        self.assertFalse(context['verification_results'])
        self.assertFalse(context['assistance_records'])
        self.assertEqual(context['hint_record_status'], 'unknown')
        self.assertFalse(context['help_shown'])
