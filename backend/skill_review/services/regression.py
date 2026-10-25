"""Fixed regression examples handed to module 8.

These are synthetic expectations, not real student outcomes.  They freeze the
first-phase rules that module 8 should protect when scoring or workflow code
changes.
"""

from .. import constants


def regression_cases():
    return {
        'version': 'm6-regression-v1',
        'generated_for': 'module8',
        'aisles': ['manual_pending', 'independence', 'correction', 'retest_pool'],
        'cases': [
            {
                'case_id': 'M6-REG-001',
                'title': '程序通过但开放题待评',
                'input': {
                    'program_status': constants.PROGRAM_PASSED,
                    'manual_required': True,
                    'manual_status': constants.MANUAL_PENDING,
                    'independence': constants.INDEPENDENCE_INDEPENDENT,
                },
                'expected': {
                    'overall_status': constants.OVERALL_PENDING_MANUAL,
                    'auto_total_score': None,
                },
            },
            {
                'case_id': 'M6-REG-002',
                'title': '提示请求未展示',
                'input': {
                    'hint_requested': True,
                    'hint_shown': False,
                    'teacher_help': False,
                    'analysis_exposure': False,
                },
                'expected': {'independence': constants.INDEPENDENCE_INDEPENDENT},
            },
            {
                'case_id': 'M6-REG-003',
                'title': '第 3 级提示展示后重交',
                'input': {
                    'hint_level': 3,
                    'hint_shown': True,
                    'resubmitted': True,
                },
                'expected': {
                    'independence': constants.INDEPENDENCE_ASSISTED,
                    'assistance_level': 3,
                },
            },
            {
                'case_id': 'M6-REG-004',
                'title': '教师更正通过为未通过',
                'input': {
                    'original_overall': constants.OVERALL_PASSED,
                    'correction_manual_decision': 'fail',
                    'source': constants.CORRECTION_SOURCE_TEACHER,
                },
                'expected': {
                    'new_version_created': True,
                    'original_preserved': True,
                    'module1_notice': 'sent_or_retry',
                    'module7_notice': 'not_connected',
                    'module8_notice': 'not_connected',
                },
            },
            {
                'case_id': 'M6-REG-005',
                'title': '复测题池无新场景',
                'input': {
                    'original_task_excluded': True,
                    'attempted_tasks_excluded': True,
                    'exposed_tasks_excluded': True,
                    'candidate_count': 0,
                },
                'expected': {
                    'retest_status': constants.RETEST_PENDING_ITEM,
                    'fake_task_created': False,
                },
            },
        ],
        'notes': [
            '这些案例只验证规则和流程，不代表真实学习保持效果。',
            '执行能力在首期固定为未开展/未评估，不进入本组分子或分母。',
        ],
    }
