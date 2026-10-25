"""Isolated module 7 tests.

All tests use synthetic users, tasks, attempts and evidence.  No external model,
network, export service or production quota is called.  Module 6 is represented
by real ``VerificationFact`` rows and shared ``LearningEvent`` rows; the
in-progress module 6 HTTP app is excluded by ``feedback_center.test_settings``.
"""

import random
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from learning_analytics.models import LearningEvent
from learning_map import constants as map_constants
from learning_map.models import (
    Capability,
    CatalogVersion,
    TaskAttempt,
    TaskPackage,
    VerificationFact,
)
from feedback_center import constants
from feedback_center.models import (
    FeedbackAccessLog,
    FeedbackAction,
    FeedbackEventLink,
    FeedbackEvidence,
    FeedbackReview,
    FeedbackSamplingBatch,
    FeedbackTicket,
)
from users.models import CTFUser


def make_catalog(version='v1-feedback-test'):
    return CatalogVersion.objects.create(
        version=version,
        label='模块七测试目录',
        status=map_constants.CATALOG_STATUS_PUBLISHED,
        rule_version='rules-feedback-test',
    )


def make_capability(catalog, stable_id='DS-001'):
    return Capability.objects.create(
        catalog=catalog,
        stable_id=stable_id,
        track=map_constants.TRACK_DATA,
        title='识别与复核',
        observable_objective='能够复核敏感项识别结果',
        dimension=map_constants.DIMENSION_IDENTIFY,
        difficulty=1,
        status=map_constants.CAPABILITY_STATUS_OPEN,
        course_order=10,
    )


def make_task(catalog, capability):
    task = TaskPackage.objects.create(
        catalog=catalog,
        task_key='TASK-DS-CUSTOMER-TABLE-001',
        version='1.0.0-feedback-test',
        title='合成客户表识别与决策回放',
        track=map_constants.TRACK_DATA,
        purpose=map_constants.PURPOSE_VERIFICATION,
        execution_mode=map_constants.EXECUTION_READONLY,
        status=map_constants.TASK_STATUS_FROZEN,
        materials={
            'student_material_refs': ['fixtures/synthetic_customer.csv'],
            'version': 'material-v1',
            'withdrawn': False,
        },
        hints=[{'level': level, 'title': f'第{level}级提示'} for level in (1, 2, 3, 4)],
        student_solution_ref='solutions/student.md',
        validator={'type': 'rules+teacher_rubric', 'version': 'rubric-v1', 'rubric_version': 'rubric-v1'},
        acceptance={'rules': ['依据与范围'], 'rubric_version': 'rubric-v1'},
        retest_task_keys=['TASK-DS-CUSTOMER-TABLE-RETEST'],
        environment_available=True,
        requires_milestone_i=False,
        course_order=10,
    )
    task.capabilities.set([capability])
    return task


def make_attempt(student, catalog, task, capability):
    return TaskAttempt.objects.create(
        student=student,
        catalog=catalog,
        task=task,
        task_version=task.version,
        capability_ids=[capability.stable_id],
        status=map_constants.ATTEMPT_PENDING_VERIFICATION,
        submitted_at=timezone.now(),
        submission_snapshot={
            'request_scope': '110 records',
            'business_purpose': '合成数据教学复核',
            'answers': 'THIS-ANSWER-TEXT-MUST-NOT-BE-COPIED',
        },
        evidence_ref='attempt-evidence-v1',
    )


def full_evidence(category, issue_type, prefix='ev'):
    items = []
    for slot in constants.required_slots(category, issue_type):
        ref = f'{prefix}:{slot}'
        summary = f'{constants.EVIDENCE_SLOT_LABELS.get(slot, slot)}的受控摘要。'
        if slot == constants.EVIDENCE_SLOT_REVIEW_RETEST:
            ref = 'not_retested'
            summary = '未发现复测记录，明确标注未复测；教学效果待验证。'
        elif slot == constants.EVIDENCE_SLOT_HELP_TRACE:
            summary = '提示请求与实际展示分开记录；本次仅作为引用，不新建学习事实。'
        items.append({
            'slot': slot,
            'ref': ref,
            'version': 'v1',
            'summary': summary,
        })
    return items


def feedback_payload(*, category, issue_type, attempt=None, dispute='具体争议：请复核。',
                     client_request_id=None, evidence=None, **overrides):
    payload = {
        'client_request_id': client_request_id or uuid.uuid4().hex,
        'category': category,
        'issue_type': issue_type,
        'dispute': dispute,
        'expected_result': '期望按原始事实重新核对。',
        'reason': '提交人认为原判定与证据不一致。',
        'original_decision_ref': f'original:{category}:{issue_type}',
        'original_decision_version': 'v1',
        'original_decision_snapshot': {'action': 'deny', 'record_count': 110},
        'evidence': full_evidence(category, issue_type) if evidence is None else evidence,
    }
    if attempt is not None:
        payload['attempt_id'] = str(attempt.attempt_id)
    payload.update(overrides)
    return payload


