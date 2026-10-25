"""Shared vocabulary for module 1 (dual-track capability map).

The identifiers in this module are part of the hand-off contract used by
modules 6, 7 and 8.  Do not rename values that have been persisted; create a
new catalog version and mapping instead.
"""

TRACK_DATA = 'data'
TRACK_NETWORK = 'network'
TRACK_BOTH = 'both'

TRACK_CHOICES = [
    (TRACK_DATA, '数据安全'),
    (TRACK_NETWORK, '网络安全'),
]

TRACK_LABELS = dict(TRACK_CHOICES)
TRACK_LABELS[TRACK_BOTH] = '双主线'

DIMENSION_EXPLAIN = 'explain'
DIMENSION_IDENTIFY = 'identify'
DIMENSION_OPERATE = 'operate'
DIMENSION_REPAIR = 'repair'

DIMENSION_CHOICES = [
    (DIMENSION_EXPLAIN, '能解释'),
    (DIMENSION_IDENTIFY, '能识别'),
    (DIMENSION_OPERATE, '能操作'),
    (DIMENSION_REPAIR, '能修复'),
]
DIMENSION_LABELS = dict(DIMENSION_CHOICES)
DIMENSION_ORDER = [DIMENSION_EXPLAIN, DIMENSION_IDENTIFY, DIMENSION_OPERATE, DIMENSION_REPAIR]

CAPABILITY_STATUS_OPEN = 'open'
CAPABILITY_STATUS_TO_BUILD = 'to_build'
CAPABILITY_STATUS_AFTER_MILESTONE_I = 'after_milestone_i'
CAPABILITY_STATUS_CHOICES = [
    (CAPABILITY_STATUS_OPEN, '已开放'),
    (CAPABILITY_STATUS_TO_BUILD, '待建设'),
    (CAPABILITY_STATUS_AFTER_MILESTONE_I, '里程碑 I 后评估'),
]
CAPABILITY_STATUS_LABELS = dict(CAPABILITY_STATUS_CHOICES)

CATALOG_STATUS_CANDIDATE = 'candidate'
CATALOG_STATUS_FROZEN = 'frozen'
CATALOG_STATUS_PUBLISHED = 'published'
CATALOG_STATUS_DEPRECATED = 'deprecated'
CATALOG_STATUS_CHOICES = [
    (CATALOG_STATUS_CANDIDATE, '候选（未审核）'),
    (CATALOG_STATUS_FROZEN, '已冻结（待发布）'),
    (CATALOG_STATUS_PUBLISHED, '已发布'),
    (CATALOG_STATUS_DEPRECATED, '已弃用'),
]
CATALOG_STATUS_LABELS = dict(CATALOG_STATUS_CHOICES)

STATE_NEEDS_DIAGNOSIS = 'needs_diagnosis'
STATE_DIAGNOSED = 'diagnosed'
STATE_NEEDS_PRACTICE = 'needs_practice'
STATE_ASSISTED_PASS = 'assisted_pass'
STATE_INDEPENDENT = 'independent'
STATE_RETEST_PENDING = 'retest_pending'
STATE_PENDING_REVIEW = 'pending_review'
STATE_PENDING_VERIFICATION = 'pending_verification'
STATE_ENVIRONMENT_AFFECTED = 'environment_affected'
STATE_UNKNOWN = 'unknown'
STATE_NOT_ATTEMPTED = 'not_attempted'

STATE_CHOICES = [
    (STATE_NEEDS_DIAGNOSIS, '待诊断'),
    (STATE_DIAGNOSED, '已完成诊断'),
    (STATE_NEEDS_PRACTICE, '需要练习'),
    (STATE_ASSISTED_PASS, '受助通过'),
    (STATE_INDEPENDENT, '已有独立证据'),
    (STATE_RETEST_PENDING, '待复测'),
    (STATE_PENDING_REVIEW, '待教师评阅'),
    (STATE_PENDING_VERIFICATION, '待核验'),
    (STATE_ENVIRONMENT_AFFECTED, '受环境影响'),
    (STATE_UNKNOWN, '未知'),
    (STATE_NOT_ATTEMPTED, '未开展'),
]
STATE_LABELS = dict(STATE_CHOICES)

# States that never mean "the student is weak".  Used by the map so an
# un-attempted dimension is shown as 未开展 instead of a low score.
NON_EVIDENCE_STATES = {
    STATE_NEEDS_DIAGNOSIS,
    STATE_DIAGNOSED,
    STATE_NOT_ATTEMPTED,
    STATE_PENDING_REVIEW,
    STATE_PENDING_VERIFICATION,
    STATE_ENVIRONMENT_AFFECTED,
    STATE_UNKNOWN,
}

