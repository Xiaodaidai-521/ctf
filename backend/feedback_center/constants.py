"""Shared vocabulary for module 7 (typed feedback and system improvement).

Only the phase-1 vocabulary lives here.  Phase-3 issue groups, candidates,
approval, activation, observation and rollback are documented in
``services/phase3.py`` and are deliberately **not** enabled in this build.

Stable identifiers must not be re-used with a new meaning.  If a category,
status or evidence slot changes meaning, add a new value and keep the old rows
readable under the old value.
"""

FEEDBACK_SCHEMA_VERSION = 'm7-feedback-v1'
PHASE3_CONTRACT_VERSION = 'm7-phase3-contract-v1-draft'

# Phase 1 never triggers an export, reserves a production quota or changes a
# production policy.  These flags are exposed by the status endpoint and by
# every ticket response so a closed ticket can never be mistaken for an active
# rule.
EXECUTION_FEEDBACK_OPEN = False
MILESTONE_I_OPEN = False
CANDIDATE_MANAGEMENT_ENABLED = False
CANDIDATE_RELEASE_ENABLED = False

CATEGORY_RECOGNITION = 'recognition'
CATEGORY_DECISION = 'decision'
CATEGORY_TEACHING = 'teaching'
CATEGORY_CHOICES = [
    (CATEGORY_RECOGNITION, '识别反馈'),
    (CATEGORY_DECISION, '决策反馈'),
    (CATEGORY_TEACHING, '教学反馈'),
]
CATEGORY_LABELS = dict(CATEGORY_CHOICES)

# The issue type is part of the submitted fact.  It is never inferred from the
# number of complaints, a like count or a normal-request block.
ISSUE_TYPES = {
    CATEGORY_RECOGNITION: [
        ('false_positive', '误报'),
        ('false_negative', '漏报'),
        ('classification_correction', '分类修正'),
        ('other', '其他识别问题'),
    ],
    CATEGORY_DECISION: [
        ('normal_request_blocked', '正常请求被拦'),
        ('unauthorized_allowed', '越权放行'),
        ('missing_authorization_fact', '遗漏授权事实'),
        ('other', '其他决策问题'),
    ],
    CATEGORY_TEACHING: [
        ('hint_ineffective', '提示无效'),
        ('wrong_attribution', '错误归因'),
        ('assistance_misrecorded', '受助误记'),
        ('retest_not_maintained', '复测未保持'),
        ('scoring_dispute', '评分争议'),
        ('catalog_or_recommendation', '目录或推荐问题'),
        ('material_issue', '材料问题'),
        ('other', '其他教学问题'),
    ],
}
ISSUE_TYPE_LABELS = {
    value: label for choices in ISSUE_TYPES.values() for value, label in choices
}


def issue_type_choices(category):
    return ISSUE_TYPES.get(category, [])


def issue_type_label(category, issue_type):
    for value, label in issue_type_choices(category):
        if value == issue_type:
            return label
    return issue_type


# ---------------------------------------------------------------------------
# Evidence slots
# ---------------------------------------------------------------------------

EVIDENCE_SLOT_ORIGINAL_DECISION = 'original_decision_ref'
EVIDENCE_SLOT_SAMPLE_LOCATION = 'sample_location'
EVIDENCE_SLOT_DETECTION_RESULT = 'detection_result'
EVIDENCE_SLOT_DETECTOR_VERSION = 'detector_version'
EVIDENCE_SLOT_MATCH_GRANULARITY = 'match_granularity'
EVIDENCE_SLOT_HUMAN_ANNOTATION = 'human_annotation'
EVIDENCE_SLOT_BASIS_CARD_VERSION = 'basis_card_version'
EVIDENCE_SLOT_APPLICABLE_FACTS = 'applicable_facts'
EVIDENCE_SLOT_REQUEST_SCOPE = 'request_scope'
EVIDENCE_SLOT_IDENTITY_AUTHORIZATION = 'identity_authorization'
EVIDENCE_SLOT_BUSINESS_PURPOSE = 'business_purpose'
EVIDENCE_SLOT_RECOGNITION_REVIEW = 'recognition_review'
EVIDENCE_SLOT_POLICY_VERSION = 'policy_version'
EVIDENCE_SLOT_REPLAY_IO = 'replay_io'
EVIDENCE_SLOT_EXPECTED_REASON = 'expected_reason'
EVIDENCE_SLOT_ATTEMPT_REF = 'attempt_ref'
EVIDENCE_SLOT_SUBMISSION_VERIFICATION = 'submission_verification'
EVIDENCE_SLOT_HELP_TRACE = 'help_trace'
EVIDENCE_SLOT_RUBRIC_VERSION = 'rubric_version'
EVIDENCE_SLOT_MATERIAL_VERSION = 'material_version'
EVIDENCE_SLOT_REVIEW_RETEST = 'review_retest'
EVIDENCE_SLOT_SCORING_BASIS = 'scoring_basis'
EVIDENCE_SLOT_CATALOG_RECOMMENDATION_REF = 'catalog_recommendation_ref'
EVIDENCE_SLOT_MATERIAL_REF = 'material_ref'