class ModuleSevenBase(TestCase):
    def setUp(self):
        self.student = CTFUser.objects.create_user(username='m7-student', password='Passw0rd!', role='student')
        self.other_student = CTFUser.objects.create_user(username='m7-other', password='Passw0rd!', role='student')
        self.teacher = CTFUser.objects.create_user(username='m7-teacher', password='Passw0rd!', role='teacher')
        self.admin = CTFUser.objects.create_user(username='m7-admin', password='Passw0rd!', role='admin')
        self.catalog = make_catalog()
        self.capability = make_capability(self.catalog)
        self.task = make_task(self.catalog, self.capability)
        self.attempt = make_attempt(self.student, self.catalog, self.task, self.capability)
        self.client = APIClient()
        self.client.force_authenticate(self.student)
        self.teacher_client = APIClient()
        self.teacher_client.force_authenticate(self.teacher)

    def submit(self, *, category=constants.CATEGORY_RECOGNITION, issue_type='false_positive',
               attempt='default', client=None, **overrides):
        if attempt == 'default':
            attempt = self.attempt
        payload = feedback_payload(
            category=category, issue_type=issue_type, attempt=attempt, **overrides,
        )
        return (client or self.client).post('/api/feedback/', payload, format='json')

    def teacher_action(self, feedback_id, action, version, **fields):
        payload = {'action': action, 'expected_version': version}
        payload.update(fields)
        return self.teacher_client.post(
            f'/api/feedback/teacher/{feedback_id}/actions/', payload, format='json',
        )

    def detail(self, feedback_id, client=None):
        return (client or self.client).get(f'/api/feedback/{feedback_id}/')


class CategoryRoutingTests(ModuleSevenBase):
    def test_three_categories_route_and_confirm_with_full_evidence(self):
        cases = [
            (constants.CATEGORY_RECOGNITION, 'false_positive',
             constants.DESTINATION_RECOGNITION_CASE, constants.OWNER_RECOGNITION),
            (constants.CATEGORY_DECISION, 'normal_request_blocked',
             constants.DESTINATION_REPLAY_CASE, constants.OWNER_DECISION),
            (constants.CATEGORY_TEACHING, 'wrong_attribution',
             constants.DESTINATION_MODULE6, constants.OWNER_TEACHER),
        ]
        for category, issue_type, destination, owner_role in cases:
            response = self.submit(
                category=category, issue_type=issue_type,
                dispute=f'{category} 的独立争议',
            )
            self.assertEqual(response.status_code, 201, response.data)
            self.assertEqual(response.data['status'], constants.STATUS_PENDING_FACT_REVIEW)
            self.assertEqual(response.data['handling_destination'], destination)
            self.assertEqual(response.data['owner_role'], owner_role)
            self.assertEqual(response.data['missing_evidence'], [])
            self.assertFalse(response.data['candidate_eligible'])
            self.assertFalse(response.data['production_effects']['export_triggered'])
            self.assertFalse(response.data['rule_activation']['rule_effective'])

            confirmed = self.teacher_action(
                response.data['feedback_id'], 'confirm', response.data['version'],
                reason='依据齐全，确认事实。',
                handling_destination=destination,
            )
            self.assertEqual(confirmed.status_code, 200, confirmed.data)
            self.assertEqual(confirmed.data['status'], constants.STATUS_CONFIRMED)
            self.assertTrue(confirmed.data['candidate_eligible'])
            self.assertEqual(len(confirmed.data['reviews']), 1)

    def test_missing_evidence_goes_pending_and_confirm_is_blocked(self):
        response = self.submit(evidence=[], dispute='缺少证据的识别争议')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['status'], constants.STATUS_PENDING_EVIDENCE)
        self.assertIn(constants.EVIDENCE_SLOT_SAMPLE_LOCATION, response.data['missing_evidence'])
        self.assertFalse(response.data['candidate_eligible'])

        blocked = self.teacher_action(
            response.data['feedback_id'], 'confirm', response.data['version'],
            reason='尝试确认。',
        )
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.data['code'], 'evidence_incomplete')

        missing = response.data['missing_evidence']
        add = self.client.post(
            f"/api/feedback/{response.data['feedback_id']}/evidence/",
            {'items': [{'slot': slot, 'ref': f'new:{slot}', 'version': 'v2', 'summary': '补证摘要'} for slot in missing]},
            format='json',
        )
        self.assertEqual(add.status_code, 200, add.data)
        self.assertEqual(add.data['status'], constants.STATUS_PENDING_FACT_REVIEW)
        self.assertEqual(add.data['missing_evidence'], [])

        confirmed = self.teacher_action(
            response.data['feedback_id'], 'confirm', add.data['version'],
            reason='补证后确认。',
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.data)
        self.assertTrue(confirmed.data['candidate_eligible'])

    def test_normal_request_blocked_stays_decision_and_never_becomes_recognition(self):
        response = self.submit(
            category=constants.CATEGORY_DECISION,
            issue_type='normal_request_blocked',
            dispute='正常请求 110 条被拒绝，但授权事实齐全。',
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['category'], constants.CATEGORY_DECISION)
        self.assertEqual(response.data['issue_type'], 'normal_request_blocked')
        self.assertEqual(response.data['handling_destination'], constants.DESTINATION_REPLAY_CASE)
        self.assertFalse(
            FeedbackTicket.objects.filter(category=constants.CATEGORY_RECOGNITION).exists()
        )

    def test_confirm_requires_mapping_not_only_evidence(self):
        response = self.submit(attempt=None, dispute='无任务关联的识别争议')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['status'], constants.STATUS_PENDING_FACT_REVIEW)
        self.assertTrue(response.data['evidence_complete'])
        self.assertFalse(response.data['mapping_complete'])
        blocked = self.teacher_action(
            response.data['feedback_id'], 'confirm', response.data['version'],
            reason='证据齐全但缺少映射。',
        )
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.data['code'], 'mapping_incomplete')
        self.assertFalse(response.data['candidate_eligible'])


