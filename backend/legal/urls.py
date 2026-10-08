"""Legal compliance API routes."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ComplianceAgentRunViewSet,
    ContainerAuditViewSet,
    ExerciseFactConfirmView,
    ExerciseFactPreviewView,
    DataProcessingActivityViewSet,
    LegalAnalysisTaskViewSet,
    LegalEvidenceViewSet,
    LegalProtocolVersionViewSet,
    LegalProtocolViewSet,
    LegalReportViewSet,
    LegalRiskFindingViewSet,
    UserConsentRecordViewSet,
    ViolationRecordViewSet,
)

router = DefaultRouter()
router.register(r'protocols', LegalProtocolViewSet, basename='legal-protocol')
router.register(r'protocol-versions', LegalProtocolVersionViewSet, basename='legal-protocol-version')
router.register(r'consents', UserConsentRecordViewSet, basename='legal-consent')
router.register(r'data-processing', DataProcessingActivityViewSet, basename='legal-data-processing')
router.register(r'analysis-tasks', LegalAnalysisTaskViewSet, basename='legal-analysis-task')
router.register(r'risk-findings', LegalRiskFindingViewSet, basename='legal-risk-finding')
router.register(r'evidence', LegalEvidenceViewSet, basename='legal-evidence')
router.register(r'violations', ViolationRecordViewSet, basename='legal-violation')
router.register(r'reports', LegalReportViewSet, basename='legal-report')
router.register(r'agent-runs', ComplianceAgentRunViewSet, basename='legal-agent-run')
router.register(r'container-audits', ContainerAuditViewSet, basename='legal-container-audit')

urlpatterns = [
    path('', include(router.urls)),
    path('exercise-facts/preview/', ExerciseFactPreviewView.as_view(), name='exercise-fact-preview'),
    path('exercise-facts/confirm/', ExerciseFactConfirmView.as_view(), name='exercise-fact-confirm'),
]