EVIDENCE_SLOT_LABELS = {
    EVIDENCE_SLOT_ORIGINAL_DECISION: '原始判定引用及版本',
    EVIDENCE_SLOT_SAMPLE_LOCATION: '合成样本定位',
    EVIDENCE_SLOT_DETECTION_RESULT: '原始检出结果',
    EVIDENCE_SLOT_DETECTOR_VERSION: '识别器版本',
    EVIDENCE_SLOT_MATCH_GRANULARITY: '匹配粒度',
    EVIDENCE_SLOT_HUMAN_ANNOTATION: '人工标注',
    EVIDENCE_SLOT_BASIS_CARD_VERSION: '依据卡版本',
    EVIDENCE_SLOT_APPLICABLE_FACTS: '分类争议适用事实',
    EVIDENCE_SLOT_REQUEST_SCOPE: '请求范围/数量',
    EVIDENCE_SLOT_IDENTITY_AUTHORIZATION: '身份与授权快照',
    EVIDENCE_SLOT_BUSINESS_PURPOSE: '业务目的',
    EVIDENCE_SLOT_RECOGNITION_REVIEW: '识别复核结果',
    EVIDENCE_SLOT_POLICY_VERSION: '教学策略版本',
    EVIDENCE_SLOT_REPLAY_IO: '回放输入输出',
    EVIDENCE_SLOT_EXPECTED_REASON: '预期理由',
    EVIDENCE_SLOT_ATTEMPT_REF: '原尝试',
    EVIDENCE_SLOT_SUBMISSION_VERIFICATION: '提交与核验',
    EVIDENCE_SLOT_HELP_TRACE: '提示实际展示/教师介入',
    EVIDENCE_SLOT_RUBRIC_VERSION: '量表版本',
    EVIDENCE_SLOT_MATERIAL_VERSION: '材料版本',
    EVIDENCE_SLOT_REVIEW_RETEST: '复盘及新场景复测（或明确未复测）',
    EVIDENCE_SLOT_SCORING_BASIS: '评分依据与分项',
    EVIDENCE_SLOT_CATALOG_RECOMMENDATION_REF: '目录/推荐版本与规则引用',
    EVIDENCE_SLOT_MATERIAL_REF: '材料引用与版本',
}

BASE_REQUIRED_SLOTS = (EVIDENCE_SLOT_ORIGINAL_DECISION,)