class DedupAndRelationTests(ModuleSevenBase):
    def test_network_retry_is_idempotent_and_conflict_is_rejected(self):
        payload = feedback_payload(
            category=constants.CATEGORY_RECOGNITION,
            issue_type='false_positive',
            attempt=self.attempt,
            client_request_id='retry-key-001',
            dispute='网络重试测试争议',
        )
        first = self.client.post('/api/feedback/', payload, format='json')
        second = self.client.post('/api/feedback/', payload, format='json')
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertFalse(second.data['created'])
        self.assertTrue(second.data['idempotent_replay'])
        self.assertEqual(first.data['feedback_id'], second.data['feedback_id'])
        self.assertEqual(FeedbackTicket.objects.count(), 1)

        changed = dict(payload, dispute='相同提交标识但不同内容')
        conflict = self.client.post('/api/feedback/', changed, format='json')
        self.assertEqual(conflict.status_code, 409)
        self.assertEqual(conflict.data['code'], 'idempotency_conflict')

    def test_same_attempt_duplicate_is_linked_and_cross_category_kept_separate(self):
        first = self.submit(dispute='同一尝试同一争议')
        self.assertEqual(first.status_code, 201)
        duplicate = self.submit(dispute='同一尝试同一争议')
        self.assertEqual(duplicate.status_code, 201)
        self.assertEqual(duplicate.data['status'], constants.STATUS_DUPLICATE)
        self.assertEqual(duplicate.data['duplicate_of'], first.data['feedback_id'])
        self.assertEqual(duplicate.data['duplicate_count'], 0)
        self.assertFalse(duplicate.data['candidate_eligible'])

        main = self.detail(first.data['feedback_id'])
        self.assertEqual(main.data['duplicate_count'], 1)
        self.assertFalse(main.data['candidate_eligible'])

        teaching = self.submit(
            category=constants.CATEGORY_TEACHING,
            issue_type='wrong_attribution',
            dispute='同一尝试的教学反馈',
        )
        self.assertEqual(teaching.status_code, 201)
        self.assertEqual(teaching.data['status'], constants.STATUS_PENDING_FACT_REVIEW)
        relation_types = {item['relation_type'] for item in teaching.data['relations']}
        self.assertIn('same_attempt_cross_category', relation_types)

        confirmed = self.teacher_action(
            first.data['feedback_id'], 'confirm', main.data['version'],
            reason='确认识别问题。',
        )
        self.assertEqual(confirmed.status_code, 200)
        teaching_detail = self.detail(teaching.data['feedback_id'])
        self.assertEqual(teaching_detail.data['status'], constants.STATUS_PENDING_FACT_REVIEW)

        duplicate_confirm = self.teacher_action(
            duplicate.data['feedback_id'], 'confirm', duplicate.data['version'],
            reason='尝试确认重复记录。',
        )
        self.assertEqual(duplicate_confirm.status_code, 409)
        self.assertEqual(duplicate_confirm.data['code'], 'invalid_status')


