"""Audit API routes."""

from django.urls import path

from .views import (
    AIAuditLogListView,
    AuditEventListView,
    AuditLedgerEntryListView,
    AuditLedgerVerifyView,
)

urlpatterns = [
    path('events/', AuditEventListView.as_view(), name='audit-events'),
    path('ai-logs/', AIAuditLogListView.as_view(), name='audit-ai-logs'),
    path('ledger/', AuditLedgerEntryListView.as_view(), name='audit-ledger'),
    path('ledger/verify/', AuditLedgerVerifyView.as_view(), name='audit-ledger-verify'),
]