REQUIRED_SLOTS = {
    CATEGORY_RECOGNITION: [
        EVIDENCE_SLOT_ORIGINAL_DECISION,
        EVIDENCE_SLOT_SAMPLE_LOCATION,
        EVIDENCE_SLOT_DETECTION_RESULT,
        EVIDENCE_SLOT_DETECTOR_VERSION,
        EVIDENCE_SLOT_MATCH_GRANULARITY,
        EVIDENCE_SLOT_HUMAN_ANNOTATION,
        EVIDENCE_SLOT_BASIS_CARD_VERSION,
    ],
    CATEGORY_DECISION: [
        EVIDENCE_SLOT_ORIGINAL_DECISION,
        EVIDENCE_SLOT_REQUEST_SCOPE,
        EVIDENCE_SLOT_IDENTITY_AUTHORIZATION,
        EVIDENCE_SLOT_BUSINESS_PURPOSE,
        EVIDENCE_SLOT_RECOGNITION_REVIEW,
        EVIDENCE_SLOT_POLICY_VERSION,
        EVIDENCE_SLOT_REPLAY_IO,
        EVIDENCE_SLOT_EXPECTED_REASON,
    ],
    CATEGORY_TEACHING: [
        EVIDENCE_SLOT_ORIGINAL_DECISION,
        EVIDENCE_SLOT_ATTEMPT_REF,
        EVIDENCE_SLOT_SUBMISSION_VERIFICATION,
        EVIDENCE_SLOT_HELP_TRACE,
        EVIDENCE_SLOT_RUBRIC_VERSION,
        EVIDENCE_SLOT_MATERIAL_VERSION,
        EVIDENCE_SLOT_REVIEW_RETEST,
    ],
}

CONDITIONAL_REQUIRED_SLOTS = {
    (CATEGORY_RECOGNITION, 'classification_correction'): [EVIDENCE_SLOT_APPLICABLE_FACTS],
    (CATEGORY_TEACHING, 'scoring_dispute'): [EVIDENCE_SLOT_SCORING_BASIS],
    (CATEGORY_TEACHING, 'catalog_or_recommendation'): [EVIDENCE_SLOT_CATALOG_RECOMMENDATION_REF],
    (CATEGORY_TEACHING, 'material_issue'): [EVIDENCE_SLOT_MATERIAL_REF],
}


def required_slots(category, issue_type):
    slots = list(REQUIRED_SLOTS.get(category, []))
    for slot in CONDITIONAL_REQUIRED_SLOTS.get((category, issue_type), []):
        if slot not in slots:
            slots.append(slot)
    return slots


EVIDENCE_STATUS_PROVIDED = 'provided'
EVIDENCE_STATUS_MISSING = 'missing'
EVIDENCE_STATUS_UNKNOWN = 'unknown'
EVIDENCE_STATUS_NOT_APPLICABLE = 'not_applicable'
EVIDENCE_STATUS_CHOICES = [
    (EVIDENCE_STATUS_PROVIDED, '已提供'),
    (EVIDENCE_STATUS_MISSING, '缺失'),
    (EVIDENCE_STATUS_UNKNOWN, '未知'),
    (EVIDENCE_STATUS_NOT_APPLICABLE, '不适用'),
]
EVIDENCE_STATUS_LABELS = dict(EVIDENCE_STATUS_CHOICES)
INCOMPLETE_EVIDENCE_STATUSES = {EVIDENCE_STATUS_MISSING, EVIDENCE_STATUS_UNKNOWN}

EVIDENCE_SOURCE_SUBMITTER = 'submitter'
EVIDENCE_SOURCE_SERVER_LINKED = 'server_linked'
EVIDENCE_SOURCE_TEACHER = 'teacher'
EVIDENCE_SOURCE_CHOICES = [
    (EVIDENCE_SOURCE_SUBMITTER, '提交人'),
    (EVIDENCE_SOURCE_SERVER_LINKED, '服务端关联'),
    (EVIDENCE_SOURCE_TEACHER, '教师补充'),
]
EVIDENCE_SOURCE_LABELS = dict(EVIDENCE_SOURCE_CHOICES)

VISIBILITY_STUDENT = 'student'
VISIBILITY_STAFF = 'staff'
VISIBILITY_CHOICES = [
    (VISIBILITY_STUDENT, '学生可见'),
    (VISIBILITY_STAFF, '仅教师可见'),
]
VISIBILITY_LABELS = dict(VISIBILITY_CHOICES)

# ---------------------------------------------------------------------------
# Status machine
# ---------------------------------------------------------------------------

