"""Isolated tests for module 1.

All tests use synthetic data and the Django test database.  No model, network
or external service is called.  Module 6 is represented by locally posted
verification facts; its real integration is explicitly marked not connected.
"""

import json
import uuid
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from learning_analytics.models import LearningEvent
from learning_map import constants
from learning_map.models import (
    Capability,
    CapabilityState,
    CatalogVersion,
    DataBasisCard,
    DeliveryRegisterItem,
    DiagnosticQuestion,
    KnowledgePoint,
    LegacyLabelMapping,
    PathChangeLog,
    TaskAttempt,
    TaskPackage,
    TeacherAdjustment,
    VerificationFact,
    WSTGMapping,
)
from learning_map.services.catalog import (
    PublishBlocked,
    freeze_catalog,
    publish_catalog,
    publish_readiness,
)
from learning_map.services.diagnosis import submit_diagnosis
from learning_map.services.handoff import FactConflict, ingest_verification_fact
from learning_map.services.interop import export_case_package, export_xapi_statement
from learning_map.services.map import build_capability_map
from learning_map.services.pathing import state_for_student
from learning_map.services.recommendation import compute_recommendation
from users.models import CTFUser

FIXTURE = Path(__file__).resolve().parents[1] / 'fixtures' / 'module1_candidate_v1.json'
CASE_SCHEMA = Path(__file__).resolve().parents[1] / 'fixtures' / 'case-v1p1-cfpackage.schema.json'


def make_catalog(version='v1-test', status=constants.CATALOG_STATUS_PUBLISHED):
    return CatalogVersion.objects.create(
        version=version,
        label=f'测试目录 {version}',
        status=status,
        rule_version='rules-test-v1',
    )


def make_capability(catalog, stable_id='DS-001', track='data', dimension='explain',
                    status=constants.CAPABILITY_STATUS_OPEN, course_order=10,
                    title=None, prerequisites=None):
    capability = Capability.objects.create(
        catalog=catalog,
        stable_id=stable_id,
        track=track,
        title=title or f'能力 {stable_id}',
        observable_objective=f'{stable_id} 的可观察目标',
        dimension=dimension,
        difficulty=1,
        status=status,
        course_order=course_order,
    )
    if prerequisites:
        capability.prerequisites.set(prerequisites)
    return capability


def make_task(catalog, capability, task_key='TASK-1', purpose=constants.PURPOSE_VERIFICATION,
              status=constants.TASK_STATUS_FROZEN, version='1.0.0',
              retest_keys=None, requires_milestone_i=False, environment_available=True,
              prerequisite_capabilities=None, course_order=10):
    task = TaskPackage.objects.create(
        catalog=catalog,
        task_key=task_key,
        version=version,
        title=f'任务 {task_key}',
        track=capability.track,
        purpose=purpose,
        execution_mode=constants.EXECUTION_READONLY,
        status=status,
        materials={'student_material_refs': ['fixtures/synthetic.csv'], 'withdrawn': False},
        hints=[{'level': level, 'title': f'第{level}级'} for level in (1, 2, 3, 4)],
        student_solution_ref='solutions/student.md',
        validator={'type': 'rules+teacher_rubric', 'version': 'v1'},
        acceptance={'rules': ['示例验收']},
        retest_task_keys=retest_keys or [],
        requires_milestone_i=requires_milestone_i,
        environment_available=environment_available,
        course_order=course_order,
    )
    task.capabilities.set([capability])
    if prerequisite_capabilities:
        task.prerequisite_capabilities.set(prerequisite_capabilities)
    return task


def fact_payload(student, catalog, capability, *, fact_id, outcome=constants.OUTCOME_PASSED,
                 independence=constants.INDEPENDENCE_INDEPENDENT, level=0,
                 source=constants.ASSISTANCE_SOURCE_NONE, shown=False,
                 occurred_at=None, task=None, retest_of=None, evidence_ref='ev-1'):
    return {
        'fact_id': fact_id,
        'student': student,
        'catalog_version': catalog.version,
        'capability_id': capability.stable_id,
        'outcome': outcome,
        'independence': independence,
        'assistance_level': level,
        'assistance_source': source,
        'assistance_shown': shown,
        'retest_of_attempt_id': retest_of,
        'task_key': task.task_key if task else None,
        'task_version': task.version if task else None,
        'evidence_ref': evidence_ref,
        'verifier_version': 'verifier-v1',
        'occurred_at': occurred_at or timezone.now(),
    }


