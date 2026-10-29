"""Closed URL set: no teaching/source/production execution endpoints."""
from django.conf import settings
from django.urls import path

from .evaluation_views import (
    EvaluationAdapterView, EvaluationExecuteView, EvaluationInterruptView,
    EvaluationReportView, EvaluationRunsView, EvaluationRunView,
)

urlpatterns = [
    path('api/evaluation/runs/', EvaluationRunsView.as_view(), name='evaluation-runs'),
    path('api/evaluation/runs/<uuid:run_id>/', EvaluationRunView.as_view(), name='evaluation-run'),
    path('api/evaluation/runs/<uuid:run_id>/execute/', EvaluationExecuteView.as_view(), name='evaluation-execute'),
    path('api/evaluation/runs/<uuid:run_id>/interrupt/', EvaluationInterruptView.as_view(), name='evaluation-interrupt'),
    path('api/evaluation/reports/<uuid:report_id>/', EvaluationReportView.as_view(), name='evaluation-report'),
]
if (getattr(settings, 'EVALUATION_ISOLATED_TESTS', False) is True and
        getattr(settings, 'EVALUATION_TEST_ADAPTER_ENABLED', False) is True):
    urlpatterns.append(path('api/evaluation/adapter/', EvaluationAdapterView.as_view(), name='evaluation-adapter'))
