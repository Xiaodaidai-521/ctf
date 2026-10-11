"""Reason-code constants (regex spec H3 reason_catalog, M0 subset).

Stable string identifiers so judgment output, policy and tests agree on one
vocabulary instead of free-form strings. English identifiers by convention.
"""

# Request / profile consistency
CONSISTENCY_ASSET_VERSION_MISMATCH = "consistency.asset_version_mismatch"
CONSISTENCY_ENVIRONMENT_MISMATCH = "consistency.environment_mismatch"

# Hard constraints (explicit over-authorization -> deny, no model needed)
HARD_RECIPIENT_FORBIDDEN = "hard.recipient_forbidden"
HARD_OPERATION_FORBIDDEN = "hard.operation_forbidden"
HARD_SCOPE_EXCEEDED = "hard.scope_exceeded"
HARD_AUTHORIZATION_FORBIDDEN = "hard.authorization_forbidden"

# Degraded / insufficient input (never silently allowed)
DEGRADE_AUTHORIZATION_UNKNOWN = "degrade.authorization_unknown"
DEGRADE_PROFILE_INCOMPLETE = "degrade.profile_incomplete"
DEGRADE_APPROVAL_MISSING = "degrade.approval_missing"

# Baseline / allow
BASELINE_WITHIN_AUTHORIZED = "baseline.within_authorized"

# Fusion layer (M3): base protection floor + cumulative + anomaly + sensitivity
FUSION_BASE_PROTECTION = "fusion.base_protection_applied"
FUSION_SINGLE_THRESHOLD = "fusion.single_request_threshold_exceeded"
FUSION_CUMULATIVE_EXCEEDED = "fusion.cumulative_threshold_exceeded"
FUSION_ANOMALY_HIGH = "fusion.anomaly_high"
FUSION_SENSITIVE_ANOMALY = "fusion.sensitive_with_anomaly"
FUSION_ANOMALY_MODEL_UNAVAILABLE = "fusion.anomaly_model_unavailable"

# Admission (review R3) and execution preparation (H4)
ADMISSION_SYNTHETIC_IN_PRODUCTION = "admission.synthetic_in_production"
EXEC_DECISION_INVALID = "exec.decision_invalid"
EXEC_DECISION_EXPIRED = "exec.decision_expired"
EXEC_FINGERPRINT_MISMATCH = "exec.fingerprint_mismatch"
EXEC_ACTION_DENY = "exec.action_deny"
EXEC_ACTION_DEFER = "exec.action_defer"
EXEC_APPROVAL_REQUIRED = "exec.approval_required"
EXEC_OBLIGATION_UNSUPPORTED = "exec.obligation_unsupported"
EXEC_QUOTA_EXCEEDED = "exec.quota_exceeded"
EXEC_AUTHORIZATION_REVOKED = "exec.authorization_revoked"
