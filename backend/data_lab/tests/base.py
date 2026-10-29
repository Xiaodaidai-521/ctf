from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from learning_map.models import Capability, CatalogVersion, DataBasisCard, TaskAttempt, TaskPackage
from users.models import CTFUser
from data_lab.catalog import BASIS_IDS, CASES, TASK_A, TASK_B, TASK_VERSION, digest
from data_lab.models import CasePackage, LabAttempt


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class LabTestCase(TestCase):
    def setUp(self):
        self.student = CTFUser.objects.create_user(username='d4-student', password='test', role='student')
        self.other = CTFUser.objects.create_user(username='d4-other', password='test', role='student')
        self.teacher = CTFUser.objects.create_user(username='d4-teacher', password='test', role='teacher')
        self.reviewer = CTFUser.objects.create_user(username='d4-reviewer', password='test', role='teacher')
        self.catalog = CatalogVersion.objects.create(version='d4-test-only', label='测试门禁，不是签收', status='published')
        self.capability = Capability.objects.create(catalog=self.catalog, stable_id='DS-005', track='data_security',
            title='定位合成标识', observable_objective='逻辑位置', dimension='identify', status='open')
        for card_id in BASIS_IDS:
            DataBasisCard.objects.create(catalog=self.catalog, card_id=card_id, source_title='测试依据卡',
                source_clause='测试条款', source_version='test-v1', source_url='https://example.invalid/basis', status='reviewed')
        self.cases = {}
        for task_key, spec in CASES.items():
            task = TaskPackage.objects.create(catalog=self.catalog, task_key=task_key, version=TASK_VERSION,
                title=spec['title'], track='data_security', purpose='retest' if task_key == TASK_B else 'practice',
                execution_mode='readonly_decision', status='frozen', validator={'type': 'data_lab', 'version': spec['validator_version']},
                materials={'student_material_refs': [spec['fixture_id']]}, hints=[{'level': i} for i in range(1, 5)],
                acceptance={'rules': ['evidence']}, retest_task_keys=[TASK_B] if task_key == TASK_A else [])
            task.capabilities.add(self.capability)
            material_digest = digest(spec)
            self.cases[task_key] = CasePackage.objects.create(task=task, owner=self.teacher, status='released',
                material_digest=material_digest, author_review={'actor_id': self.teacher.pk, 'at': 'test', 'digest': material_digest},
                second_review={'actor_id': self.reviewer.pk, 'at': 'test', 'digest': material_digest},
                release_checks={k: True for k in ('readonly', 'no_ai', 'events', 'permissions')})
        self.lab = self.new_lab()
        self.client = APIClient()
        self.client.force_authenticate(self.student)

    def new_lab(self, user=None, task_key=TASK_A):
        case = self.cases[task_key]
        attempt = TaskAttempt.objects.create(student=user or self.student, task=case.task, catalog=self.catalog,
            task_version=TASK_VERSION, capability_ids=['DS-005'])
        return LabAttempt.objects.create(attempt=attempt, case=case)

    def basis(self, lab=None):
        from data_lab.services import save_basis
        lab = lab or self.lab
        return save_basis(lab.attempt.student, lab.attempt.attempt_id, {
            'entity_category': '合成形态', 'personal_information': '假设可识别性需查证',
            'data_classification': '未确定行业目录', 'uncertainties': '请教师复核目录',
            'fact_ids': ['F-PURPOSE'], 'basis_ids': ['BC-DS-001']})

    def scan(self, lab=None, key='scan-1'):
        from data_lab.services import start_scan
        lab = lab or self.lab
        self.basis(lab)
        scan = start_scan(lab.attempt.student, lab.attempt.attempt_id, {
            'fixture_id': CASES[lab.case.task.task_key]['fixture_id'], 'idempotency_key': key})
        self.assertEqual(scan.status, 'completed', scan.failure_code)
        return scan