STATUS_SUBMITTED = 'submitted'
STATUS_DEDUPLICATING = 'deduplicating'
STATUS_DUPLICATE = 'duplicate'
STATUS_PENDING_FACT_REVIEW = 'pending_fact_review'
STATUS_PENDING_EVIDENCE = 'pending_evidence'
STATUS_CONFIRMED = 'confirmed'
STATUS_REJECTED = 'rejected'
STATUS_HANDLING = 'handling'
STATUS_HANDLED = 'handled'
STATUS_REOPENED = 'reopened'
STATUS_CHOICES = [
    (STATUS_SUBMITTED, '已提交'),
    (STATUS_DEDUPLICATING, '待去重'),
    (STATUS_DUPLICATE, '重复（已关联主记录）'),
    (STATUS_PENDING_FACT_REVIEW, '待事实复核'),
    (STATUS_PENDING_EVIDENCE, '待补证'),
    (STATUS_CONFIRMED, '已确认'),
    (STATUS_REJECTED, '已驳回'),
    (STATUS_HANDLING, '人工处理中'),
    (STATUS_HANDLED, '已处理'),
    (STATUS_REOPENED, '新证据待复核'),
]
STATUS_LABELS = dict(STATUS_CHOICES)

OPEN_STATUSES = {
    STATUS_SUBMITTED,
    STATUS_DEDUPLICATING,
    STATUS_PENDING_FACT_REVIEW,
    STATUS_PENDING_EVIDENCE,
    STATUS_REOPENED,
}
REVIEWABLE_STATUSES = {STATUS_PENDING_FACT_REVIEW}
HANDLEABLE_STATUSES = {STATUS_CONFIRMED, STATUS_HANDLING}
EFFECT_EDITABLE_STATUSES = {STATUS_CONFIRMED, STATUS_HANDLING, STATUS_HANDLED}
REOPENABLE_STATUSES = {STATUS_CONFIRMED, STATUS_REJECTED, STATUS_HANDLED}
CANDIDATE_SOURCE_STATUSES = {STATUS_CONFIRMED, STATUS_HANDLING, STATUS_HANDLED}

# A transition map is kept for audit/documentation.  Services still check the
# exact action preconditions because some transitions also depend on evidence,
# role or referral acknowledgement.
ALLOWED_TRANSITIONS = {
    STATUS_SUBMITTED: {STATUS_DEDUPLICATING},
    STATUS_DEDUPLICATING: {STATUS_DUPLICATE, STATUS_PENDING_FACT_REVIEW, STATUS_PENDING_EVIDENCE},
    STATUS_DUPLICATE: {STATUS_PENDING_FACT_REVIEW, STATUS_PENDING_EVIDENCE},
    STATUS_PENDING_FACT_REVIEW: {STATUS_PENDING_EVIDENCE, STATUS_CONFIRMED, STATUS_REJECTED},
    STATUS_PENDING_EVIDENCE: {STATUS_PENDING_FACT_REVIEW, STATUS_REJECTED},
    STATUS_CONFIRMED: {STATUS_HANDLING, STATUS_REJECTED, STATUS_REOPENED},
    STATUS_REJECTED: {STATUS_REOPENED},
    STATUS_HANDLING: {STATUS_HANDLED, STATUS_REOPENED},
    STATUS_HANDLED: {STATUS_REOPENED},
    STATUS_REOPENED: {STATUS_PENDING_FACT_REVIEW},
}

# ---------------------------------------------------------------------------
# Responsibility / routing
# ---------------------------------------------------------------------------

OWNER_RECOGNITION = 'recognition_owner'
OWNER_DECISION = 'decision_owner'
OWNER_TEACHER = 'teacher'
OWNER_COURSE = 'course_owner'
OWNER_PLATFORM = 'platform_owner'
OWNER_ROLE_CHOICES = [
    (OWNER_RECOGNITION, '识别负责人'),
    (OWNER_DECISION, '决策负责人'),
    (OWNER_TEACHER, '领域教师'),
    (OWNER_COURSE, '课程负责人'),
    (OWNER_PLATFORM, '平台负责人'),
]
OWNER_ROLE_LABELS = dict(OWNER_ROLE_CHOICES)

