"""Admin evaluation endpoints; token adapter is registered ONLY in test_urls."""
import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import evaluations
from .models import EvaluationReport, EvaluationRun
from .permissions import CanEvaluate


def _error(exc):
    return Response({'detail': str(exc), 'code': exc.code}, status=400)


def _run_payload(run):
    # Unsupported configurations can contain credentials. Keep the full frozen
    # contents in the server record; the read API exposes digests, not secrets.
    manifest = {**run.frozen, 'binding': {
        key: value for key, value in run.frozen['binding'].items()
        if key not in ('baseline_config', 'candidate_config')
    }}
    return {'run_id': str(run.run_id), 'state': run.state, 'stop_reason': run.stop_reason,
            'manifest_summary': manifest, 'manifest_digest': run.manifest_digest,
            'completed_cases': run.case_results.count()}


def _get_run(run_id):
    try:
        return EvaluationRun.objects.get(run_id=run_id)
    except (EvaluationRun.DoesNotExist, ValidationError, ValueError) as exc:
        raise evaluations.EvaluationError('运行不存在。') from exc


def _strict_data(data, allowed):
    if not isinstance(data, dict) or set(data) - set(allowed):
        raise evaluations.EvaluationError('不允许自带案例输入、角色、地址或未知字段。')


class EvaluationRunsView(APIView):
    permission_classes = [CanEvaluate]

    def get(self, request):
        # Metadata only: results are paged by requesting a specific report.
        runs = EvaluationRun.objects.select_related('candidate').order_by('-created_at')[:100]
        return Response([{'run_id': str(run.run_id), 'state': run.state,
                          'candidate_id': str(run.candidate.candidate_id),
                          'dataset_version': run.frozen['dataset_version']} for run in runs])

    def post(self, request):
        from feedback_center.models import FeedbackCandidate
        try:
            _strict_data(request.data, ('candidate_id', 'purpose', 'max_cases', 'max_duration_ms', 'dataset_version'))
            try:
                candidate = FeedbackCandidate.objects.get(candidate_id=request.data.get('candidate_id'))
            except (FeedbackCandidate.DoesNotExist, ValidationError, ValueError) as exc:
                raise evaluations.EvaluationError('候选不存在。') from exc
            options = {key: request.data[key] for key in ('purpose', 'max_cases', 'max_duration_ms', 'dataset_version')
                       if key in request.data}
            run = evaluations.create_run(candidate, actor=request.user, **options)
            return Response(_run_payload(run), status=201)
        except evaluations.EvaluationError as exc:
            return _error(exc)


class EvaluationRunView(APIView):
    permission_classes = [CanEvaluate]

    def get(self, request, run_id):
        try:
            return Response(_run_payload(_get_run(run_id)))
        except evaluations.EvaluationError as exc:
            return _error(exc)


class EvaluationExecuteView(APIView):
    permission_classes = [CanEvaluate]

    def post(self, request, run_id):
        try:
            _strict_data(request.data, ())
            report = evaluations.execute_run(_get_run(run_id), actor=request.user)
            return Response({'reference': evaluations.report_reference(report), 'report': report.payload})
        except evaluations.EvaluationError as exc:
            return _error(exc)


class EvaluationInterruptView(APIView):
    permission_classes = [CanEvaluate]

    def post(self, request, run_id):
        try:
            _strict_data(request.data, ())
            report = evaluations.interrupt_run(_get_run(run_id), actor=request.user)
            return Response({'reference': evaluations.report_reference(report), 'report': report.payload})
        except evaluations.EvaluationError as exc:
            return _error(exc)


class EvaluationReportView(APIView):
    permission_classes = [CanEvaluate]

    def get(self, request, report_id):
        try:
            try:
                report = EvaluationReport.objects.get(report_id=report_id)
            except (EvaluationReport.DoesNotExist, ValidationError, ValueError) as exc:
                raise evaluations.EvaluationError('报告不存在。') from exc
            report = evaluations.validate_report(report)
            return Response({'reference': evaluations.report_reference(report), 'report': report.payload})
        except evaluations.EvaluationError as exc:
            return _error(exc)


class EvaluationServiceAuthentication(BaseAuthentication):
    """Dedicated constant-time token, with server-selected offline admin identity."""

    def authenticate_header(self, request):
        return 'Evaluation'

    def authenticate(self, request):
        if (getattr(settings, 'EVALUATION_TEST_ADAPTER_ENABLED', False) is not True or
                getattr(settings, 'EVALUATION_ISOLATED_TESTS', False) is not True or
                settings.ROOT_URLCONF != evaluations.TEST_URLCONF):
            raise AuthenticationFailed('隔离评测适配器未启用。')
        expected = getattr(settings, 'EVALUATION_SERVICE_TOKEN', '')
        supplied = request.headers.get('Authorization', '')
        token = supplied[len('Evaluation '):] if supplied.startswith('Evaluation ') else ''
        if (not isinstance(expected, str) or not expected or
                not secrets.compare_digest(token.encode('utf-8'), expected.encode('utf-8'))):
            raise AuthenticationFailed('评测服务令牌无效。')
        account = get_user_model().objects.filter(
            pk=getattr(settings, 'EVALUATION_SERVICE_ACCOUNT_ID', None)).first()
        try:
            evaluations.require_isolated_write(account)
        except evaluations.EvaluationError as exc:
            raise AuthenticationFailed(str(exc)) from exc
        return account, None


class EvaluationAdapterView(EvaluationExecuteView):
    authentication_classes = [EvaluationServiceAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            _strict_data(request.data, ('run_id',))
            report = evaluations.execute_run(_get_run(request.data.get('run_id')), actor=request.user)
            return Response({'reference': evaluations.report_reference(report), 'report': report.payload})
        except evaluations.EvaluationError as exc:
            return _error(exc)
