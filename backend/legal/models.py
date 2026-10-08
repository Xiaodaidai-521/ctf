"""Models for legal compliance business workflows."""

from django.conf import settings
from django.db import models


class LegalProtocol(models.Model):
    """A protocol, privacy notice, terms document, or compliance policy."""

    PROTOCOL_TYPE_CHOICES = [
        ('privacy_policy', 'Privacy policy'),
        ('terms', 'Terms of service'),
        ('data_processing', 'Data processing notice'),
        ('training_notice', 'Training notice'),
        ('other', 'Other'),
    ]

    key = models.SlugField(max_length=80, unique=True, verbose_name='Protocol key')
    name = models.CharField(max_length=200, verbose_name='Name')
    protocol_type = models.CharField(
        max_length=30,
        choices=PROTOCOL_TYPE_CHOICES,
        default='other',
        verbose_name='Protocol type',
    )
    description = models.TextField(blank=True, verbose_name='Description')
    is_active = models.BooleanField(default=True, verbose_name='Active')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created at')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Updated at')

    class Meta:
        verbose_name = 'Legal protocol'
        verbose_name_plural = 'Legal protocols'
        ordering = ['key']

    def __str__(self):
        return self.name


class LegalProtocolVersion(models.Model):
    """Immutable versioned content for a legal protocol."""

    protocol = models.ForeignKey(
        LegalProtocol,
        on_delete=models.CASCADE,
        related_name='versions',
        verbose_name='Protocol',
    )
    version = models.CharField(max_length=50, verbose_name='Version')
    title = models.CharField(max_length=200, verbose_name='Title')
    content = models.TextField(verbose_name='Content')
    content_hash = models.CharField(max_length=64, db_index=True, verbose_name='Content hash')
    effective_at = models.DateTimeField(null=True, blank=True, verbose_name='Effective at')
    published_at = models.DateTimeField(null=True, blank=True, verbose_name='Published at')
    source_url = models.URLField(blank=True, verbose_name='Source URL')
    is_published = models.BooleanField(default=False, verbose_name='Published')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_legal_protocol_versions',
        verbose_name='Created by',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created at')

    class Meta:
        verbose_name = 'Legal protocol version'
        verbose_name_plural = 'Legal protocol versions'
        ordering = ['protocol', '-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['protocol', 'version'],
                name='unique_legal_protocol_version',
            ),
        ]

    def __str__(self):
        return f'{self.protocol.key} v{self.version}'


class UserConsentRecord(models.Model):
    """Evidence that a user accepted a specific protocol version."""

    CONSENT_METHOD_CHOICES = [
        ('clickwrap', 'Clickwrap'),
        ('checkbox', 'Checkbox'),
        ('admin_import', 'Admin import'),
        ('api', 'API'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='legal_consents',
        verbose_name='User',
    )
    protocol_version = models.ForeignKey(
        LegalProtocolVersion,
        on_delete=models.PROTECT,
        related_name='consent_records',
        verbose_name='Protocol version',
    )
    consent_method = models.CharField(
        max_length=30,
        choices=CONSENT_METHOD_CHOICES,
        default='clickwrap',
        verbose_name='Consent method',
    )
    evidence = models.JSONField(default=dict, blank=True, verbose_name='Evidence')
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name='IP address')
    user_agent = models.CharField(max_length=500, blank=True, verbose_name='User-Agent')
    ledger_entry = models.ForeignKey(
        'audit.AuditLedgerEntry',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='consent_records',
        verbose_name='Ledger entry',
    )
    signed_at = models.DateTimeField(auto_now_add=True, verbose_name='Signed at')

    class Meta:
        verbose_name = 'User consent record'
        verbose_name_plural = 'User consent records'
        ordering = ['-signed_at']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'protocol_version'],
                name='unique_user_protocol_consent',
            ),
        ]

    def __str__(self):
        return f'{self.user_id} accepted {self.protocol_version_id}'