DESTINATION_UNASSIGNED = 'unassigned'
DESTINATION_RECOGNITION_CASE = 'recognition_case'
DESTINATION_REPLAY_CASE = 'replay_case'
DESTINATION_MODULE6 = 'module6'
DESTINATION_MODULE1 = 'module1'
DESTINATION_COURSE_MATERIAL = 'course_material'
DESTINATION_PLATFORM = 'platform'
DESTINATION_EXECUTION = 'execution_integration'
DESTINATION_CHOICES = [
    (DESTINATION_UNASSIGNED, '未分配'),
    (DESTINATION_RECOGNITION_CASE, '识别案例'),
    (DESTINATION_REPLAY_CASE, '决策回放案例'),
    (DESTINATION_MODULE6, '模块六：核验/评分争议'),
    (DESTINATION_MODULE1, '模块一：目录/推荐'),
    (DESTINATION_COURSE_MATERIAL, '课程材料维护'),
    (DESTINATION_PLATFORM, '平台维护'),
    (DESTINATION_EXECUTION, '执行集成（里程碑 I，未开放）'),
]
DESTINATION_LABELS = dict(DESTINATION_CHOICES)

# Only these destinations may be acknowledged through the phase-1 referral
# register.  Execution integration remains closed until milestone I.
REFERRAL_DESTINATIONS = [
    DESTINATION_MODULE6,
    DESTINATION_MODULE1,
    DESTINATION_COURSE_MATERIAL,
    DESTINATION_PLATFORM,
]
REFERRAL_PENDING = 'pending_ack'
REFERRAL_ACKNOWLEDGED = 'acknowledged'
REFERRAL_DECLINED = 'declined'
REFERRAL_STATUS_CHOICES = [
    (REFERRAL_PENDING, '待接收方确认'),
    (REFERRAL_ACKNOWLEDGED, '已确认接收'),
    (REFERRAL_DECLINED, '已退回'),
]
REFERRAL_STATUS_LABELS = dict(REFERRAL_STATUS_CHOICES)


def default_owner_role(category, issue_type):
    if category == CATEGORY_RECOGNITION:
        return OWNER_RECOGNITION
    if category == CATEGORY_DECISION:
        return OWNER_DECISION
    if issue_type in ('catalog_or_recommendation',):
        return OWNER_COURSE
    if issue_type in ('material_issue',):
        return OWNER_COURSE
    return OWNER_TEACHER


def default_destination(category, issue_type):
    if category == CATEGORY_RECOGNITION:
        return DESTINATION_RECOGNITION_CASE
    if category == CATEGORY_DECISION:
        return DESTINATION_REPLAY_CASE
    if issue_type in ('scoring_dispute', 'wrong_attribution', 'assistance_misrecorded', 'retest_not_maintained'):
        return DESTINATION_MODULE6
    if issue_type in ('catalog_or_recommendation',):
        return DESTINATION_MODULE1
    if issue_type in ('hint_ineffective', 'material_issue'):
        return DESTINATION_COURSE_MATERIAL
    return DESTINATION_MODULE6


# ---------------------------------------------------------------------------
# Priority, sampling and effect
# ---------------------------------------------------------------------------

IMPACT_UNKNOWN = 'unknown'
IMPACT_LOW = 'low'
IMPACT_MEDIUM = 'medium'
IMPACT_HIGH = 'high'
IMPACT_CHOICES = [
    (IMPACT_UNKNOWN, '未评估'),
    (IMPACT_LOW, '低'),
    (IMPACT_MEDIUM, '中'),
    (IMPACT_HIGH, '高'),
]
IMPACT_LABELS = dict(IMPACT_CHOICES)
IMPACT_RANK = {IMPACT_UNKNOWN: 0, IMPACT_LOW: 1, IMPACT_MEDIUM: 2, IMPACT_HIGH: 3}

NOVELTY_UNKNOWN = 'unknown'
NOVELTY_ROUTINE = 'routine'
NOVELTY_NEW = 'new'
NOVELTY_CHOICES = [
    (NOVELTY_UNKNOWN, '未知'),
    (NOVELTY_ROUTINE, '已知问题'),
    (NOVELTY_NEW, '新问题'),
]
NOVELTY_LABELS = dict(NOVELTY_CHOICES)
NOVELTY_RANK = {NOVELTY_UNKNOWN: 0, NOVELTY_ROUTINE: 1, NOVELTY_NEW: 2}

