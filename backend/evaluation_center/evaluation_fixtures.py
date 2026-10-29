"""Versioned synthetic regression inputs. Never sourced from a request or student.

TASK-X is a synthetic teaching-policy exercise, NOT a production export policy.
The reviewed exercise permits up to 120 records; exceeding that needs approval.
These small regression cases are not independent final acceptance or a claim of
production accuracy. Unconnected modules and end-to-end outage tests are excluded.
"""

DATASET_VERSION = 'm8-synthetic-regression/1'
TASK_SCOPE = ['TASK-X@1.0.0']
VIRTUAL_TIME = '2026-10-11T00:10:00+00:00'


def regression_cases():
    cases = []

    def add(case_id, adapter, inputs, expected, group, *, critical=False):
        cases.append({
            'case_id': case_id, 'adapter': adapter, 'input': inputs,
            'expected': expected, 'group': group, 'critical': critical,
            'version': '1', 'task_version': TASK_SCOPE[0], 'role': 'synthetic_student',
            'source': 'synthetic', 'family': adapter, 'split': 'fixed_regression',
            'evidence': {'model_response': None, 'retrieval': [], 'tools': [],
                         'clock': VIRTUAL_TIME, 'random_seed': 0},
        })

    for count in (10, 100, 110, 120, 121, 1000):
        add(f'export-volume-{count}', 'export_rule', {'records': count},
            {'action': 'allow' if count <= 120 else 'require_approval'},
            'data_security', critical=count > 120)
    for violation in ('recipient', 'scope', 'subject', 'forbidden'):
        add(f'export-deny-{violation}', 'export_rule', {'records': 10, 'violation': violation},
            {'action': 'deny'}, 'data_security', critical=True)
    add('export-mask-floor', 'export_rule', {'records': 10, 'protected': True},
        {'action': 'mask'}, 'data_security', critical=True)
    add('export-stateful-replay', 'export_replay', {'scenario': 'unapproved_recipient', 'policy': 'A-v1'},
        {'actions': ['deny'], 'simulated': True}, 'data_security', critical=True)
    for material, withdrawn, unlocked, allowed in (
        ('teacher_answer', False, False, False),
        ('scoring_key', False, False, False),
        ('hidden_verifier', False, False, False),
        ('student_material', True, False, False),
        ('student_analysis', False, False, False),
        ('student_analysis', False, True, True),
        ('student_material', False, False, True),
    ):
        add(f'material-{material}-{withdrawn}-{unlocked}', 'teaching_material',
            {'material_type': material, 'withdrawn': withdrawn, 'analysis_unlocked': unlocked},
            {'allowed': allowed}, 'teaching_effectiveness', critical=not allowed)
    add('material-strip-answer', 'teaching_redaction',
        {'student_material_refs': [{'title': 'Synthetic exercise', 'teacher_answer': 'synthetic-key'}],
         'hidden_verifier': 'synthetic-check'},
        {'student_material_refs': [{'title': 'Synthetic exercise'}]},
        'teaching_effectiveness', critical=True)
    for outcome, independence, reason in (
        ('passed', 'independent', 'independent_pass'),
        ('passed', 'assisted', 'assisted_pass'),
        ('passed', 'unknown', 'help_record_unknown'),
        ('pending_review', 'unknown', 'pending_teacher_review'),
        ('environment_affected', 'unknown', 'environment_affected'),
    ):
        add(f'teaching-fact-{outcome}-{independence}', 'teaching_fact',
            {'outcome': outcome, 'independence': independence}, {'reason': reason},
            'teaching_effectiveness')
    return cases