class DataProcessingActivity(models.Model):
    """Data processing ledger entry."""

    PROCESSING_TYPE_CHOICES = [
        ('collect', 'Collect'),
        ('store', 'Store'),
        ('use', 'Use'),
        ('share', 'Share'),
        ('delete', 'Delete'),
        ('export', 'Export'),
    ]

    RISK_LEVEL_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]

    name = models.CharField(max_length=200, verbose_name='Name')
    processing_type = models.CharField(max_length=30, choices=PROCESSING_TYPE_CHOICES)
    data_categories = models.JSONField(default=list, blank=True, verbose_name='Data categories')
    purpose = models.TextField(verbose_name='Purpose')
    legal_basis = models.CharField(max_length=200, blank=True, verbose_name='Legal basis')
    processor = models.CharField(max_length=200, blank=True, verbose_name='Processor')
    recipient = models.CharField(max_length=200, blank=True, verbose_name='Recipient')
    retention_period = models.CharField(max_length=100, blank=True, verbose_name='Retention period')
    risk_level = models.CharField(
        max_length=20,
        choices=RISK_LEVEL_CHOICES,
        default='low',
        verbose_name='Risk level',
    )
    metadata = models.JSONField(default=dict, blank=True, verbose_name='Metadata')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_data_processing_activities',
        verbose_name='Created by',
    )
    ledger_entry = models.ForeignKey(
        'audit.AuditLedgerEntry',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='data_processing_activities',
        verbose_name='Ledger entry',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created at')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Updated at')

    class Meta:
        verbose_name = 'Data processing activity'
        verbose_name_plural = 'Data processing activities'
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class LegalAnalysisTask(models.Model):
    """Compliance analysis task submitted by an admin or teacher."""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    SOURCE_TYPE_CHOICES = [
        ('manual', 'Manual'),
        ('challenge', 'Challenge'),
        ('article', 'Article'),
        ('resource', 'Resource'),
        ('data_processing', 'Data processing activity'),
        ('protocol', 'Protocol'),
    ]

    title = models.CharField(max_length=200, verbose_name='Title')
    source_type = models.CharField(max_length=30, choices=SOURCE_TYPE_CHOICES, default='manual')
    source_object_id = models.PositiveIntegerField(null=True, blank=True, verbose_name='Source object ID')
    input_text = models.TextField(blank=True, verbose_name='Input text')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_legal_analysis_tasks',
        verbose_name='Created by',
    )
    result_summary = models.TextField(blank=True, verbose_name='Result summary')
    error_message = models.TextField(blank=True, verbose_name='Error message')
    metadata = models.JSONField(default=dict, blank=True, verbose_name='Metadata')
    started_at = models.DateTimeField(null=True, blank=True, verbose_name='Started at')
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name='Completed at')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created at')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Updated at')

    class Meta:
        verbose_name = 'Legal analysis task'
        verbose_name_plural = 'Legal analysis tasks'
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class LegalRiskFinding(models.Model):
    """Risk finding generated by analysis, rules, or manual review."""

    SEVERITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]

    STATUS_CHOICES = [
        ('open', 'Open'),
        ('accepted', 'Accepted'),
        ('mitigated', 'Mitigated'),
        ('false_positive', 'False positive'),
    ]

    task = models.ForeignKey(
        LegalAnalysisTask,
        on_delete=models.CASCADE,
        related_name='risk_findings',
        verbose_name='Analysis task',
    )
    title = models.CharField(max_length=200, verbose_name='Title')
    description = models.TextField(verbose_name='Description')
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='medium')
    likelihood = models.FloatField(default=0.5, verbose_name='Likelihood')
    impact = models.FloatField(default=0.5, verbose_name='Impact')
    score = models.FloatField(default=0, verbose_name='Score')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    recommendation = models.TextField(blank=True, verbose_name='Recommendation')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created at')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Updated at')

    class Meta:
        verbose_name = 'Legal risk finding'
        verbose_name_plural = 'Legal risk findings'
        ordering = ['-score', '-created_at']

    def __str__(self):
        return self.title


class LegalEvidence(models.Model):
    """Evidence supporting a legal analysis, risk finding, violation, or report."""

    EVIDENCE_TYPE_CHOICES = [
        ('legal_clause', 'Legal clause'),
        ('legal_case', 'Legal case'),
        ('audit_event', 'Audit event'),
        ('ledger_entry', 'Ledger entry'),
        ('platform_object', 'Platform object'),
        ('manual', 'Manual'),
    ]

    task = models.ForeignKey(
        LegalAnalysisTask,
        on_delete=models.CASCADE,
        related_name='evidence_items',
        null=True,
        blank=True,
        verbose_name='Analysis task',
    )
    risk_finding = models.ForeignKey(
        LegalRiskFinding,
        on_delete=models.CASCADE,
        related_name='evidence_items',
        null=True,
        blank=True,
        verbose_name='Risk finding',
    )
    evidence_type = models.CharField(max_length=30, choices=EVIDENCE_TYPE_CHOICES)
    object_type = models.CharField(max_length=100, blank=True, verbose_name='Object type')
    object_id = models.CharField(max_length=100, blank=True, verbose_name='Object ID')
    title = models.CharField(max_length=200, verbose_name='Title')
    excerpt = models.TextField(blank=True, verbose_name='Excerpt')
    source_url = models.URLField(blank=True, verbose_name='Source URL')
    relevance_score = models.FloatField(default=0, verbose_name='Relevance score')
    metadata = models.JSONField(default=dict, blank=True, verbose_name='Metadata')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created at')

    class Meta:
        verbose_name = 'Legal evidence'
        verbose_name_plural = 'Legal evidence'
        ordering = ['-relevance_score', 'id']

    def __str__(self):
        return self.title