SAMPLING_RANDOM = 'random'
SAMPLING_HIGH_RISK = 'high_risk'
SAMPLING_CENSUS = 'census'
SAMPLING_REASON_CHOICES = [
    (SAMPLING_RANDOM, '随机样本'),
    (SAMPLING_HIGH_RISK, '高风险样本'),
    (SAMPLING_CENSUS, '不足时全部查看'),
]
SAMPLING_REASON_LABELS = dict(SAMPLING_REASON_CHOICES)

EFFECT_NOT_ASSESSED = 'not_assessed'
EFFECT_AWAITING_RETEST = 'awaiting_retest'
EFFECT_VERIFIED = 'verified'
EFFECT_INSUFFICIENT = 'insufficient'
EFFECT_CHOICES = [
    (EFFECT_NOT_ASSESSED, '未评估'),
    (EFFECT_AWAITING_RETEST, '待复测'),
    (EFFECT_VERIFIED, '已验证'),
    (EFFECT_INSUFFICIENT, '证据不足'),
]
EFFECT_LABELS = dict(EFFECT_CHOICES)

# ---------------------------------------------------------------------------
# Event dictionary
# ---------------------------------------------------------------------------

EVENT_FEEDBACK_SUBMITTED = 'feedback_submitted'
EVENT_FEEDBACK_DEDUPLICATED = 'feedback_deduplicated'
EVENT_FEEDBACK_EVIDENCE_ADDED = 'feedback_evidence_added'
EVENT_FEEDBACK_REVIEWED = 'feedback_reviewed'
EVENT_FEEDBACK_HANDLING_STARTED = 'feedback_handling_started'
EVENT_FEEDBACK_HANDLED = 'feedback_handled'
EVENT_FEEDBACK_REOPENED = 'feedback_reopened'
EVENT_FEEDBACK_EFFECT_UPDATED = 'feedback_effect_updated'
EVENT_FEEDBACK_STATUS_CHANGED = 'feedback_status_changed'

FEEDBACK_EVENT_TYPES = [
    (EVENT_FEEDBACK_SUBMITTED, 'Feedback submitted'),
    (EVENT_FEEDBACK_DEDUPLICATED, 'Feedback deduplicated'),
    (EVENT_FEEDBACK_EVIDENCE_ADDED, 'Feedback evidence added'),
    (EVENT_FEEDBACK_REVIEWED, 'Feedback reviewed'),
    (EVENT_FEEDBACK_HANDLING_STARTED, 'Feedback handling started'),
    (EVENT_FEEDBACK_HANDLED, 'Feedback handled'),
    (EVENT_FEEDBACK_REOPENED, 'Feedback reopened'),
    (EVENT_FEEDBACK_EFFECT_UPDATED, 'Feedback effect updated'),
    (EVENT_FEEDBACK_STATUS_CHANGED, 'Feedback status changed'),
]

# Event-link states used by the reconciliation page.  A pending link is not a
# learning fact; it is an outbox row that must be retried and reconciled.
EVENT_LINK_LINKED = 'linked'
EVENT_LINK_PENDING = 'pending'
EVENT_LINK_MISMATCH = 'mismatch'
EVENT_LINK_MISSING = 'missing'
EVENT_LINK_STATUS_CHOICES = [
    (EVENT_LINK_LINKED, '已关联'),
    (EVENT_LINK_PENDING, '待重试'),
    (EVENT_LINK_MISMATCH, '内容不一致'),
    (EVENT_LINK_MISSING, '事件缺失'),
]
EVENT_LINK_STATUS_LABELS = dict(EVENT_LINK_STATUS_CHOICES)

# ---------------------------------------------------------------------------
# Action / relation labels
# ---------------------------------------------------------------------------

ACTION_LABELS = {
    'submit': '提交',
    'dedup': '去重',
    'claim': '认领',
    'assign': '分配',
    'triage': '登记优先级',
    'request_evidence': '要求补证',
    'provide_evidence': '补充证据',
    'confirm': '确认',
    'reject': '驳回',
    'revise_review': '追加复核更正',
    'start_handling': '开始处理',
    'refer': '转交',
    'ack_referral': '确认接收转交',
    'handle': '标记已处理',
    'reopen': '重开',
    'note': '内部备注',
    'set_effect': '登记教学效果',
    'confirm_duplicate': '确认重复',
    'split_duplicate': '拆分重复',
}

