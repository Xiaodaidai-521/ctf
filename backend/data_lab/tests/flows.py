"""Fixed synthetic acceptance answers, used only by backend tests."""
from data_lab.services import submit_review, scan_dto
from data_lab.replay import start_replay, save_judgment
from data_lab.teacher_material import EXPECTED_REPLAYS
from data_lab.verification import target_locations, finding_locations


def complete_evidence(test, lab=None):
    lab = lab or test.lab
    user = lab.attempt.student
    scan = test.scan(lab)
    expected = target_locations({'task_key': lab.attempt.task.task_key, 'scan': scan_dto(scan)})
    for finding in scan.original['findings']:
        scan.refresh_from_db()
        submit_review(user, scan.current_profile_id, {'action': 'confirm' if finding_locations([finding]) <= expected else 'false_positive',
            'finding_id': finding['finding_id'], 'expected_state_version': 1, 'idempotency_key': finding['finding_id'],
            'reason': '根据业务事实逐项核对', 'fact_ids': ['F-PERSON', 'F-DEVICE'], 'basis_ids': ['BC-DS-001']})
    for index, (row, column, start, end, category) in enumerate(sorted(expected - finding_locations(scan.original['findings']))):
        scan.refresh_from_db()
        cell = next(c for c in scan.parsed['cells'] if c['row'] == row and c['column'] == column)
        submit_review(user, scan.current_profile_id, {'action': 'add_manual', 'category_id': category,
            'locations': [{'kind': 'span', 'sheet_id': cell['sheet_id'], 'channel': cell['channel'], 'row': row,
                           'column': column, 'span': {'start': start, 'end': end}}],
            'expected_state_version': 1, 'idempotency_key': f'manual-{index}', 'reason': '补录规则缺口，不提高原覆盖',
            'fact_ids': ['F-COVERAGE'], 'basis_ids': ['BC-DS-001']})
    scan.refresh_from_db()
    replays = []
    for variant, actions in EXPECTED_REPLAYS.items():
        replay = start_replay(user, lab.attempt.attempt_id, {'scenario_variant': variant, 'idempotency_key': variant})
        save_judgment(user, replay.replay_id, {'actions': actions, 'reason': '依据授权与严格大于边界判断',
            'fact_ids': ['F-AUTH'], 'basis_ids': ['BC-DS-001'], 'idempotency_key': variant})
        replays.append(str(replay.replay_id))
    return {'idempotency_key': 'submit', 'scan_id': str(scan.scan_id), 'profile_id': str(scan.current_profile_id),
            'replay_ids': replays, 'explanation': '形态与属性分开，缺少行业目录，交教师复核；只提出保护建议。'}
