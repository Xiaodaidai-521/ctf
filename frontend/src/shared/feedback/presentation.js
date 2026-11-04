// Display vocabulary only. Values sent to the feedback service stay unchanged.
const labels = {
  status: {
    submitted: '已提交', deduplicating: '待检查重复', duplicate: '重复反馈',
    pending_fact_review: '待事实复核', pending_evidence: '待补证', confirmed: '已确认',
    rejected: '已驳回', handling: '人工处理中', handled: '已处理', reopened: '新证据待复核',
  },
  category: { recognition: '识别反馈', decision: '决策反馈', teaching: '教学反馈' },
  issue: {
    false_positive: '误报', false_negative: '漏报', classification_correction: '分类修正',
    normal_request_blocked: '正常请求被拦', unauthorized_allowed: '越权放行',
    missing_authorization_fact: '遗漏授权事实', hint_ineffective: '提示无效',
    wrong_attribution: '错误归因', assistance_misrecorded: '受助误记',
    retest_not_maintained: '复测未保持', scoring_dispute: '评分争议',
    catalog_or_recommendation: '目录或推荐问题', material_issue: '材料问题', other: '其他问题',
  },
  role: { student: '学生', teacher: '教师', admin: '管理员', system: '系统' },
  owner: {
    recognition_owner: '识别负责人', decision_owner: '决策负责人', teacher: '领域教师',
    course_owner: '课程负责人', platform_owner: '平台负责人',
  },
  destination: {
    unassigned: '未分配', recognition_case: '识别案例', replay_case: '决策回放案例',
    module6: '核验与评分复核', module1: '目录与推荐维护', course_material: '课程材料维护',
    platform: '平台维护', execution_integration: '执行处理（暂未开放）',
  },
  impact: { unknown: '未评估', low: '低', medium: '中', high: '高' },
  novelty: { unknown: '未评估', routine: '已知问题', new: '新问题' },
  effect: { not_assessed: '未评估', awaiting_retest: '待复测', verified: '已验证', insufficient: '证据不足' },
  sampling: { random: '随机抽样', high_risk: '高风险样本', census: '不足时全部查看' },
  evidence: { provided: '已提供', missing: '缺失', unknown: '待确认', not_applicable: '不适用' },
  source: { submitter: '提交人', server_linked: '关联记录', teacher: '教师补充' },
  visibility: { student: '学生可见', staff: '仅教师可见' },
  referral: { pending_ack: '待接收方确认', acknowledged: '已确认接收', declined: '已退回' },
  eventStatus: { linked: '已关联', pending: '待重试', mismatch: '内容不一致', missing: '事件缺失' },
  action: {
    submit: '提交反馈', dedup: '检查重复', claim: '认领反馈', assign: '分配责任人',
    triage: '登记优先级', request_evidence: '要求补证', provide_evidence: '补充证据',
    confirm: '确认反馈', reject: '驳回反馈', revise_review: '追加复核更正',
    start_handling: '开始处理', refer: '登记转交', ack_referral: '登记接收结果',
    handle: '标记已处理', reopen: '重新复核', note: '保存内部备注', set_effect: '登记教学效果',
    confirm_duplicate: '确认重复', split_duplicate: '拆分重复',
  },
  todoStatus: { unclaimed: '未认领', in_progress: '处理中', pending_verification: '待验证', verified: '复测已验证' },
  todoKind: {
    help: '主动求助', manual_review: '开放题必评', sampling: '常规抽查', dispute: '争议复核', evidence: '证据异常',
  },
  sourceQueueStatus: {
    pending: '待认领', open: '开放', claimed: '处理中', completed: '已完成', needs_correction: '需更正',
    submitted: '已提交', under_review: '复核中', reviewed: '已评阅', resolved: '已解决', helped: '已协助',
  },
  attemptStatus: { not_submitted: '未提交', unknown: '待确认', claimed: '已领取', in_progress: '进行中', submitted: '已提交', pending_verification: '待核验', verified: '已核验', abandoned: '已放弃' },
  event: {
    feedback_submitted: '反馈提交', feedback_deduplicated: '重复检查',
    feedback_evidence_added: '证据补充', feedback_reviewed: '反馈复核',
    feedback_handling_started: '处理开始', feedback_handled: '处理完成',
    feedback_reopened: '重新复核', feedback_effect_updated: '教学效果更新',
    feedback_status_changed: '反馈状态变更',
  },
  mapping: {
    catalog_version: '目录版本', task: '关联任务', task_version: '任务版本', attempt: '练习记录',
    capability_or_knowledge_point: '能力或知识点',
  },
  slot: {
    original_decision_ref: '原始判定及版本', sample_location: '样本出处',
    detection_result: '原始检出结果', detector_version: '识别器版本', match_granularity: '匹配粒度',
    human_annotation: '人工标注', basis_card_version: '依据卡版本', applicable_facts: '分类争议适用事实',
    request_scope: '请求范围与数量', identity_authorization: '身份与授权记录', business_purpose: '业务目的',
    recognition_review: '识别复核结果', policy_version: '教学策略版本', replay_io: '回放输入与输出',
    expected_reason: '预期理由', attempt_ref: '原练习记录', submission_verification: '提交与核验',
    help_trace: '提示展示与教师介入', rubric_version: '量表版本', material_version: '材料版本',
    review_retest: '复盘与新场景复测', scoring_basis: '评分依据与分项',
    catalog_recommendation_ref: '目录与推荐依据', material_ref: '材料与版本',
  },
}