RELATION_TYPE_LABELS = {
    'duplicate': '重复提交',
    'same_attempt_cross_category': '同尝试跨类别',
    'split_from': '从重复记录拆出',
}

# ---------------------------------------------------------------------------
# Attachments
# ---------------------------------------------------------------------------

ATTACHMENT_ALLOWED_EXTENSIONS = {'.pdf', '.png', '.jpg', '.jpeg', '.txt', '.csv', '.json', '.md'}
ATTACHMENT_MAX_BYTES = 10 * 1024 * 1024
ATTACHMENT_DOWNLOAD_ACTION = 'download_attachment'
ACCESS_VIEW_DETAIL = 'view_detail'


def label(mapping, value, fallback=''):
    return mapping.get(value, fallback or value or '')

# ---------------------------------------------------------------- phase 3
# Issue groups, candidates and the release state machine.  The state machine is
# implemented; whether it can be driven is controlled by settings
# ``FEEDBACK_PHASE3_ENABLED`` and ``FEEDBACK_PHASE3_RELEASE_ENABLED`` so the
# first phase cannot publish a teaching configuration by accident.

ISSUE_GROUP_DRAFT = 'draft'
ISSUE_GROUP_PENDING_CONFIRMATION = 'pending_confirmation'
ISSUE_GROUP_CONFIRMED = 'confirmed'
ISSUE_GROUP_REJECTED = 'rejected'
ISSUE_GROUP_SUPERSEDED = 'superseded'
ISSUE_GROUP_STATUS_CHOICES = [
    (ISSUE_GROUP_DRAFT, '草稿'),
    (ISSUE_GROUP_PENDING_CONFIRMATION, '待确认成员'),
    (ISSUE_GROUP_CONFIRMED, '已确认'),
    (ISSUE_GROUP_REJECTED, '已驳回'),
    (ISSUE_GROUP_SUPERSEDED, '已替代'),
]
ISSUE_GROUP_STATUS_LABELS = dict(ISSUE_GROUP_STATUS_CHOICES)

ISSUE_GROUP_ACTION_CREATED = 'created'
ISSUE_GROUP_ACTION_MEMBER_ADDED = 'member_added'
ISSUE_GROUP_ACTION_MEMBER_REMOVED = 'member_removed'
ISSUE_GROUP_ACTION_CONFIRMED = 'confirmed'
ISSUE_GROUP_ACTION_REJECTED = 'rejected'
ISSUE_GROUP_ACTION_SPLIT = 'split'
ISSUE_GROUP_ACTION_MERGED = 'merged'
ISSUE_GROUP_ACTION_CHOICES = [
    (ISSUE_GROUP_ACTION_CREATED, '创建'),
    (ISSUE_GROUP_ACTION_MEMBER_ADDED, '加入成员'),
    (ISSUE_GROUP_ACTION_MEMBER_REMOVED, '移除成员'),
    (ISSUE_GROUP_ACTION_CONFIRMED, '确认'),
    (ISSUE_GROUP_ACTION_REJECTED, '驳回'),
    (ISSUE_GROUP_ACTION_SPLIT, '拆组'),
    (ISSUE_GROUP_ACTION_MERGED, '并组'),
]

CANDIDATE_DRAFT = 'draft'
CANDIDATE_PENDING_EVAL = 'pending_eval'
CANDIDATE_EVALUATING = 'evaluating'
CANDIDATE_NEEDS_REVISION = 'needs_revision'
CANDIDATE_PENDING_APPROVAL = 'pending_approval'
CANDIDATE_APPROVED_PENDING_RELEASE = 'approved_pending_release'
CANDIDATE_OBSERVING = 'observing'
CANDIDATE_STABLE = 'stable'
CANDIDATE_ROLLED_BACK = 'rolled_back'
CANDIDATE_WITHDRAWN = 'withdrawn'
CANDIDATE_STATE_CHOICES = [
    (CANDIDATE_DRAFT, '候选草稿'),
    (CANDIDATE_PENDING_EVAL, '待评测'),
    (CANDIDATE_EVALUATING, '评测中'),
    (CANDIDATE_NEEDS_REVISION, '待修订'),
    (CANDIDATE_PENDING_APPROVAL, '待审批'),
    (CANDIDATE_APPROVED_PENDING_RELEASE, '已批准待发布'),
    (CANDIDATE_OBSERVING, '观察中'),
    (CANDIDATE_STABLE, '已稳定'),
    (CANDIDATE_ROLLED_BACK, '已回退'),
    (CANDIDATE_WITHDRAWN, '已撤回'),
]
CANDIDATE_STATE_LABELS = dict(CANDIDATE_STATE_CHOICES)