class WorkflowAndCorrectionTests(ModuleSevenBase):
    def test_manual_correction_preserves_original_review(self):
        response = self.submit(dispute='人工更正留痕测试')
        ticket_id = response.data['feedback_id']
        confirmed = self.teacher_action(
            ticket_id, 'confirm', response.data['version'], reason='第一次确认理由。',
        )
        self.assertEqual(confirmed.status_code, 200)
        first_review_id = confirmed.data['reviews'][0]['review_id']
        first_reason = confirmed.data['reviews'][0]['reason']
        original_snapshot = confirmed.data['original_decision_snapshot']

        revised = self.teacher_action(
            ticket_id, 'revise_review', confirmed.data['version'],
            conclusion=constants.STATUS_REJECTED,
            reason='第二次复核认为证据不足以确认。',
            evidence_refs=['ev:new-check'],
        )
        self.assertEqual(revised.status_code, 200, revised.data)
        self.assertEqual(revised.data['status'], constants.STATUS_REJECTED)
        self.assertEqual(len(revised.data['reviews']), 2)
        reviews = {item['review_id']: item for item in revised.data['reviews']}
        self.assertFalse(reviews[first_review_id]['is_current'])
        self.assertEqual(reviews[first_review_id]['reason'], first_reason)
        self.assertEqual(revised.data['original_decision_snapshot'], original_snapshot)
        self.assertEqual(
            revised.data['reviews'][-1]['supersedes_review_id'],
            first_review_id,
        )

        with self.assertRaises(ValidationError):
            review = FeedbackReview.objects.get(review_id=first_review_id)
            review.reason = '试图覆盖原结论'
            review.save()

    def test_rejected_ticket_reopens_on_new_evidence_and_keeps_original(self):
        response = self.submit(dispute='重开测试争议')
        ticket_id = response.data['feedback_id']
        rejected = self.teacher_action(
            ticket_id, 'reject', response.data['version'], reason='证据不足，驳回。',
        )
        self.assertEqual(rejected.status_code, 200)
        self.assertEqual(rejected.data['status'], constants.STATUS_REJECTED)

        add = self.client.post(
            f'/api/feedback/{ticket_id}/evidence/',
            {'items': [{
                'slot': constants.EVIDENCE_SLOT_SAMPLE_LOCATION,
                'ref': 'new-sample-location',
                'version': 'v2',
                'summary': '新证据：样本定位更正。',
            }]},
            format='json',
        )
        self.assertEqual(add.status_code, 200, add.data)
        self.assertEqual(add.data['status'], constants.STATUS_REOPENED)
        self.assertEqual(add.data['dispute'], '重开测试争议')
        self.assertEqual(len(add.data['reviews']), 1)
        self.assertTrue(add.data['reviews'][0]['is_current'])

        claim = self.teacher_action(
            ticket_id, 'claim', add.data['version'], reason='认领重开工单。',
        )
        self.assertEqual(claim.status_code, 200)
        self.assertEqual(claim.data['status'], constants.STATUS_PENDING_FACT_REVIEW)
        claimed = FeedbackTicket.objects.get(feedback_id=ticket_id)
        claim_action = claimed.actions.get(action='claim')
        self.assertTrue(
            claimed.event_links.filter(action=claim_action, status=constants.EVENT_LINK_LINKED).exists()
        )

        confirmed = self.teacher_action(
            ticket_id, 'confirm', claim.data['version'], reason='新证据后确认。',
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.data)
        self.assertEqual(len(confirmed.data['reviews']), 2)
        self.assertTrue(any(item['conclusion'] == constants.STATUS_REJECTED for item in confirmed.data['reviews']))

    def test_scoring_dispute_routes_to_module6_and_requires_acknowledgement(self):
        before_facts = VerificationFact.objects.count()
        before_score = self.student.score
        response = self.submit(
            category=constants.CATEGORY_TEACHING,
            issue_type='scoring_dispute',
            dispute='评分争议：量表分项与证据不一致。',
        )
        ticket_id = response.data['feedback_id']
        confirmed = self.teacher_action(
            ticket_id, 'confirm', response.data['version'],
            reason='确认评分争议事实。', handling_destination=constants.DESTINATION_MODULE6,
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.data)
        self.assertEqual(confirmed.data['handling_destination'], constants.DESTINATION_MODULE6)

        started = self.teacher_action(
            ticket_id, 'start_handling', confirmed.data['version'],
            handling_action='转模块六复核量表与分项。',
            handling_note='保留原成绩，等待模块六复核。',
            handling_destination=constants.DESTINATION_MODULE6,
        )
        self.assertEqual(started.status_code, 200, started.data)
        self.assertEqual(started.data['status'], constants.STATUS_HANDLING)
        self.assertEqual(len(started.data['referrals']), 1)
        referral_id = started.data['referrals'][0]['referral_id']
        self.assertEqual(started.data['referrals'][0]['status'], constants.REFERRAL_PENDING)

        blocked = self.teacher_action(
            ticket_id, 'handle', started.data['version'],
            handling_note='尝试直接关闭。',
        )
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.data['code'], 'referral_pending')

        ack = self.teacher_action(
            ticket_id, 'ack_referral', started.data['version'],
            referral_id=referral_id,
            referral_status=constants.REFERRAL_ACKNOWLEDGED,
            external_ref='m6-review-001',
            ack_note='模块六已接收评分争议。',
        )
        self.assertEqual(ack.status_code, 200, ack.data)

        handled = self.teacher_action(
            ticket_id, 'handle', ack.data['version'],
            handling_note='模块六已接收，原成绩未由模块七改写。',
        )
        self.assertEqual(handled.status_code, 200, handled.data)
        self.assertEqual(handled.data['status'], constants.STATUS_HANDLED)
        self.assertEqual(handled.data['effect_status'], constants.EFFECT_NOT_ASSESSED)
        self.assertEqual(VerificationFact.objects.count(), before_facts)
        self.assertEqual(self.student.score, before_score)
        self.assertEqual(handled.data['handling_destination'], constants.DESTINATION_MODULE6)

    def test_catalog_or_recommendation_routes_to_module1(self):
        response = self.submit(
            category=constants.CATEGORY_TEACHING,
            issue_type='catalog_or_recommendation',
            dispute='推荐顺序与目录先修不一致。',
        )
        ticket_id = response.data['feedback_id']
        confirmed = self.teacher_action(
            ticket_id, 'confirm', response.data['version'],
            reason='确认目录/推荐问题。', handling_destination=constants.DESTINATION_MODULE1,
        )
        self.assertEqual(confirmed.status_code, 200)
        started = self.teacher_action(
            ticket_id, 'start_handling', confirmed.data['version'],
            handling_action='转模块一核对目录与推荐规则。',
            handling_destination=constants.DESTINATION_MODULE1,
        )
        self.assertEqual(started.status_code, 200, started.data)
        self.assertEqual(started.data['referrals'][0]['destination'], constants.DESTINATION_MODULE1)

    def test_effect_verified_requires_real_retest_fact_and_does_not_change_status(self):
        response = self.submit(dispute='复测效果验证测试')
        ticket_id = response.data['feedback_id']
        confirmed = self.teacher_action(
            ticket_id, 'confirm', response.data['version'], reason='确认问题。',
        )
        started = self.teacher_action(
            ticket_id, 'start_handling', confirmed.data['version'],
            handling_action='补充解释并安排复测。',
            handling_destination=constants.DESTINATION_RECOGNITION_CASE,
        )
        self.assertEqual(started.status_code, 200, started.data)
        handled = self.teacher_action(
            ticket_id, 'handle', started.data['version'], handling_note='处理动作完成。',
        )
        self.assertEqual(handled.status_code, 200)
        self.assertEqual(handled.data['effect_status'], constants.EFFECT_NOT_ASSESSED)

        missing = self.teacher_action(
            ticket_id, 'set_effect', handled.data['version'],
            effect_status=constants.EFFECT_VERIFIED,
        )
        self.assertEqual(missing.status_code, 400)
        self.assertIn('retest_fact_ref', missing.data)

        fact = VerificationFact.objects.create(
            fact_id='m6-retest-fact-001',
            student=self.student,
            catalog=self.catalog,
            capability=self.capability,
            task=self.task,
            task_version=self.task.version,
            attempt_id=self.attempt.attempt_id,
            dimension=map_constants.DIMENSION_IDENTIFY,
            outcome=map_constants.OUTCOME_PASSED,
            independence=map_constants.INDEPENDENCE_INDEPENDENT,
            assistance_level=0,
            assistance_source=map_constants.ASSISTANCE_SOURCE_NONE,
            assistance_shown=False,
            retest_of_attempt_id=self.attempt.attempt_id,
            first_attempt=False,
            evidence_ref='m6-retest-evidence',
            verifier_version='m6-rubric-v1',
            occurred_at=timezone.now(),
        )
        verified = self.teacher_action(
            ticket_id, 'set_effect', handled.data['version'],
            effect_status=constants.EFFECT_VERIFIED,
            effect_note='新场景复测通过。',
            retest_fact_ref=fact.fact_id,
            retest_attempt_ref=str(self.attempt.attempt_id),
        )
        self.assertEqual(verified.status_code, 200, verified.data)
        self.assertEqual(verified.data['status'], constants.STATUS_HANDLED)
        self.assertEqual(verified.data['effect_status'], constants.EFFECT_VERIFIED)


