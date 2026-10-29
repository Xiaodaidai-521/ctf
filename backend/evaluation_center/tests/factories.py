"""Integration fixtures exercise the real persisted evaluation service."""
import uuid

from django.contrib.auth import get_user_model
from django.test import override_settings

from evaluation_center import evaluations
from evaluation_center.models import NonFormalAccount


def completed_report(candidate, *, recommendation='pass'):
    """Return a validated real report reference, keeping the candidate untouched.

    'insufficient' explicitly disables an actual adapter dependency before freezing
    the run; every case is still accounted for. 'pass' is NOT forced: unsupported
    candidates or real failing assertions raise, rather than fabricating approval.
    """
    if recommendation == 'insufficient':
        recommendation = 'insufficient_evidence'
    if recommendation not in ('pass', 'insufficient_evidence'):
        raise ValueError('completed_report supports pass / insufficient_evidence only')
    unavailable = ('export_risk',) if recommendation == 'insufficient_evidence' else ()
    with override_settings(
        EVALUATION_ISOLATED_TESTS=True, ROOT_URLCONF=evaluations.TEST_URLCONF,
        EVALUATION_UNAVAILABLE_DEPENDENCIES=unavailable,
    ):
        actor = get_user_model().objects.create_user(
            username='m8-offline-' + uuid.uuid4().hex, role='admin', password=None)
        NonFormalAccount.objects.create(student=actor, source='offline')
        run = evaluations.create_run(candidate, actor=actor)
        report = evaluations.execute_run(run, actor=actor)
        reference = evaluations.resolve_report(candidate, evaluations.report_reference(report))
        if reference['recommendation'] != recommendation:
            raise AssertionError(f"Real evaluation returned {reference['recommendation']!r}, "
                                 f"not {recommendation!r}: {report.payload['failed_cases']}")
        return reference