# Allowed transitions.  Every entry names the state it moves to and is enforced
# on the server; the UI only hides buttons that would fail.
CANDIDATE_TRANSITIONS = {
    CANDIDATE_DRAFT: {CANDIDATE_PENDING_EVAL, CANDIDATE_WITHDRAWN},
    CANDIDATE_PENDING_EVAL: {CANDIDATE_EVALUATING, CANDIDATE_DRAFT, CANDIDATE_WITHDRAWN},
    CANDIDATE_EVALUATING: {CANDIDATE_PENDING_APPROVAL, CANDIDATE_NEEDS_REVISION, CANDIDATE_WITHDRAWN},
    CANDIDATE_NEEDS_REVISION: {CANDIDATE_PENDING_EVAL, CANDIDATE_DRAFT, CANDIDATE_WITHDRAWN},
    CANDIDATE_PENDING_APPROVAL: {CANDIDATE_APPROVED_PENDING_RELEASE, CANDIDATE_NEEDS_REVISION, CANDIDATE_WITHDRAWN},
    CANDIDATE_APPROVED_PENDING_RELEASE: {CANDIDATE_OBSERVING, CANDIDATE_WITHDRAWN},
    CANDIDATE_OBSERVING: {CANDIDATE_STABLE, CANDIDATE_ROLLED_BACK},
    CANDIDATE_STABLE: {CANDIDATE_ROLLED_BACK},
    CANDIDATE_ROLLED_BACK: set(),
    CANDIDATE_WITHDRAWN: set(),
}

REPORT_RECOMMENDATION_PASS = 'pass'
REPORT_RECOMMENDATION_FAIL = 'fail'
REPORT_RECOMMENDATION_INSUFFICIENT = 'insufficient_evidence'
REPORT_RECOMMENDATION_CHOICES = [
    (REPORT_RECOMMENDATION_PASS, '建议通过'),
    (REPORT_RECOMMENDATION_FAIL, '建议不通过'),
    (REPORT_RECOMMENDATION_INSUFFICIENT, '证据不足'),
]

OBSERVATION_OBSERVING = 'observing'
OBSERVATION_STABLE = 'stable'
OBSERVATION_INSUFFICIENT = 'insufficient_evidence'
OBSERVATION_PAUSED = 'paused'
OBSERVATION_STATUS_CHOICES = [
    (OBSERVATION_OBSERVING, '观察中'),
    (OBSERVATION_STABLE, '已稳定'),
    (OBSERVATION_INSUFFICIENT, '证据不足'),
    (OBSERVATION_PAUSED, '已暂停'),
]

ROLLBACK_SUCCESS = 'success'
ROLLBACK_FAILED = 'failed'
ROLLBACK_UNKNOWN = 'unknown_pending_reconciliation'
ROLLBACK_RESULT_CHOICES = [
    (ROLLBACK_SUCCESS, '成功'),
    (ROLLBACK_FAILED, '失败'),
    (ROLLBACK_UNKNOWN, '未知，待对账'),
]

# Phase 3 write gate.  Read endpoints stay open so the contract and the state of
# existing rows are inspectable while writes are closed.
PHASE3_WRITE_DISABLED = 'phase3_write_disabled'
PHASE3_RELEASE_DISABLED = 'phase3_release_disabled'

DISPUTE_STATUS_MIRROR_LABELS = [
    ('submitted', '已提交模块六'),
    ('under_review', '模块六复核中'),
    ('resolved', '模块六已解决'),
    ('rejected', '模块六已驳回'),
]