class SamplingTests(ModuleSevenBase):
    def _create_many(self, count=12):
        ids = []
        for index in range(count):
            response = self.submit(dispute=f'抽样测试争议 {index}')
            self.assertEqual(response.status_code, 201, response.data)
            ids.append(response.data['feedback_id'])
        return sorted(ids)

    def test_sampling_is_reproducible_excludes_prior_and_can_census(self):
        ids = self._create_many(12)
        population = sorted(str(item) for item in FeedbackTicket.objects.values_list('feedback_id', flat=True))
        seed = None
        target = None
        for candidate in range(0, 200):
            sample = sorted(random.Random(candidate).sample(population, 3))
            if ids[0] in sample:
                seed = candidate
                target = sample
                break
        self.assertIsNotNone(seed)
        self.assertIn(ids[0], target)

        first = self.teacher_client.post(
            '/api/feedback/teacher/sampling-batches/',
            {
                'scope': {'statuses': [constants.STATUS_PENDING_FACT_REVIEW]},
                'sample_size': 3,
                'random_seed': seed,
                'exclude_prior': False,
                'notes': '可复现随机抽样测试',
            },
            format='json',
        )
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(first.data['population_count'], 12)
        self.assertEqual(sorted(first.data['population_ids']), population)
        first_ids = sorted(item['ticket_id'] for item in first.data['items'])
        self.assertEqual(len(first_ids), 3)
        self.assertIn(ids[0], first_ids)
        self.assertEqual(first.data['random_seed'], seed)
        self.assertEqual(first.data['population_hash'], FeedbackSamplingBatch.objects.get().population_hash)

        second = self.teacher_client.post(
            '/api/feedback/teacher/sampling-batches/',
            {
                'scope': {'statuses': [constants.STATUS_PENDING_FACT_REVIEW]},
                'sample_size': 3,
                'random_seed': seed,
                'exclude_prior': False,
            },
            format='json',
        )
        self.assertEqual(second.status_code, 201)
        self.assertEqual(
            sorted(item['ticket_id'] for item in second.data['items']),
            first_ids,
        )

        third = self.teacher_client.post(
            '/api/feedback/teacher/sampling-batches/',
            {
                'scope': {'statuses': [constants.STATUS_PENDING_FACT_REVIEW]},
                'sample_size': 3,
                'random_seed': seed + 1,
                'exclude_prior': True,
            },
            format='json',
        )
        self.assertEqual(third.status_code, 201, third.data)
        third_ids = {item['ticket_id'] for item in third.data['items']}
        self.assertFalse(third_ids & set(first_ids))

        census = self.teacher_client.post(
            '/api/feedback/teacher/sampling-batches/',
            {
                'scope': {'statuses': [constants.STATUS_PENDING_FACT_REVIEW]},
                'sample_size': 50,
                'random_seed': 7,
                'exclude_prior': False,
            },
            format='json',
        )
        self.assertEqual(census.status_code, 201, census.data)
        self.assertEqual(len(census.data['items']), 12)
        self.assertTrue(all(item['selected_reason'] == constants.SAMPLING_CENSUS for item in census.data['items']))
        self.assertEqual(census.data['method'], constants.SAMPLING_CENSUS)

        risk = self.teacher_client.post(
            '/api/feedback/teacher/sampling-batches/',
            {
                'scope': {'statuses': [constants.STATUS_PENDING_FACT_REVIEW]},
                'sample_size': 2,
                'random_seed': 11,
                'exclude_prior': False,
                'risk_ticket_ids': [ids[0]],
            },
            format='json',
        )
        self.assertEqual(risk.status_code, 201, risk.data)
        reasons = {item['ticket_id']: item['selected_reason'] for item in risk.data['items']}
        self.assertEqual(reasons[ids[0]], constants.SAMPLING_HIGH_RISK)