const unknownLabels = {
  status: '状态待确认', category: '反馈类别待确认', issue: '问题类型待确认', role: '角色待确认',
  owner: '责任角色待确认', destination: '去向待确认', sampling: '抽样方式待确认',
  action: '其他反馈操作', event: '其他反馈事件', eventStatus: '核对状态待确认',
  mapping: '其他关联信息', slot: '其他证据',
}

export function feedbackLabel(kind, value) {
  const group = labels[kind]
  return group && Object.hasOwn(group, value) ? group[value] : (unknownLabels[kind] || '待确认')
}

export function feedbackOptions(items, kind) {
  return (items || []).map(item => ({ ...item, label: feedbackLabel(kind, item.value) }))
}

export function feedbackDate(value) {
  if (!value) return '日期未提供'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '日期待确认' : date.toLocaleString('zh-CN')
}

export function feedbackTitle(item) {
  if (!item) return '反馈详情（标题暂不可用）'
  return [item.task_title, feedbackLabel('category', item.category),
    feedbackLabel('issue', item.issue_type), item.student_name, feedbackDate(item.created_at)]
    .filter(Boolean).join(' · ')
}

export function feedbackPriority(item) {
  return `${item.conflict_flag ? '存在证据冲突' : '未标记证据冲突'}；影响${feedbackLabel('impact', item.impact_level)}；${feedbackLabel('novelty', item.novelty)}；等待 ${item.waiting_days ?? '待确认'} 天`
}

// The queue caps page_size at 100. Follow the returned size rather than assuming
// the requested size was honoured; never treat a short first page as all records.
export function nextFeedbackPage(response) {
  const page = Number(response.page)
  const size = Number(response.page_size)
  const total = Number(response.total)
  if (!Number.isInteger(page) || page < 1 || !Number.isInteger(size) || size < 1 || !Number.isFinite(total) || total < 0) {
    throw new Error('Invalid feedback pagination')
  }
  if (page * size >= total) return null
  if (!response.items?.length) throw new Error('Incomplete feedback pagination')
  return page + 1
}

export function mergeFeedbackItems(existing, incoming) {
  return [...new Map([...existing, ...incoming].map(item => [item.feedback_id, item])).values()]
}

export function reconciliationNote(item) {
  if (item.status === 'mismatch') return '记录内容不一致，请人工核对。'
  if (item.status === 'missing') return '尚未找到对应事件，请重试补齐。'
  if (item.status === 'pending') return '暂未完成同步，可以重试。'
  if (item.status === 'linked') return '已完成核对。'
  return '核对结果暂不可用，请刷新后重试。'
}

