"""Observe only SQLSTATE and HTTP status while running unchanged failed tests."""
from collections import Counter
import json
import os
from unittest.mock import patch


def main():
    if os.environ.get('DATA_SECURITY_ISOLATED_TEST') != '1':
        raise RuntimeError('ISOLATED_TEST_OPT_IN_REQUIRED')
    import django
    django.setup()
    from django.core.management import call_command
    from django.db import DatabaseError
    from django.db.backends.utils import CursorWrapper
    from rest_framework.views import APIView

    sqlstates = Counter()
    http_statuses = Counter()
    execute = CursorWrapper.execute
    finalize = APIView.finalize_response

    def observed_execute(self, sql, params=None):
        try:
            return execute(self, sql, params)
        except DatabaseError as error:
            code = getattr(error.__cause__, 'pgcode', None)
            sqlstates['postgres-outer-join-lock' if code == '0A000' else 'other-db-error'] += 1
            raise

    def observed_finalize(self, request, response, *args, **kwargs):
        result = finalize(self, request, response, *args, **kwargs)
        http_statuses[str(result.status_code)] += 1
        return result

    labels = [
        'feedback_center.tests.test_module7.CategoryRoutingTests.test_missing_evidence_goes_pending_and_confirm_is_blocked',
        'feedback_center.tests.test_module7.WorkflowAndCorrectionTests.test_scoring_dispute_routes_to_module6_and_requires_acknowledgement',
        'challenges.tests.ChallengeProxyAccessTests.test_access_url_does_not_include_reusable_token',
        'challenges.tests.ChallengeProxyAccessTests.test_proxy_accepts_authenticated_owner_without_cookie',
        'challenges.tests.ChallengeProxyAccessTests.test_proxy_rejects_authenticated_non_owner',
        'challenges.tests.ChallengeProxyAccessTests.test_proxy_rejects_unsafe_session_request_without_csrf',
    ]
    try:
        with patch.object(CursorWrapper, 'execute', observed_execute), patch.object(APIView, 'finalize_response', observed_finalize):
            call_command('test', *labels, interactive=False, verbosity=2)
    finally:
        print(json.dumps({'diagnostic_only': True, 'original_assertions_unchanged': True,
                          'sqlstate_counts': dict(sqlstates), 'http_status_counts': dict(http_statuses),
                          'payloads_and_sql_omitted': True}))


if __name__ == '__main__':
    main()