class PermissionAndAttachmentTests(ModuleSevenBase):
    def test_student_cannot_read_other_feedback_or_use_teacher_queue(self):
        response = self.submit(dispute='权限测试')
        ticket_id = response.data['feedback_id']
        other_client = APIClient()
        other_client.force_authenticate(self.other_student)
        self.assertEqual(other_client.get(f'/api/feedback/{ticket_id}/').status_code, 403)
        self.assertEqual(other_client.get('/api/feedback/teacher/queue/').status_code, 403)
        self.assertEqual(
            other_client.post(
                f'/api/feedback/teacher/{ticket_id}/actions/',
                {'action': 'confirm', 'expected_version': response.data['version'], 'reason': '越权'},
                format='json',
            ).status_code,
            403,
        )
        self.assertIn(APIClient().get(f'/api/feedback/{ticket_id}/').status_code, (401, 403))
        self.assertEqual(self.teacher_client.get('/api/feedback/teacher/queue/').status_code, 200)
        self.assertEqual(self.teacher_client.get(f'/api/feedback/teacher/{ticket_id}/').status_code, 200)
        self.assertTrue(
            FeedbackAccessLog.objects.filter(ticket__feedback_id=ticket_id, allowed=False).exists()
        )

    def test_attachment_access_is_ticket_and_visibility_scoped(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        response = self.submit(dispute='附件权限测试')
        ticket_id = response.data['feedback_id']
        upload = self.client.post(
            f'/api/feedback/{ticket_id}/attachments/',
            {'file': SimpleUploadedFile('evidence.txt', b'controlled evidence', content_type='text/plain')},
            format='multipart',
        )
        self.assertEqual(upload.status_code, 201, upload.data)
        attachment_id = upload.data['attachment_id']

        other_client = APIClient()
        other_client.force_authenticate(self.other_student)
        self.assertEqual(
            other_client.get(f'/api/feedback/{ticket_id}/attachments/{attachment_id}/download/').status_code,
            403,
        )
        self.assertEqual(
            self.client.get(f'/api/feedback/{ticket_id}/attachments/{attachment_id}/download/').status_code,
            200,
        )
        self.assertEqual(
            self.teacher_client.get(f'/api/feedback/{ticket_id}/attachments/{attachment_id}/download/').status_code,
            200,
        )

        staff_upload = self.teacher_client.post(
            f'/api/feedback/{ticket_id}/attachments/',
            {
                'file': SimpleUploadedFile('staff.txt', b'staff only', content_type='text/plain'),
                'visibility': constants.VISIBILITY_STAFF,
            },
            format='multipart',
        )
        self.assertEqual(staff_upload.status_code, 201, staff_upload.data)
        staff_id = staff_upload.data['attachment_id']
        student_detail = self.detail(ticket_id)
        visible_ids = {item['attachment_id'] for item in student_detail.data['attachments']}
        self.assertNotIn(staff_id, visible_ids)
        self.assertEqual(
            self.client.get(f'/api/feedback/{ticket_id}/attachments/{staff_id}/download/').status_code,
            403,
        )
        self.assertEqual(
            self.teacher_client.get(f'/api/feedback/{ticket_id}/attachments/{staff_id}/download/').status_code,
            200,
        )


class EventAndFailureTests(ModuleSevenBase):
    def test_event_sync_failure_is_pending_and_retry_is_idempotent(self):
        with patch('feedback_center.services.events.emit_event', side_effect=RuntimeError('event store down')):
            response = self.submit(dispute='事件同步失败测试')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['event_sync']['status'], 'pending_retry')
        ticket = FeedbackTicket.objects.get(feedback_id=response.data['feedback_id'])
        self.assertTrue(ticket.event_links.filter(status=constants.EVENT_LINK_PENDING).exists())

        retry = self.teacher_client.post(
            '/api/feedback/teacher/reconciliation/retry/',
            {'ticket_id': str(ticket.feedback_id)},
            format='json',
        )
        self.assertEqual(retry.status_code, 200, retry.data)
        ticket.refresh_from_db()
        self.assertFalse(ticket.event_links.filter(status=constants.EVENT_LINK_PENDING).exists())
        self.assertTrue(ticket.event_links.filter(status=constants.EVENT_LINK_LINKED).exists())
        count_before = LearningEvent.objects.filter(metadata__feedback_id=str(ticket.feedback_id)).count()
        self.assertGreaterEqual(count_before, 2)
        again = self.teacher_client.post(
            '/api/feedback/teacher/reconciliation/retry/',
            {'ticket_id': str(ticket.feedback_id)},
            format='json',
        )
        self.assertEqual(again.status_code, 200)
        self.assertEqual(
            LearningEvent.objects.filter(metadata__feedback_id=str(ticket.feedback_id)).count(),
            count_before,
        )

    def test_event_metadata_does_not_contain_dispute_or_answer_text(self):
        secret = 'SECRET-ANSWER-TEXT-MUST-NOT-APPEAR'
        response = self.submit(dispute=f'争议包含 {secret}')
        self.assertEqual(response.status_code, 201)
        ticket = FeedbackTicket.objects.get(feedback_id=response.data['feedback_id'])
        events = LearningEvent.objects.filter(metadata__feedback_id=str(ticket.feedback_id))
        self.assertTrue(events.exists())
        for event in events:
            rendered = str(event.metadata)
            self.assertNotIn(secret, rendered)
            self.assertNotIn('THIS-ANSWER-TEXT-MUST-NOT-BE-COPIED', rendered)
            self.assertEqual(event.metadata.get('source'), 'feedback_center')
            self.assertEqual(event.metadata.get('feedback_id'), str(ticket.feedback_id))

    def test_save_failure_is_retryable_and_does_not_create_ticket(self):
        payload = feedback_payload(
            category=constants.CATEGORY_RECOGNITION,
            issue_type='false_positive',
            attempt=self.attempt,
            client_request_id='save-failure-key',
            dispute='保存失败重试测试',
        )
        with patch(
            'feedback_center.services.submission.FeedbackTicket.objects.create',
            side_effect=DatabaseError('database unavailable'),
        ):
            response = self.client.post('/api/feedback/', payload, format='json')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data['code'], 'save_failed_retry')
        self.assertTrue(response.data['retryable'])
        self.assertFalse(FeedbackTicket.objects.filter(client_request_id='save-failure-key').exists())

        retry = self.client.post('/api/feedback/', payload, format='json')
        self.assertEqual(retry.status_code, 201, retry.data)

    def test_execution_feedback_entry_is_closed(self):
        response = self.submit(
            category=constants.CATEGORY_DECISION,
            issue_type='normal_request_blocked',
            dispute='执行反馈不应开放',
            involves_actual_execution=True,
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data['code'], 'milestone_i_not_open')
        self.assertFalse(FeedbackTicket.objects.exists())
        status_response = APIClient().get('/api/feedback/status/')
        self.assertEqual(status_response.status_code, 200)
        self.assertFalse(status_response.data['execution_feedback_open'])
        self.assertFalse(status_response.data['milestone_i_open'])

    @override_settings(
        FEEDBACK_EXECUTION_OPEN=False,
        FEEDBACK_MILESTONE_I_OPEN=False,
        LEARNING_MAP_AI_ENABLED=False,
        FEEDBACK_CANDIDATE_MANAGEMENT_ENABLED=False,
    )
    def test_core_flow_works_with_models_disabled(self):
        response = self.submit(dispute='全模型停用下的反馈流程')
        self.assertEqual(response.status_code, 201)
        confirmed = self.teacher_action(
            response.data['feedback_id'], 'confirm', response.data['version'], reason='规则人工复核。',
        )
        self.assertEqual(confirmed.status_code, 200)
        started = self.teacher_action(
            response.data['feedback_id'], 'start_handling', confirmed.data['version'],
            handling_action='安排审核任务。',
            handling_destination=constants.DESTINATION_RECOGNITION_CASE,
        )
        self.assertEqual(started.status_code, 200)
        handled = self.teacher_action(
            response.data['feedback_id'], 'handle', started.data['version'],
            handling_note='人工处理完成。',
        )
        self.assertEqual(handled.status_code, 200)
        status_response = APIClient().get('/api/feedback/status/')
        self.assertFalse(status_response.data['ai_required_for_core'])
        self.assertFalse(status_response.data['production_effects']['export_triggered'])


