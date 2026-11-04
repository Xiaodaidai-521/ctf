// 结果与复盘的纯适配层：提交、复盘卡、复测、复核都用后台真实字段。
// 这里不构造成绩、不补完成时间，也不把“自报复习”写成能力证据。

export const CARD_FIELDS = Object.freeze([
  { key: 'original_task_summary', label: '任务摘要', hint: '默认由任务与版本生成，可按本人理解改写；完成复盘时同样会真实提交。' },
  { key: 'error_evidence', label: '错误证据', hint: '写清哪一步、哪条输出或哪份材料说明当时出了错。' },
  { key: 'judgment_at_time', label: '当时的判断', hint: '当时依据什么做了这个判断。' },
  { key: 'correct_basis', label: '正确依据或方法', hint: '正确的依据、方法或材料出处。' },
  { key: 'next_verification', label: '下一次如何验证', hint: '下一次用什么可复核的动作确认已改正。' },
  { key: 'student_reflection', label: '我的反思', hint: '这次复盘对后续练习的具体影响。' },
])

export const CARD_REQUIRED = Object.freeze(CARD_FIELDS.map(field => field.key))

const RETEST_STATUS_LABELS = Object.freeze({
  pending_item: '待补题',
  scheduled: '待到期',
  due: '已到期',
  in_progress: '进行中',
  completed: '已测',
  missed: '未完成',
  waived: '已免测',
})

const DISPUTE_STATUS_LABELS = Object.freeze({
  submitted: '已提交',
  under_review: '复核中',
  resolved: '已解决',
  rejected: '已驳回',
})

const CLAIMABLE_RETEST = new Set(['scheduled', 'due', 'in_progress'])

export function text(value) {
  return value === null || value === undefined ? '' : String(value)
}

export function formatDateTime(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  })
}

// 提交卡片保留逐项核验与教师评阅，不能压成一个综合分。
export function submissionView(item) {
  if (!item || !item.submission_id) return null
  const task = item.task || {}
  const assistance = item.assistance || {}
  return {
    id: String(item.submission_id),
    taskTitle: task.title || '未命名任务',
    versionLabel: task.version_label || '',
    trackLabel: task.track_label || '',
    submittedAt: item.submitted_at || null,
    submittedLabel: formatDateTime(item.submitted_at),
    sequence: item.sequence ?? null,
    firstEffective: item.first_effective ?? null,
    overallStatus: item.overall_status || '',
    overallLabel: item.overall_status_label || item.overall_status || '状态未知',
    programLabel: item.program_status_label || '待核验',
    manualLabel: item.manual_status_label || '不适用',
    independenceLabel: assistance.independence_label || '未记录',
    assistanceLevelLabel: assistance.level_label || '',
    saveLabel: item.save_status_label || '保存状态未知',
    note: item.verification_note || '',
    answerExposure: Boolean(assistance.answer_exposure),
    items: Array.isArray(item.items) ? item.items.map(entry => ({
      label: entry.label || entry.item_id || '未命名分项',
      kindLabel: entry.kind_label || '',
      status: entry.status || '',
      statusLabel: entry.status_label || entry.status || '状态未知',
      score: entry.score ?? null,
      maxPoints: entry.max_points ?? null,
      reason: entry.reason || '',
    })) : [],
    totalScore: item.total_score ?? null,
    maxTotalScore: item.max_total_score ?? null,
    remarks: item.review_remarks || '',
    resultVersion: item.result_version ?? null,
    corrected: Boolean(item.corrected) || Number(item.result_version) > 1,
  }
}

export function submissionViews(payload) {
  const items = Array.isArray(payload) ? payload : (Array.isArray(payload?.items) ? payload.items : [])
  return items.map(submissionView).filter(Boolean)
}

// 打开编辑先恢复已有草稿；没有复盘卡时用任务与版本生成任务摘要，仍会真实提交。
export function cardDraft(submission, card) {
  const view = submission && submission.taskTitle !== undefined ? submission : submissionView(submission)
  const source = card && typeof card === 'object' ? card : {}
  const values = {}
  for (const field of CARD_FIELDS) values[field.key] = text(source[field.key])
  if (!values.original_task_summary.trim() && view) {
    values.original_task_summary = [view.taskTitle, view.versionLabel].filter(Boolean).join(' · ')
  }
  const status = source.status || 'new'
  return {
    values,
    status,
    statusLabel: source.status_label || (status === 'completed' ? '已完成' : status === 'draft' ? '草稿' : '未开始'),
    readOnly: status === 'completed',
    completedAt: source.completed_at || null,
    teacherConfirmation: source.teacher_confirmation || '',
    assistanceLabel: source.assistance_level_label || '',
  }
}

export function cardMissing(values) {
  return CARD_FIELDS
    .filter(field => !text(values?.[field.key]).trim())
    .map(field => field.label)
}

export function cardPayload(values, complete = false) {
  const payload = {}
  for (const field of CARD_FIELDS) payload[field.key] = text(values?.[field.key]).trim()
  payload.complete = Boolean(complete)
  return payload
}