OUTCOME_PASSED = 'passed'
OUTCOME_FAILED = 'failed'
OUTCOME_PENDING_REVIEW = 'pending_review'
OUTCOME_VERIFICATION_FAILED = 'verification_failed'
OUTCOME_ENVIRONMENT_AFFECTED = 'environment_affected'
OUTCOME_UNKNOWN = 'unknown'
OUTCOME_CHOICES = [
    (OUTCOME_PASSED, '通过'),
    (OUTCOME_FAILED, '未通过'),
    (OUTCOME_PENDING_REVIEW, '待教师评阅'),
    (OUTCOME_VERIFICATION_FAILED, '核验失败'),
    (OUTCOME_ENVIRONMENT_AFFECTED, '受环境影响'),
    (OUTCOME_UNKNOWN, '未知'),
]

INDEPENDENCE_INDEPENDENT = 'independent'
INDEPENDENCE_ASSISTED = 'assisted'
INDEPENDENCE_UNKNOWN = 'unknown'
INDEPENDENCE_CHOICES = [
    (INDEPENDENCE_INDEPENDENT, '平台内独立'),
    (INDEPENDENCE_ASSISTED, '受助'),
    (INDEPENDENCE_UNKNOWN, '未知'),
]

ASSISTANCE_SOURCE_AI = 'ai'
ASSISTANCE_SOURCE_CARD = 'card'
ASSISTANCE_SOURCE_TEACHER = 'teacher'
ASSISTANCE_SOURCE_NONE = 'none'
ASSISTANCE_SOURCE_UNKNOWN = 'unknown'
ASSISTANCE_SOURCE_CHOICES = [
    (ASSISTANCE_SOURCE_AI, 'AI'),
    (ASSISTANCE_SOURCE_CARD, '预置卡片'),
    (ASSISTANCE_SOURCE_TEACHER, '教师'),
    (ASSISTANCE_SOURCE_NONE, '无'),
    (ASSISTANCE_SOURCE_UNKNOWN, '未知'),
]

DIAGNOSIS_UNKNOWN = 'unknown'
DIAGNOSIS_LIKELY_MASTERED = 'likely_mastered'
DIAGNOSIS_NEEDS_LEARNING = 'needs_learning'
DIAGNOSIS_INSUFFICIENT = 'insufficient'
DIAGNOSIS_RESULT_CHOICES = [
    (DIAGNOSIS_UNKNOWN, '未诊断'),
    (DIAGNOSIS_LIKELY_MASTERED, '诊断表现较好'),
    (DIAGNOSIS_NEEDS_LEARNING, '建议学习'),
    (DIAGNOSIS_INSUFFICIENT, '证据不足'),
]

TASK_STATUS_DRAFT = 'draft'
TASK_STATUS_REVIEWED = 'reviewed'
TASK_STATUS_FROZEN = 'frozen'
TASK_STATUS_WITHDRAWN = 'withdrawn'
TASK_STATUS_CHOICES = [
    (TASK_STATUS_DRAFT, '草案（未审核）'),
    (TASK_STATUS_REVIEWED, '已复核（待冻结）'),
    (TASK_STATUS_FROZEN, '已冻结'),
    (TASK_STATUS_WITHDRAWN, '已撤回'),
]

PURPOSE_PRACTICE = 'practice'
PURPOSE_VERIFICATION = 'verification'
PURPOSE_CONSOLIDATION = 'consolidation'
PURPOSE_RETEST = 'retest'
PURPOSE_NEW_CAPABILITY = 'new_capability'
PURPOSE_CHOICES = [
    (PURPOSE_PRACTICE, '练习'),
    (PURPOSE_VERIFICATION, '验收'),
    (PURPOSE_CONSOLIDATION, '受助后巩固'),
    (PURPOSE_RETEST, '新场景复测'),
    (PURPOSE_NEW_CAPABILITY, '新能力任务'),
]

EXECUTION_READONLY = 'readonly_decision'
EXECUTION_ISOLATED = 'isolated_challenge'
EXECUTION_DIAGNOSTIC = 'diagnostic'
EXECUTION_EXTERNAL = 'external'
EXECUTION_MODE_CHOICES = [
    (EXECUTION_READONLY, '只读决策演练'),
    (EXECUTION_ISOLATED, '隔离靶场'),
    (EXECUTION_DIAGNOSTIC, '诊断'),
    (EXECUTION_EXTERNAL, '外部任务'),
]

ATTEMPT_CLAIMED = 'claimed'
ATTEMPT_IN_PROGRESS = 'in_progress'
ATTEMPT_SUBMITTED = 'submitted'
ATTEMPT_PENDING_VERIFICATION = 'pending_verification'
ATTEMPT_VERIFIED = 'verified'
ATTEMPT_ABANDONED = 'abandoned'
ATTEMPT_STATUS_CHOICES = [
    (ATTEMPT_CLAIMED, '已领取'),
    (ATTEMPT_IN_PROGRESS, '进行中'),
    (ATTEMPT_SUBMITTED, '已提交'),
    (ATTEMPT_PENDING_VERIFICATION, '待核验'),
    (ATTEMPT_VERIFIED, '已核验'),
    (ATTEMPT_ABANDONED, '已放弃'),
]