class ViolationRecord(models.Model):
    """Compliance violation or suspected violation record."""

    STATUS_CHOICES = [
        ('open', 'Open'),
        ('investigating', 'Investigating'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
    ]

    SEVERITY_CHOICES = LegalRiskFinding.SEVERITY_CHOICES

    title = models.CharField(max_length=200, verbose_name='Title')
    description = models.TextField(verbose_name='Description')
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='medium')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    related_task = models.ForeignKey(
        LegalAnalysisTask,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='violation_records',
        verbose_name='Related task',
    )
    remediation_plan = models.TextField(blank=True, verbose_name='Remediation plan')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_violation_records',
        verbose_name='Created by',
    )
    ledger_entry = models.ForeignKey(
        'audit.AuditLedgerEntry',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='violation_records',
        verbose_name='Ledger entry',
    )
    occurred_at = models.DateTimeField(null=True, blank=True, verbose_name='Occurred at')
    resolved_at = models.DateTimeField(null=True, blank=True, verbose_name='Resolved at')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created at')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Updated at')

    class Meta:
        verbose_name = 'Violation record'
        verbose_name_plural = 'Violation records'
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class LegalReport(models.Model):
    """Generated legal compliance report."""

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('final', 'Final'),
        ('exported', 'Exported'),
        ('archived', 'Archived'),
    ]

    REPORT_TYPE_CHOICES = [
        ('analysis', 'Analysis report'),
        ('violation', 'Violation report'),
        ('periodic', 'Periodic report'),
        ('exercise', 'Exercise report'),
    ]

    task = models.ForeignKey(
        LegalAnalysisTask,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reports',
        verbose_name='Analysis task',
    )
    report_type = models.CharField(max_length=30, choices=REPORT_TYPE_CHOICES, default='analysis')
    title = models.CharField(max_length=200, verbose_name='Title')
    summary = models.TextField(blank=True, verbose_name='Summary')
    content = models.TextField(blank=True, verbose_name='Content')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='generated_legal_reports',
        verbose_name='Generated by',
    )
    ledger_entry = models.ForeignKey(
        'audit.AuditLedgerEntry',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='legal_reports',
        verbose_name='Ledger entry',
    )
    metadata = models.JSONField(default=dict, blank=True, verbose_name='Metadata')
    generated_at = models.DateTimeField(auto_now_add=True, verbose_name='Generated at')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Updated at')

    class Meta:
        verbose_name = 'Legal report'
        verbose_name_plural = 'Legal reports'
        ordering = ['-generated_at']

    def __str__(self):
        return self.title


class ComplianceAgentRun(models.Model):
    """Execution trace for compliance AI or rule-based analysis."""

    task = models.ForeignKey(
        LegalAnalysisTask,
        on_delete=models.CASCADE,
        related_name='agent_runs',
        verbose_name='Analysis task',
    )
    agent_id = models.CharField(max_length=80, default='compliance_officer', verbose_name='Agent ID')
    provider = models.CharField(max_length=80, blank=True, verbose_name='Provider')
    model = models.CharField(max_length=120, blank=True, verbose_name='Model')
    input_payload = models.JSONField(default=dict, blank=True, verbose_name='Input payload')
    output_payload = models.JSONField(default=dict, blank=True, verbose_name='Output payload')
    success = models.BooleanField(default=True, verbose_name='Success')
    error_message = models.TextField(blank=True, verbose_name='Error message')
    duration_ms = models.IntegerField(default=0, verbose_name='Duration ms')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Created at')

    class Meta:
        verbose_name = 'Compliance agent run'
        verbose_name_plural = 'Compliance agent runs'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.agent_id} for task {self.task_id}'


class LegalFactSnapshot(models.Model):
    """Confirmed input facts for a legal analysis task."""

    SOURCE_KIND_CHOICES = [
        ('automated', 'Automated'),
        ('hybrid', 'Hybrid'),
    ]
    source_kind = models.CharField(max_length=20, choices=SOURCE_KIND_CHOICES)
    scope = models.JSONField(default=dict)
    automated_facts = models.JSONField(default=dict)
    manual_notes = models.TextField(blank=True)
    warnings = models.JSONField(default=list, blank=True)
    evidence_refs = models.JSONField(default=list, blank=True)
    preview_hash = models.CharField(max_length=64, db_index=True)
    snapshot_hash = models.CharField(max_length=64, db_index=True)
    extraction_version = models.CharField(max_length=30, default='v1')
    redaction_version = models.CharField(max_length=30, default='v1')
    analysis_task = models.ForeignKey(
        LegalAnalysisTask,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='fact_snapshots',
    )
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='confirmed_legal_fact_snapshots',
    )
    confirmed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-confirmed_at']

    def __str__(self):
        return f'Fact snapshot {self.id} ({self.source_kind})'