// 保存结果只转述后台返回；复测未安排时如实显示“等待补题”。
export function cardResult(payload, complete) {
  const card = payload?.review_card || null
  const retest = payload?.retest || null
  if (!complete) return { message: '草稿已保存；关闭后再次打开会从后台读回。', completed: false, retest: null }
  if (!retest) return { message: '复盘已保存；后台未返回复测安排，请稍后刷新复测清单。', completed: true, retest: null }
  const target = retest.task ? retest.task.title : '等待补题'
  const due = retest.due_at ? `，建议 ${formatDateTime(retest.due_at)}` : ''
  return {
    message: `复盘已完成，已安排复测：${target}${due}。`,
    completed: true,
    retest,
    card,
  }
}

export function retestView(item) {
  if (!item || !item.assignment_id) return null
  const status = item.status || ''
  const task = item.task || null
  return {
    id: String(item.assignment_id),
    status,
    statusLabel: item.status_label || RETEST_STATUS_LABELS[status] || '状态未知',
    taskTitle: task?.title || '',
    versionLabel: task?.version_label || '',
    dueAt: item.due_at || null,
    dueLabel: formatDateTime(item.due_at),
    scheduledLabel: formatDateTime(item.scheduled_at),
    graceLabel: formatDateTime(item.grace_until),
    outcomeLabel: item.outcome_label || '',
    completedLabel: item.completed_at ? formatDateTime(item.completed_at) : '',
    originalTaskTitle: item.original_task_title || '',
    note: item.note || '',
    pendingItem: status === 'pending_item',
    claimable: CLAIMABLE_RETEST.has(status),
    claimLabel: status === 'in_progress' ? '继续复测' : '领取复测',
  }
}

export function retestViews(payload) {
  const items = Array.isArray(payload) ? payload : (Array.isArray(payload?.items) ? payload.items : [])
  return items.map(retestView).filter(Boolean)
}

// 领取成功后必须指向真实任务尝试。后台只返回 attempt_id/task/created/note，
// 当前前端没有该任务的练习工作面；不得把证据页或 DataLab 当作“开始练习”，
// 因此如实说明落点缺口（G08），并保留可核对的尝试编号与任务信息。
export function claimTarget(payload) {
  const attemptId = text(payload?.attempt_id).trim()
  const task = payload?.task || {}
  if (!attemptId) {
    return {
      available: false,
      reason: '领取已受理，但后台未返回任务尝试编号，暂时无法核对这次复测；请刷新复测清单后重试。',
      note: payload?.note || '',
    }
  }
  const created = payload?.created === true
  return {
    available: true,
    attemptId,
    taskTitle: task.title || '复测任务',
    versionLabel: task.version_label || '',
    created,
    note: payload?.note || '',
    path: null,
    unresolved: true,
    reason: '本站尚未提供该复测任务的练习工作面（G08）；请按任务材料完成后再提交，不要以材料证据页代替练习。',
    message: created
      ? `已领取复测任务：${task.title || '复测任务'}${task.version_label ? ` · ${task.version_label}` : ''}；尝试编号 ${attemptId}。`
      : `该复测已有进行中的尝试：${task.title || '复测任务'}${task.version_label ? ` · ${task.version_label}` : ''}；尝试编号 ${attemptId}，未重复创建。`,
  }
}

// 复核标识在打开表单时固定；重试沿用同一 client_dispute_id，由后台幂等去重。
export function disputeKey(submissionId, seed) {
  return `d-${text(submissionId)}-${text(seed) || 'stable'}`
}

export function disputePayload(reason, key) {
  return { client_dispute_id: text(key), reason: text(reason).trim() }
}

export function disputeResult(payload) {
  const created = payload?.created !== false
  const label = payload?.status_label || DISPUTE_STATUS_LABELS[payload?.status] || '已提交'
  return {
    created,
    status: payload?.status || '',
    statusLabel: label,
    message: created ? `复核申请已提交，当前状态：${label}。` : `相同复核申请此前已提交，未重复创建；当前状态：${label}。`,
  }
}

export function disputeView(item) {
  if (!item || !item.dispute_id) return null
  return {
    id: String(item.dispute_id),
    taskTitle: item.task_title || '未命名任务',
    reason: item.reason || '',
    status: item.status || '',
    statusLabel: item.status_label || DISPUTE_STATUS_LABELS[item.status] || '状态未知',
    resolution: item.resolution || '',
    createdAt: item.created_at || null,
    createdLabel: formatDateTime(item.created_at),
    resolvedAt: item.resolved_at || null,
    resolvedLabel: item.resolved_at ? formatDateTime(item.resolved_at) : '',
  }
}

export function disputeViews(payload) {
  const items = Array.isArray(payload) ? payload : (Array.isArray(payload?.items) ? payload.items : [])
  return items.map(disputeView).filter(Boolean)
}

// 失败反馈留在对应提交/争议区；优先显示后台 detail，不吞掉版本冲突说明。
export function errorText(error) {
  const data = error?.response?.data
  if (!data) return '网络或服务异常，操作未完成。'
  if (typeof data === 'string') return data
  if (typeof data.detail === 'string') return data.detail
  if (data.detail && typeof data.detail.detail === 'string') return data.detail.detail
  if (typeof data.message === 'string') return data.message
  const first = Object.values(data).find(value => typeof value === 'string')
  return first || '操作未完成，请重试。'
}