const errors = {
  version_conflict: '反馈已被其他操作更新，请刷新后重试。', version_required: '请刷新反馈后重试。',
  forbidden: '当前账号无权执行此操作。', reason_required: '请填写理由。', note_required: '请填写备注。',
  invalid_status: '当前反馈状态不支持此操作，请刷新并检查处理进度。',
  invalid_transition: '当前反馈尚不满足此操作的条件，请检查处理进度。',
  owner_conflict: '反馈已由其他责任人认领。', owner_not_found: '未找到指定责任人，请检查后重试。',
  invalid_owner: '责任人必须是教师或管理员。', invalid_destination: '请选择有效的处理去向。',
  milestone_i_not_open: '此处理去向暂未开放，请选择其他去向。',
  evidence_incomplete: '请先补齐关键证据，再确认反馈。', mapping_incomplete: '请先补齐任务、练习、版本与能力或知识点关联。',
  invalid_evidence_slot: '请选择本反馈要求补充的证据。', evidence_not_missing: '目前没有需要补充的证据。',
  invalid_datetime: '请检查日期和时间格式。', invalid_impact: '请选择有效的影响程度。', invalid_novelty: '请选择有效的问题新颖性。',
  invalid_conclusion: '请选择确认或驳回作为复核结论。', handling_action_required: '请填写处理动作。',
  handling_note_required: '请填写处理动作或处理说明。', referral_not_found: '未找到该转交记录，请刷新后重新选择。',
  invalid_referral_status: '请选择接收或退回转交。', ack_note_required: '退回转交时请说明原因。',
  referral_pending: '请等待接收方确认所有转交后，再标记已处理。', referral_required: '请先完成所需转交并确认接收。',
  invalid_effect_status: '请选择有效的教学效果状态。', effect_note_required: '请说明教学效果证据不足的原因。',
  retest_evidence_required: '请提供复测核验记录和复测练习记录。', retest_fact_not_found: '未找到该学生的复测核验记录。',
  retest_not_passed: '复测尚未通过，不能标记效果已验证。', retest_attempt_mismatch: '复测核验与练习记录不一致。',
  retest_link_missing: '复测记录尚未关联原练习，请先核对。',
  duplicate_record: '重复反馈请通过主反馈处理。', already_duplicate: '该反馈已关联主反馈。',
  main_ticket_not_found: '未找到主反馈，或所选反馈就是当前反馈。', main_ticket_is_duplicate: '主反馈不能是重复反馈。',
  student_mismatch: '不同学生的反馈不能合并为重复记录。', not_duplicate: '只有重复反馈可以拆分。',
  risk_not_in_population: '所选高风险反馈不在本次抽查范围内，可能已被抽查；请刷新选择或检查“排除既往样本”。',
  population_too_large: '本次抽查范围过大，请缩小范围后重试。',
  invalid_sample_size: '样本数量须为大于零的整数。', sample_size_required: '请填写样本数量。',
  invalid_seed: '抽样复现值须为非负整数。', invalid_risk_id: '部分高风险反馈已不可用，请重新选择。',
}

export function feedbackError(error, fallback = '操作未完成，请稍后重试。') {
  const data = error?.response?.data
  if (data?.code === 'destination_required') return `此反馈需要转交${feedbackLabel('destination', data.required_destination)}。`
  if (Object.hasOwn(errors, data?.code)) return errors[data.code]
  const status = error?.response?.status
  if (status === 401) return '登录已过期，请重新登录。'
  if (status === 403) return '当前账号无权访问或操作此反馈。'
  if (status === 404) return '记录不存在或当前账号无法访问，请刷新后重试。'
  if (status === 409) return '反馈已更新或当前条件不允许此操作，请刷新后检查。'
  if (status === 400) return '提交内容未通过检查，请核对必填项与记录关联后重试。'
  return fallback
}