class ModuleOneServiceTests(TestCase):
    def setUp(self):
        self.student = CTFUser.objects.create_user(username='s1', password='Passw0rd!', role='student')
        self.teacher = CTFUser.objects.create_user(username='t1', password='Passw0rd!', role='teacher')
        self.admin = CTFUser.objects.create_user(username='a1', password='Passw0rd!', role='admin')
        self.catalog = make_catalog()
        self.cap1 = make_capability(self.catalog, 'DS-001', course_order=10)
        self.cap2 = make_capability(self.catalog, 'DS-002', 'data', 'identify', course_order=20,
                                    prerequisites=[self.cap1])
        self.task1 = make_task(self.catalog, self.cap1, 'TASK-DS-001', course_order=10)
        self.task2 = make_task(self.catalog, self.cap2, 'TASK-DS-002', course_order=20,
                               prerequisite_capabilities=[self.cap1])
        self.retest_task = make_task(
            self.catalog, self.cap1, 'TASK-DS-RETEST', purpose=constants.PURPOSE_RETEST,
            course_order=30, retest_keys=[],
        )
        self.retest_task2 = make_task(
            self.catalog, self.cap2, 'TASK-DS-002-RETEST', purpose=constants.PURPOSE_RETEST,
            course_order=40, retest_keys=[],
        )

    # 1. New student: needs diagnosis, no fabricated weakness.
    def test_new_student_is_needs_diagnosis_and_gets_diagnostic_item(self):
        run = compute_recommendation(student=self.student, catalog=self.catalog)
        self.assertFalse(run.ai_used)
        self.assertFalse(run.output['core_requires_ai'])
        self.assertEqual(run.output['items'][0]['type'], 'diagnostic')
        capability_map = build_capability_map(
            student=self.student, catalog=self.catalog, audience='teacher',
        )
        for track in capability_map['tracks']:
            self.assertEqual(len(track['dimensions']), 4)
        states = {
            capability['state']
            for track in capability_map['tracks']
            for capability in track['capabilities']
        }
        self.assertEqual(states, {constants.STATE_NEEDS_DIAGNOSIS})
        self.assertFalse(CapabilityState.objects.filter(state=constants.STATE_NEEDS_PRACTICE).exists())

    # 2. Deterministic repeat with AI disabled.
    @override_settings(LEARNING_MAP_AI_ENABLED=False)
    def test_recommendation_is_deterministic_with_models_off(self):
        first = compute_recommendation(student=self.student, catalog=self.catalog)
        second = compute_recommendation(student=self.student, catalog=self.catalog)
        self.assertEqual(first.inputs_hash, second.inputs_hash)
        self.assertEqual(json.dumps(first.output, sort_keys=True, ensure_ascii=False),
                         json.dumps(second.output, sort_keys=True, ensure_ascii=False))
        self.assertFalse(first.output['ai_used'])
        self.assertFalse(first.output['core_requires_ai'])

    # 3. Assisted pass preserves assistance and schedules a retest.
    def test_assisted_pass_keeps_assistance_and_retest_due(self):
        occurred = timezone.now() - timedelta(days=4)
        fact, state, changed, created = ingest_verification_fact(fact_payload(
            self.student, self.catalog, self.cap1, fact_id='f-assisted',
            independence=constants.INDEPENDENCE_ASSISTED, level=3,
            source=constants.ASSISTANCE_SOURCE_CARD, shown=True,
            occurred_at=occurred, task=self.task1,
        ))
        self.assertTrue(created)
        self.assertTrue(changed)
        self.assertEqual(state.state, constants.STATE_ASSISTED_PASS)
        self.assertIsNotNone(state.retest_due_at)
        run = compute_recommendation(student=self.student, catalog=self.catalog)
        categories = [item['category'] for item in run.output['items']]
        self.assertIn('due_retest', categories)
        retest_item = next(item for item in run.output['items'] if item['category'] == 'due_retest')
        self.assertEqual(retest_item['task']['purpose'], constants.PURPOSE_RETEST)
        state.refresh_from_db()
        self.assertEqual(state.state, constants.STATE_RETEST_PENDING)

    # 4. Requested but not shown help is not assistance.
    def test_requested_but_not_shown_is_independent(self):
        fact, state, _, _ = ingest_verification_fact(fact_payload(
            self.student, self.catalog, self.cap1, fact_id='f-not-shown',
            independence=constants.INDEPENDENCE_INDEPENDENT, level=0, shown=False,
            task=self.task1,
        ))
        self.assertEqual(state.state, constants.STATE_INDEPENDENT)
        self.assertFalse(fact.assistance_shown)

    # 5. Missing help record stays unknown, never independent.
    def test_unknown_help_is_unknown_state(self):
        _, state, _, _ = ingest_verification_fact(fact_payload(
            self.student, self.catalog, self.cap1, fact_id='f-unknown',
            independence=constants.INDEPENDENCE_UNKNOWN, shown=False,
            task=self.task1,
        ))
        self.assertEqual(state.state, constants.STATE_UNKNOWN)
        self.assertNotEqual(state.state, constants.STATE_INDEPENDENT)

    # 6. Environment failure is not a knowledge error.
    def test_environment_failure_is_not_deduction(self):
        _, state, _, _ = ingest_verification_fact(fact_payload(
            self.student, self.catalog, self.cap1, fact_id='f-env',
            outcome=constants.OUTCOME_ENVIRONMENT_AFFECTED,
            independence=constants.INDEPENDENCE_UNKNOWN,
            task=self.task1,
        ))
        self.assertEqual(state.state, constants.STATE_ENVIRONMENT_AFFECTED)
        self.assertNotEqual(state.state, constants.STATE_NEEDS_PRACTICE)

    # 7. Fact idempotency and conflict.
    def test_fact_is_idempotent_and_conflicts_are_rejected(self):
        payload = fact_payload(self.student, self.catalog, self.cap1, fact_id='f-same', task=self.task1)
        _, first_state, first_changed, created = ingest_verification_fact(payload)
        _, second_state, second_changed, second_created = ingest_verification_fact(payload)
        self.assertTrue(created)
        self.assertFalse(second_created)
        self.assertFalse(second_changed)
        self.assertEqual(VerificationFact.objects.filter(fact_id='f-same').count(), 1)
        self.assertEqual(PathChangeLog.objects.filter(trigger_fact__fact_id='f-same').count(), 1)
        with self.assertRaises(FactConflict):
            changed_payload = dict(payload)
            changed_payload['outcome'] = constants.OUTCOME_FAILED
            ingest_verification_fact(changed_payload)

    # 8. Unmapped legacy labels are excluded from totals.
    def test_unmapped_legacy_label_is_excluded(self):
        LegacyLabelMapping.objects.create(
            catalog=self.catalog, source_system='other', source_label='legacy-x',
            mapping_status=constants.MAPPING_UNMAPPED, note='待确认',
        )
        LegacyLabelMapping.objects.create(
            catalog=self.catalog, source_system='challenge', source_label='challenge-x',
            capability=self.cap1, mapping_status=constants.MAPPING_MAPPED,
        )
        capability_map = build_capability_map(
            student=self.student, catalog=self.catalog, audience='teacher',
        )
        self.assertEqual(capability_map['summary']['legacy_mappings']['unmapped'], 1)
        self.assertEqual(capability_map['summary']['legacy_mappings']['mapped'], 1)
        self.assertTrue(capability_map['summary']['unmapped_excluded_from_capability_totals'])

    # 9. Old versions keep their facts; new version has its own state.
    def test_versioning_keeps_old_facts(self):
        ingest_verification_fact(fact_payload(
            self.student, self.catalog, self.cap1, fact_id='f-v1', task=self.task1,
        ))
        v2 = make_catalog('v2-test')
        cap1_v2 = make_capability(v2, 'DS-001', course_order=10)
        ingest_verification_fact(fact_payload(
            self.student, v2, cap1_v2, fact_id='f-v2', task=None,
            independence=constants.INDEPENDENCE_UNKNOWN,
        ))
        self.assertEqual(VerificationFact.objects.filter(catalog=self.catalog).count(), 1)
        self.assertEqual(VerificationFact.objects.filter(catalog=v2).count(), 1)
        v1_state = state_for_student(self.student, self.catalog)[self.cap1.id]
        v2_state = state_for_student(self.student, v2)[cap1_v2.id]
        self.assertEqual(v1_state.state, constants.STATE_INDEPENDENT)
        self.assertEqual(v2_state.state, constants.STATE_UNKNOWN)

    # 10. Publish blocked until delivery sign-off and review evidence exist.
    def test_publish_blocked_without_signoff(self):
        readiness = publish_readiness(self.catalog)
        self.assertFalse(readiness['ready'])
        codes = {item['code'] for item in readiness['missing']}
        self.assertIn('delivery_item_missing', codes)
        self.catalog.status = constants.CATALOG_STATUS_CANDIDATE
        self.catalog.save()
        with self.assertRaises(PublishBlocked):
            freeze_catalog(self.catalog, actor=self.admin)

    # 11. Task package incompleteness blocks publish even with sign-offs.
    def test_publish_blocked_when_task_package_incomplete(self):
        self._sign_all_delivery_items()
        self._review_domain_evidence()
        self.task2.hints = []
        self.task2.save()
        self.retest_task2.hints = []
        self.retest_task2.save()
        readiness = publish_readiness(self.catalog)
        self.assertFalse(readiness['ready'])
        self.assertIn(
            'task_package_incomplete',
            {item['code'] for item in readiness['missing']},
        )

    # 12. Full sign-off path freezes and publishes with real reviewer rows.
    def test_freeze_and_publish_after_signoff(self):
        self._sign_all_delivery_items()
        self._review_domain_evidence()
        self.catalog.status = constants.CATALOG_STATUS_CANDIDATE
        self.catalog.save()
        readiness = publish_readiness(self.catalog)
        self.assertTrue(readiness['ready'], readiness['missing'])
        frozen = freeze_catalog(self.catalog, actor=self.admin)
        self.assertEqual(frozen.status, constants.CATALOG_STATUS_FROZEN)
        published = publish_catalog(frozen, actor=self.admin)
        self.assertEqual(published.status, constants.CATALOG_STATUS_PUBLISHED)

    # 13. Milestone-I tasks are not recommended.
    def test_milestone_i_task_not_recommended(self):
        self.catalog.status = constants.CATALOG_STATUS_PUBLISHED
        self.catalog.save()
        self.task1.status = constants.TASK_STATUS_WITHDRAWN
        self.task1.save()
        later = make_task(
            self.catalog, self.cap1, 'TASK-AFTER-I',
            status=constants.TASK_STATUS_FROZEN, requires_milestone_i=True,
        )
        self.assertFalse(later.is_recommendable)
        self._complete_diagnosis()
        run = compute_recommendation(student=self.student, catalog=self.catalog)
        task_keys = [item['task']['task_key'] for item in run.output['items'] if item.get('task')]
        self.assertNotIn('TASK-AFTER-I', task_keys)

    # 14. Empty pool is a gap, never a fake task.
    def test_empty_task_pool_returns_gap(self):
        self.task1.status = constants.TASK_STATUS_WITHDRAWN
        self.task1.save()
        self.task2.status = constants.TASK_STATUS_WITHDRAWN
        self.task2.save()
        self._complete_diagnosis()
        run = compute_recommendation(student=self.student, catalog=self.catalog)
        self.assertEqual(run.output['items'], [])
        self.assertTrue(run.output['gaps'])
        self.assertIn('task_pool_empty', {gap['code'] for gap in run.output['gaps']})

    # 15. Teacher assignment is first and carries the rationale.
    def test_teacher_assignment_is_first(self):
        TeacherAdjustment.objects.create(
            catalog=self.catalog, teacher=self.teacher, student=self.student,
            capability=self.cap2, task=self.task2, action='assign_task',
            rationale='按教师观察先补对象识别。',
        )
        run = compute_recommendation(student=self.student, catalog=self.catalog)
        self.assertEqual(run.output['items'][0]['category'], 'teacher_assigned')
        self.assertIn('对象识别', run.output['items'][0]['reason']['text'])

    # 15b. Retest evidence re-evaluates the state; an assisted retest stays assisted.
    def test_retest_evidence_updates_state(self):
        ingest_verification_fact(fact_payload(
            self.student, self.catalog, self.cap1, fact_id='f-first',
            independence=constants.INDEPENDENCE_ASSISTED, level=2,
            source=constants.ASSISTANCE_SOURCE_AI, shown=True,
            task=self.task1,
        ))
        first_attempt = TaskAttempt.objects.create(
            student=self.student, catalog=self.catalog, task=self.task1,
            task_version=self.task1.version, capability_ids=[self.cap1.stable_id],
        )
        _, state, changed, created = ingest_verification_fact(fact_payload(
            self.student, self.catalog, self.cap1, fact_id='f-retest-independent',
            independence=constants.INDEPENDENCE_INDEPENDENT,
            task=self.retest_task, retest_of=first_attempt.attempt_id,
        ))
        self.assertTrue(created)
        self.assertTrue(changed)
        self.assertEqual(state.state, constants.STATE_INDEPENDENT)
        self.assertIsNone(state.retest_due_at)

        self.student2 = CTFUser.objects.create_user(username='s2', password='Passw0rd!', role='student')
        first_attempt2 = TaskAttempt.objects.create(
            student=self.student2, catalog=self.catalog, task=self.task1,
            task_version=self.task1.version, capability_ids=[self.cap1.stable_id],
        )
        ingest_verification_fact(fact_payload(
            self.student2, self.catalog, self.cap1, fact_id='f-first-2',
            independence=constants.INDEPENDENCE_ASSISTED, level=1,
            source=constants.ASSISTANCE_SOURCE_CARD, shown=True,
            task=self.task1,
        ))
        _, state2, _, _ = ingest_verification_fact(fact_payload(
            self.student2, self.catalog, self.cap1, fact_id='f-retest-assisted',
            independence=constants.INDEPENDENCE_ASSISTED, level=1,
            source=constants.ASSISTANCE_SOURCE_TEACHER, shown=True,
            task=self.retest_task, retest_of=first_attempt2.attempt_id,
        ))
        self.assertEqual(state2.state, constants.STATE_ASSISTED_PASS)
        self.assertIsNotNone(state2.retest_due_at)

    # 15c. If the event write fails, the attempt is not left half-saved; retry is safe.
    def test_claim_rolls_back_when_event_write_fails(self):
        self.client = APIClient()
        self.client.force_authenticate(self.student)
        self.client.raise_request_exception = False
        with patch('learning_map.views.emit_event', side_effect=RuntimeError('event store down')):
            failed = self.client.post(f'/api/learning-map/tasks/{self.task1.id}/claim/', {}, format='json')
        self.assertEqual(failed.status_code, 500)
        self.assertFalse(TaskAttempt.objects.filter(student=self.student, task=self.task1).exists())
        retry = self.client.post(f'/api/learning-map/tasks/{self.task1.id}/claim/', {}, format='json')
        self.assertEqual(retry.status_code, 201, retry.content)
        self.assertTrue(TaskAttempt.objects.filter(student=self.student, task=self.task1).exists())

    # 16. Diagnosis is deterministic and unanswered is not weakness.
    def test_diagnosis_scoring_and_unanswered(self):
        DiagnosticQuestion.objects.create(
            catalog=self.catalog, question_key='Q1', track='data', capability=self.cap1,
            dimension='explain', prompt='题目一', options=[{'key': 'A', 'label': 'A'}, {'key': 'B', 'label': 'B'}],
            correct_options=['B'], points=1, status='frozen',
        )
        DiagnosticQuestion.objects.create(
            catalog=self.catalog, question_key='Q2', track='data', capability=self.cap2,
            dimension='identify', prompt='题目二', options=[{'key': 'A', 'label': 'A'}],
            correct_options=['A'], points=1, status='frozen',
        )
        session = submit_diagnosis(
            student=self.student, catalog=self.catalog, goal_track='data',
            answers={'Q1': 'B'},
        )
        self.assertEqual(session.result['capabilities']['DS-001']['result'], constants.DIAGNOSIS_LIKELY_MASTERED)
        self.assertEqual(session.result['capabilities']['DS-002']['result'], constants.DIAGNOSIS_INSUFFICIENT)
        state1 = state_for_student(self.student, self.catalog)[self.cap1.id]
        state2 = state_for_student(self.student, self.catalog)[self.cap2.id]
        self.assertEqual(state1.state, constants.STATE_DIAGNOSED)
        self.assertEqual(state1.diagnosis_result, constants.DIAGNOSIS_LIKELY_MASTERED)
        self.assertEqual(state2.state, constants.STATE_DIAGNOSED)
        self.assertEqual(state2.diagnosis_result, constants.DIAGNOSIS_INSUFFICIENT)

    # 17. Claim records an attempt and a canonical event.
    def test_claim_records_attempt_and_event(self):
        from learning_map.views import ClaimTaskView
        self.client = APIClient()
        self.client.force_authenticate(self.student)
        response = self.client.post(f'/api/learning-map/tasks/{self.task1.id}/claim/', {}, format='json')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(TaskAttempt.objects.filter(student=self.student, task=self.task1).exists())
        event = LearningEvent.objects.get(event_id__startswith='lm-task-claim-')
        self.assertEqual(event.event_type, 'task_claim')
        self.assertEqual(event.metadata['catalog_version'], self.catalog.version)

    # 18. Claim rejects unmet prerequisite.
    def test_claim_rejects_unmet_prerequisite(self):
        self.client = APIClient()
        self.client.force_authenticate(self.student)
        response = self.client.post(f'/api/learning-map/tasks/{self.task2.id}/claim/', {}, format='json')
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.data['code'], 'prerequisite_unmet')

    # 19. CASE export validates against the official CASE v1.1 schema.
    def test_case_export_matches_official_schema(self):
        package = export_case_package(self.catalog)
        self.assertTrue(CASE_SCHEMA.exists(), 'vendored CASE schema missing')
        import jsonschema
        schema = json.loads(CASE_SCHEMA.read_text(encoding='utf-8'))
        jsonschema.validate(package, schema)
        self.assertEqual(package['CFDocument']['caseVersion'], '1.1')
        self.assertTrue(package['CFItems'])
        self.assertTrue(package['CFAssociations'])

    # 20. xAPI statement has no answer text or real identity.
    def test_xapi_statement_shape_and_privacy(self):
        fact, _, _, _ = ingest_verification_fact(fact_payload(
            self.student, self.catalog, self.cap1, fact_id='f-xapi', task=self.task1,
        ))
        statement = export_xapi_statement(fact)
        self.assertEqual(statement['verb']['id'], 'http://adlnet.gov/expapi/verbs/passed')
        self.assertEqual(statement['object']['objectType'], 'Activity')
        self.assertFalse(statement['result']['success'] is None)
        self.assertNotIn('s1', statement['actor']['account']['name'])
        serialized = json.dumps(statement)
        self.assertNotIn('flag', serialized.lower())
        self.assertNotIn('answer', serialized.lower())

    def _complete_diagnosis(self):
        DiagnosticQuestion.objects.create(
            catalog=self.catalog, question_key='Q1', track='data', capability=self.cap1,
            dimension='explain', prompt='题目一', options=[{'key': 'A', 'label': 'A'}],
            correct_options=['A'], points=1, status='frozen',
        )
        submit_diagnosis(
            student=self.student, catalog=self.catalog, goal_track='data',
            answers={'Q1': 'A'},
        )

    def _sign_all_delivery_items(self):
        now = timezone.now()
        for delivery_no, title in constants.REQUIRED_DELIVERY_ITEMS:
            DeliveryRegisterItem.objects.update_or_create(
                delivery_no=delivery_no,
                defaults={
                    'catalog': self.catalog,
                    'title': title,
                    'status': constants.DELIVERY_SIGNED_OFF,
                    'author': self.teacher,
                    'reviewer': self.admin,
                    'attachment_path': f'docs/learning-map/{delivery_no}.md',
                    'signed_off_at': now,
                },
            )

    def _review_domain_evidence(self):
        for index, capability in enumerate(self.catalog.capabilities.filter(
            status=constants.CAPABILITY_STATUS_OPEN,
        ), start=1):
            if capability.track == constants.TRACK_NETWORK:
                WSTGMapping.objects.create(
                    catalog=self.catalog, scenario_id=f'WSTG-TEST-{index:02d}',
                    scenario_title='测试场景', capability=capability,
                    status='reviewed', reviewer=self.teacher,
                    reviewed_at=timezone.now(), wstg_version='4.2',
                )
            else:
                DataBasisCard.objects.create(
                    catalog=self.catalog, card_id=f'BC-TEST-{index:03d}',
                    capability=capability, source_title='测试依据',
                    status='reviewed', owner=self.teacher,
                    verified_date=timezone.localdate(),
                )
        for track in (constants.TRACK_DATA, constants.TRACK_NETWORK):
            if not self.catalog.capabilities.filter(track=track).exists():
                continue
            DiagnosticQuestion.objects.get_or_create(
                catalog=self.catalog, question_key=f'PUB-{track}', version='1.0.0',
                defaults={
                    'track': track,
                    'capability': self.catalog.capabilities.filter(track=track).first(),
                    'dimension': 'explain', 'prompt': '发布校验题',
                    'options': [{'key': 'A', 'label': 'A'}],
                    'correct_options': ['A'], 'status': 'frozen',
                },
            )