MAPPING_MAPPED = 'mapped'
MAPPING_UNMAPPED = 'unmapped'
MAPPING_PROPOSED = 'proposed'
MAPPING_SPLIT = 'split'
MAPPING_STATUS_CHOICES = [
    (MAPPING_MAPPED, '已映射（已审核）'),
    (MAPPING_UNMAPPED, '未映射'),
    (MAPPING_PROPOSED, '候选映射（待审核）'),
    (MAPPING_SPLIT, '拆分（新 ID/版本）'),
]

DELIVERY_PENDING = 'pending_authoring'
DELIVERY_PENDING_REVIEW = 'pending_review'
DELIVERY_NEEDS_REVISION = 'needs_revision'
DELIVERY_SIGNED_OFF = 'signed_off'
DELIVERY_STATUS_CHOICES = [
    (DELIVERY_PENDING, '待编制'),
    (DELIVERY_PENDING_REVIEW, '待复核'),
    (DELIVERY_NEEDS_REVISION, '需修订'),
    (DELIVERY_SIGNED_OFF, '已签收'),
]

# Delivery numbers required before the first student task may be published.
REQUIRED_DELIVERY_ITEMS = [
    ('D1-catalog-mapping', '能力目录与旧标签映射 v1'),
    ('D2-wstg-basis', 'WSTG 场景转译表与数据依据卡'),
    ('D3-diagnostic-tasks', '双主线诊断与最小任务包'),
    ('D4-recommendation-rules', '诊断与推荐规则版本'),
    ('D5-events-handoff', '事件与模块交接清单'),
]

RULE_VERSION = 'rules-v1-candidate'

RECOMMENDATION_CATEGORY_ORDER = [
    'teacher_assigned',
    'diagnosis',
    'due_retest',
    'prerequisite',
    'practice',
    'consolidation',
    'new_capability',
]

RECOMMENDATION_CATEGORY_LABELS = {
    'teacher_assigned': '教师指定',
    'diagnosis': '基础诊断',
    'due_retest': '到期复测',
    'prerequisite': '补齐先修',
    'practice': '未通过练习',
    'consolidation': '受助后巩固',
    'new_capability': '新能力任务',
}

# Only an independent, platform-observed pass satisfies a prerequisite.  An
# assisted pass keeps the student moving on consolidation, not on tasks that
# require independent evidence.
PREREQUISITE_SATISFIED_STATES = {STATE_INDEPENDENT}

HINT_LEVELS = (1, 2, 3, 4)
HINT_LEVEL_LABELS = {1: '方向提示', 2: '相关知识', 3: '局部线索', 4: '关键步骤'}

MODULE6_NOT_CONNECTED = 'module6_not_connected'
MILESTONE_I_NOT_OPEN = 'milestone_i_not_open'

# Student-facing display helpers.  Internal reason codes and state identifiers
# stay in the API for teachers/audit; students see labels and tones only.
STATE_TONES = {
    STATE_INDEPENDENT: 'success',
    STATE_NEEDS_PRACTICE: 'danger',
    STATE_ASSISTED_PASS: 'warning',
    STATE_RETEST_PENDING: 'warning',
    STATE_NEEDS_DIAGNOSIS: 'muted',
    STATE_DIAGNOSED: 'muted',
    STATE_NOT_ATTEMPTED: 'muted',
    STATE_PENDING_REVIEW: 'neutral',
    STATE_PENDING_VERIFICATION: 'neutral',
    STATE_ENVIRONMENT_AFFECTED: 'neutral',
    STATE_UNKNOWN: 'neutral',
}

REASON_LABELS = {
    'independent_pass': '核验通过，已有独立证据',
    'assisted_pass': '核验通过但使用了帮助，已安排复测',
    'help_record_unknown': '帮助记录缺失，独立性未知',
    'verification_not_passed': '核验未通过，需要练习',
    'pending_teacher_review': '等待教师评阅',
    'verification_service_failed': '核验服务异常，等待重新核验',
    'environment_affected': '环境异常，不计为知识错误',
    'unknown_evidence': '证据不足，状态未知',
    'retest_independent_pass': '复测独立通过',
    'retest_assisted_pass': '复测使用了帮助，仍为受助通过',
    'retest_failed': '复测未通过，回到练习',
    'retest_due': '复测到期',
    'basic_diagnosis_completed': '已完成基础诊断',
}


def reason_label(code):
    return REASON_LABELS.get(code, '路径状态已更新')
