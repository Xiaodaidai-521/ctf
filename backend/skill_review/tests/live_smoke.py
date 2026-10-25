"""Live HTTP smoke test for module 6 against a running dev server.

This is a local verification script, not a test suite.  It uses synthetic data
and a scratch SQLite database; it refuses to run against anything but
127.0.0.1.
"""

import json
import sys

import requests

BASE = 'http://127.0.0.1:8000'


def session_for(username, password):
    session = requests.Session()
    session.get(f'{BASE}/api/users/csrf/', timeout=10)
    csrf = session.cookies.get('csrftoken')
    response = session.post(
        f'{BASE}/api/users/login/',
        json={'username': username, 'password': password},
        headers={'X-CSRFToken': csrf, 'Referer': BASE},
        timeout=10,
    )
    response.raise_for_status()
    return session, session.cookies.get('csrftoken')


def post(session, csrf, path, payload=None):
    return session.post(
        f'{BASE}{path}',
        json=payload or {},
        headers={'X-CSRFToken': csrf, 'Referer': BASE},
        timeout=20,
    )


def show(label, response):
    body = response.text
    try:
        parsed = json.loads(body)
        summary = json.dumps(parsed, ensure_ascii=False)[:320]
    except ValueError:
        summary = body[:200]
    print(f'[{response.status_code}] {label}: {summary}')


def main():
    student, student_csrf = session_for('student1', 'Passw0rd!')
    teacher, teacher_csrf = session_for('teacher1', 'Passw0rd!')
    owner, owner_csrf = session_for('owner1', 'Passw0rd!')

    submissions = student.get(f'{BASE}/api/skill-review/me/submissions/', timeout=10).json()
    if not submissions['items']:
        print('no submission present; run the demo submission snippet first')
        return 1
    submission_id = submissions['items'][0]['submission_id']

    show('student own submission', student.get(
        f'{BASE}/api/skill-review/submissions/{submission_id}/', timeout=10))
    show('student other-submission guard', student.get(
        f'{BASE}/api/skill-review/teacher/queue/', timeout=10))
    show('teacher queue', teacher.get(f'{BASE}/api/skill-review/teacher/queue/', timeout=10))
    show('regular teacher draft catalog (expect 403)', teacher.get(
        f'{BASE}/api/learning-map/teacher/catalog/', timeout=10))
    show('course owner draft catalog', owner.get(
        f'{BASE}/api/learning-map/teacher/catalog/', timeout=10))
    show('teacher stats', teacher.get(f'{BASE}/api/skill-review/teacher/stats/', timeout=10))
    show('regression cases', teacher.get(
        f'{BASE}/api/skill-review/teacher/regression-cases/', timeout=10))

    manual = teacher.get(f'{BASE}/api/skill-review/teacher/manual-tasks/', timeout=10).json()
    if manual['items']:
        item = manual['items'][0]
        show('teacher claim', post(
            teacher, teacher_csrf,
            f"/api/skill-review/teacher/manual-tasks/{item['task_id']}/claim/",
        ))
        scores = {
            key: {'score': 2, 'evidence': '定位到分项', 'reason': '理由充分'}
            for key in ('basis', 'causal', 'evidence', 'improvement')
        }
        show('teacher review', post(
            teacher, teacher_csrf,
            f"/api/skill-review/teacher/manual-tasks/{item['task_id']}/review/",
            {'scores': scores, 'decision': 'pass', 'remarks': '解释完整'},
        ))

    show('student submission after review', student.get(
        f'{BASE}/api/skill-review/submissions/{submission_id}/', timeout=10))
    show('student retests', student.get(f'{BASE}/api/skill-review/me/retests/', timeout=10))
    show('teacher process due', post(
        teacher, teacher_csrf, '/api/skill-review/teacher/retests/process-due/',
        {'now': '2027-01-01T00:00:00+08:00'},
    ))
    return 0


if __name__ == '__main__':
    sys.exit(main())