class StudentPayloadSanitizationTests(TestCase):
    def setUp(self):
        self.student = CTFUser.objects.create_user(username='sx', password='Passw0rd!', role='student')
        self.teacher = CTFUser.objects.create_user(username='tx', password='Passw0rd!', role='teacher')
        self.catalog = make_catalog()
        self.cap = make_capability(self.catalog, 'DS-001')
        self.task = make_task(self.catalog, self.cap, 'TASK-1')
        DiagnosticQuestion.objects.create(
            catalog=self.catalog, question_key='Q1', track='data', capability=self.cap,
            dimension='explain', prompt='题目', options=[{'key': 'A', 'label': 'A'}],
            correct_options=['A'], points=1, status='frozen',
        )
        PathChangeLog.objects.create(
            student=self.student, catalog=self.catalog, capability=self.cap,
            from_state=constants.STATE_NEEDS_DIAGNOSIS,
            to_state=constants.STATE_DIAGNOSED,
            reason='basic_diagnosis_completed', rule_version='rules-test-v1',
        )
        self.client = APIClient()

    def test_diagnostic_questions_hide_capability_ids(self):
        self.client.force_authenticate(self.student)
        response = self.client.get('/api/learning-map/diagnostic/questions/?track=data')
        self.assertEqual(response.status_code, 200, response.content)
        question = response.data['questions'][0]
        self.assertNotIn('capability_id', question)
        self.assertNotIn('status', question)
        self.assertNotIn('version', question)
        self.assertIn('capability_title', question)

    def test_diagnostic_result_is_display_only(self):
        self.client.force_authenticate(self.student)
        response = self.client.post(
            '/api/learning-map/diagnostic/submit/',
            {'goal_track': 'data', 'answers': {'Q1': 'A'}},
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertNotIn('session_id', response.data)
        self.assertNotIn('rule_version', response.data)
        item = response.data['result']['items'][0]
        self.assertEqual(set(item), {'title', 'result_label'})

    def test_student_changelog_is_label_only(self):
        self.client.force_authenticate(self.student)
        response = self.client.get('/api/learning-map/me/changelog/')
        self.assertEqual(response.status_code, 200, response.content)
        item = response.data['items'][0]
        self.assertEqual(
            set(item),
            {'capability_title', 'from_state_label', 'to_state_label', 'reason_label', 'created_at'},
        )
        self.assertNotIn('fact_id', item)
        self.assertNotIn('rule_version', item)


class SeedCommandTests(TestCase):
    def test_seed_is_idempotent_and_preserves_review_state(self):
        call_command('seed_learning_map', skip_legacy_inspect=True, verbosity=0)
        catalog = CatalogVersion.objects.get(version='v1-candidate')
        self.assertEqual(catalog.capabilities.count(), 20)
        self.assertEqual(catalog.tasks.count(), 4)
        self.assertEqual(catalog.diagnostic_questions.count(), 8)
        task = catalog.tasks.get(task_key='TASK-DS-CUSTOMER-TABLE-001')
        task.status = constants.TASK_STATUS_FROZEN
        task.save(update_fields=['status'])
        call_command('seed_learning_map', skip_legacy_inspect=True, verbosity=0)
        self.assertEqual(CatalogVersion.objects.filter(version='v1-candidate').count(), 1)
        self.assertEqual(catalog.capabilities.count(), 20)
        self.assertEqual(catalog.tasks.count(), 4)
        task.refresh_from_db()
        self.assertEqual(task.status, constants.TASK_STATUS_FROZEN)


class ModuleOneApiTests(TestCase):
    def setUp(self):
        self.student_a = CTFUser.objects.create_user(username='sa', password='Passw0rd!', role='student')
        self.student_b = CTFUser.objects.create_user(username='sb', password='Passw0rd!', role='student')
        self.teacher = CTFUser.objects.create_user(username='teacher', password='Passw0rd!', role='teacher')
        self.admin = CTFUser.objects.create_user(username='admin', password='Passw0rd!', role='admin')
        self.catalog = make_catalog()
        self.cap = make_capability(self.catalog, 'DS-001')
        self.task = make_task(self.catalog, self.cap, 'TASK-1')
        self.client = APIClient()

    def test_student_cannot_read_another_map(self):
        self.client.force_authenticate(self.student_a)
        response = self.client.get(f'/api/learning-map/teacher/students/{self.student_b.id}/map/')
        self.assertEqual(response.status_code, 403)

    def test_student_reads_own_map_without_internal_fields(self):
        self.client.force_authenticate(self.student_a)
        response = self.client.get('/api/learning-map/me/map/')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data['student']['username'], self.student_a.username)
        self.assertNotIn('id', response.data['student'])
        self.assertNotIn('legacy_mappings', response.data['summary'])
        self.assertNotIn('rule_version', response.data['catalog'])
        self.assertNotIn('version', response.data['catalog'])
        self.assertIn('version_label', response.data['catalog'])
        self.assertNotIn('task_versions', response.data['versions'])
        for track in response.data['tracks']:
            self.assertNotIn('counts', track['dimensions'][0])
            for capability in track['capabilities']:
                self.assertNotIn('capability_id', capability)
                self.assertNotIn('evidence_ref', capability)
                self.assertNotIn('reason_code', capability)
                self.assertNotIn('verifier_version', capability)
                self.assertEqual(set(capability['evidence']), {'fact_count', 'latest'})

    def test_teacher_map_keeps_audit_fields(self):
        self.client.force_authenticate(self.teacher)
        response = self.client.get(f'/api/learning-map/teacher/students/{self.student_a.id}/map/')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn('legacy_mappings', response.data['summary'])
        self.assertIn('rule_version', response.data['catalog'])
        capability = response.data['tracks'][0]['capabilities'][0]
        self.assertIn('capability_id', capability)
        self.assertIn('reason_code', capability)
        self.assertIn('task_versions', response.data['versions'])

    def test_student_recommendation_hides_internal_fields(self):
        self.client.force_authenticate(self.student_a)
        response = self.client.get('/api/learning-map/me/recommendations/')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertNotIn('inputs_hash', response.data)
        self.assertNotIn('rule_version', response.data)
        self.assertNotIn('gaps', response.data)
        for item in response.data['items']:
            self.assertNotIn('capability_id', item)
            self.assertFalse('code' in item.get('reason', {}))
            if item['kind'] == 'task':
                self.assertNotIn('task_key', item['task'])
                self.assertNotIn('version', item['task'])
                self.assertIn('version_label', item['task'])

    def test_unpublished_catalog_not_visible_to_student(self):
        CatalogVersion.objects.filter(status=constants.CATALOG_STATUS_PUBLISHED).update(
            status=constants.CATALOG_STATUS_DEPRECATED,
        )
        CatalogVersion.objects.create(
            version='v-candidate', label='候选', status=constants.CATALOG_STATUS_CANDIDATE,
        )
        self.client.force_authenticate(self.student_a)
        response = self.client.get('/api/learning-map/me/map/')
        self.assertEqual(response.status_code, 409, response.content)

    def test_verification_fact_requires_teacher_or_service_token(self):
        self.client.force_authenticate(self.student_a)
        payload = {
            'fact_id': 'api-fact-1', 'student': self.student_a.id,
            'catalog_version': self.catalog.version, 'capability_id': self.cap.stable_id,
            'outcome': 'passed', 'independence': 'independent',
            'occurred_at': timezone.now().isoformat(),
        }
        response = self.client.post('/api/learning-map/verification-facts/', payload, format='json')
        self.assertEqual(response.status_code, 403)

    def test_teacher_can_ingest_fact(self):
        self.client.force_authenticate(self.teacher)
        payload = {
            'fact_id': 'api-fact-2', 'student': self.student_a.id,
            'catalog_version': self.catalog.version, 'capability_id': self.cap.stable_id,
            'outcome': 'passed', 'independence': 'assisted', 'assistance_level': 2,
            'assistance_source': 'card', 'assistance_shown': True,
            'occurred_at': timezone.now().isoformat(),
        }
        response = self.client.post('/api/learning-map/verification-facts/', payload, format='json')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data['state'], constants.STATE_ASSISTED_PASS)
        self.assertFalse(response.data['module6_connected'])

    def test_delivery_signoff_requires_real_reviewer(self):
        item = DeliveryRegisterItem.objects.create(
            catalog=self.catalog, delivery_no='D1-catalog-mapping',
            title='目录', status=constants.DELIVERY_PENDING,
        )
        self.teacher.is_course_owner = True
        self.teacher.save(update_fields=['is_course_owner'])
        self.client.force_authenticate(self.teacher)
        response = self.client.patch(
            '/api/learning-map/delivery-register/D1-catalog-mapping/',
            {'status': 'signed_off', 'attachment_path': 'docs/x.md'},
            format='json',
        )
        self.assertEqual(response.status_code, 400, response.content)
        item.refresh_from_db()
        self.assertEqual(item.status, constants.DELIVERY_PENDING)

    def test_only_admin_can_publish(self):
        self.client.force_authenticate(self.teacher)
        response = self.client.post(f'/api/learning-map/admin/catalog/{self.catalog.version}/publish/')
        self.assertEqual(response.status_code, 403)

    def test_regular_teacher_cannot_read_draft_catalog(self):
        self.client.force_authenticate(self.teacher)
        response = self.client.get('/api/learning-map/teacher/catalog/')
        self.assertEqual(response.status_code, 403, response.content)
        response = self.client.get('/api/learning-map/delivery-register/')
        self.assertEqual(response.status_code, 403, response.content)

    def test_course_owner_can_read_draft_catalog(self):
        self.teacher.is_course_owner = True
        self.teacher.save(update_fields=['is_course_owner'])
        self.client.force_authenticate(self.teacher)
        response = self.client.get('/api/learning-map/teacher/catalog/')
        self.assertEqual(response.status_code, 200, response.content)
        response = self.client.get('/api/learning-map/delivery-register/')
        self.assertEqual(response.status_code, 200, response.content)

    def test_status_endpoint_is_minimal(self):
        response = self.client.get('/api/learning-map/status/')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['ai_required_for_core'])
        self.assertFalse(response.data['execution_open'])
        self.assertNotIn('module6_connected', response.data)
        self.assertNotIn('notes', response.data)