class PriorityAndPhase3Tests(ModuleSevenBase):
    def test_priority_order_uses_conflict_impact_novelty_then_waiting(self):
        first = self.submit(dispute='优先级测试 A')
        second = self.submit(dispute='优先级测试 B')
        third = self.submit(dispute='优先级测试 C')
        # A: low/routine; B: conflict; C: high/new.
        self.teacher_action(
            first.data['feedback_id'], 'triage', first.data['version'],
            impact_level=constants.IMPACT_LOW,
            novelty=constants.NOVELTY_ROUTINE,
            conflict_flag=False,
            reason='低影响已知问题。',
        )
        self.teacher_action(
            second.data['feedback_id'], 'triage', second.data['version'],
            impact_level=constants.IMPACT_LOW,
            novelty=constants.NOVELTY_UNKNOWN,
            conflict_flag=True,
            reason='证据冲突。',
        )
        self.teacher_action(
            third.data['feedback_id'], 'triage', third.data['version'],
            impact_level=constants.IMPACT_HIGH,
            novelty=constants.NOVELTY_NEW,
            conflict_flag=False,
            reason='高影响新问题。',
        )
        queue = self.teacher_client.get('/api/feedback/teacher/queue/')
        self.assertEqual(queue.status_code, 200)
        ids = [item['feedback_id'] for item in queue.data['items']]
        self.assertEqual(ids[:3], [
            second.data['feedback_id'],
            third.data['feedback_id'],
            first.data['feedback_id'],
        ])
        self.assertIn('证据冲突', queue.data['items'][0]['priority_reason'])

    def test_phase3_contract_is_visible_but_candidate_management_is_disabled(self):
        contract = self.teacher_client.get('/api/feedback/teacher/phase3/contracts/')
        self.assertEqual(contract.status_code, 200)
        self.assertFalse(contract.data['enabled'])
        self.assertFalse(contract.data['candidate_management_enabled'])
        self.assertFalse(contract.data['candidate_release_enabled'])
        self.assertIn('issue_group', contract.data)
        self.assertIn('candidate', contract.data)
        self.assertIn('next_tasks', contract.data)
        blocked = self.teacher_client.post(
            '/api/feedback/teacher/phase3/candidates/',
            {
                'title': 'T100 -> T120',
                'issue_group_ids': ['00000000-0000-0000-0000-000000000000'],
                'baseline_config_version': 'T100',
                'candidate_config_version': 'T120',
                'single_changed_factor': 'export_record_limit',
                'rollback_version': 'T100',
            },
            format='json',
        )
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.data['code'], constants.PHASE3_WRITE_DISABLED)
