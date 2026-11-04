// 能力探索的纯呈现层：只用学生 map 中的真实对象，未知状态保持未知，不补 0 掌握、
// 不按标题造边。任务推荐来自 learning-map 推荐接口，与具体能力没有精确映射时
// 只标“本主线推荐”，不冒充“本节点关联”。

export const STATE_LEGEND = Object.freeze([
  { key: 'independent', label: '独立通过', note: '自己独立完成，没有用过提示或讲解' },
  { key: 'assisted', label: '提示后通过 / 待复测', note: '换一道新题，独立再做一次' },
  { key: 'practice', label: '继续练习', note: '这次没有通过，按练习记录继续练' },
  { key: 'pending', label: '待确认 / 待批阅', note: '还没有最终结果，不算已通过' },
  { key: 'unknown', label: '待诊断 / 状态未知', note: '还没有练习记录，状态保持未知' },
])

// 后端状态名带评估术语，展示时换成学生能直接理解的说法；判断仍按原始状态，语义不变。
const STUDENT_LABELS = Object.freeze({
  '已有独立证据': '独立通过',
  '受助通过': '提示后通过',
  '待复测': '待复测',
  '需要练习': '继续练习',
  '待教师评阅': '待老师批阅',
  '待核验': '待确认',
  '受环境影响': '环境异常，待重试',
  '待诊断': '待诊断',
  '已完成诊断': '已做诊断',
  '未开展': '未开始',
  '未知': '状态未知',
  '核验失败': '检查未通过',
  '未知结果': '状态未知',
})
export const studentLabel = value => STUDENT_LABELS[text(value)] || text(value)

const UNKNOWN_STATES = new Set(['待诊断', '未知', '未开展', '已完成诊断'])
const ASSISTED_STATES = new Set(['受助通过', '待复测'])
const PRACTICE_STATES = new Set(['需要练习'])
const PENDING_STATES = new Set(['待教师评阅', '待核验', '受环境影响'])

export const text = value => (value === null || value === undefined ? '' : String(value))

export function formatDateTime(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

// 学生 map 不给能力稳定 ID；用“主线 + 标题”组成只在本页使用的键，不跨接口当 ID。
export function capabilityKey(track, capability) {
  return `${text(track)}::${text(capability?.title)}`
}

export function stateInfo(capability) {
  const label = text(capability?.state_label).trim()
  const tone = text(capability?.tone) || 'neutral'
  if (!label) return { key: 'unknown', label: '状态未知', tone: 'neutral', known: false }
  if (UNKNOWN_STATES.has(label)) return { key: 'unknown', label: studentLabel(label), rawLabel: label, tone, known: false }
  if (ASSISTED_STATES.has(label)) return { key: 'assisted', label: studentLabel(label), rawLabel: label, tone, known: true }
  if (PRACTICE_STATES.has(label)) return { key: 'practice', label: studentLabel(label), rawLabel: label, tone, known: true }
  if (PENDING_STATES.has(label)) return { key: 'pending', label: studentLabel(label), rawLabel: label, tone, known: true }
  if (label === '已有独立证据') return { key: 'independent', label: studentLabel(label), rawLabel: label, tone, known: true }
  return { key: 'unknown', label: studentLabel(label), rawLabel: label, tone, known: false }
}

export function evidenceView(evidence) {
  const latest = evidence?.latest || null
  const count = Number(evidence?.fact_count)
  if (!latest) {
    return { count: Number.isFinite(count) ? count : 0, hasEvidence: false, result: '还没有练习记录', task: null, assisted: null, time: null, timeLabel: '—' }
  }
  return {
    count: Number.isFinite(count) ? count : 0,
    hasEvidence: true,
    result: studentLabel(text(latest.outcome_label)) || '结果未知',
    task: text(latest.task_title) || null,
    assisted: typeof latest.assisted === 'boolean' ? latest.assisted : null,
    time: latest.occurred_at || null,
    timeLabel: formatDateTime(latest.occurred_at),
  }
}

export function prerequisiteViews(prerequisites) {
  return (Array.isArray(prerequisites) ? prerequisites : []).map(item => ({
    title: text(item?.title) || '未命名先修能力',
    stateLabel: studentLabel(text(item?.state_label)) || '状态未知',
    tone: text(item?.tone) || 'muted',
    // 只有“独立通过”才算先修完成；其余状态如实显示，不推断。
    satisfied: text(item?.state_label) === '已有独立证据',
  }))
}

export function capabilityView(track, capability) {
  if (!capability || !track?.track) return null
  const evidence = evidenceView(capability.evidence)
  return {
    key: capabilityKey(track.track, capability),
    track: track.track,
    trackLabel: text(track.label) || track.track,
    title: text(capability.title) || '未命名能力',
    objective: text(capability.observable_objective),
    dimension: text(capability.dimension),
    dimensionLabel: text(capability.dimension_label) || '维度未知',
    difficulty: Number.isFinite(Number(capability.difficulty)) ? Number(capability.difficulty) : null,
    availabilityLabel: text(capability.availability_label) || '开放状态未知',
    open: text(capability.availability_label) === '已开放',
    knownPoints: (Array.isArray(capability.knowledge_points) ? capability.knowledge_points : [])
      .map(point => text(point?.name)).filter(Boolean),
    prerequisites: prerequisiteViews(capability.prerequisites),
    state: stateInfo(capability),
    evidence,
    retestAt: capability.retest_due_at || null,
    retestLabel: capability.retest_due_at ? formatDateTime(capability.retest_due_at) : '',
  }
}

export function trackViews(map) {
  const tracks = Array.isArray(map?.tracks) ? map.tracks : []
  return tracks.map(track => {
    const capabilities = (Array.isArray(track?.capabilities) ? track.capabilities : [])
      .map(capability => capabilityView(track, capability)).filter(Boolean)
    return {
      track: track.track,
      label: text(track.label) || text(track.track),
      capabilities,
      dimensions: (Array.isArray(track?.dimensions) ? track.dimensions : []).map(dimension => ({
        key: text(dimension?.dimension),
        label: text(dimension?.label) || '维度未知',
        displayLabel: studentLabel(text(dimension?.display_label)) || '状态未知',
        tone: text(dimension?.tone) || 'neutral',
        count: Number.isFinite(Number(dimension?.capability_count)) ? Number(dimension.capability_count) : null,
      })),
    }
  })
}

export function allCapabilities(map) {
  return trackViews(map).flatMap(track => track.capabilities)
}

export function findCapability(map, key) {
  return allCapabilities(map).find(capability => capability.key === key) || null
}

// 只有明确的“本节点关联”才可标；当前学生 map 没有节点到任务的映射，默认返回 null。
export function nodeTaskLink() {
  return null
}

// 后端任务用途是内部枚举值的中文直译，换成学生看得懂的说法。
const PURPOSE_LABELS = Object.freeze({
  '练习': '练习',
  '验收': '检验掌握',
  '受助后巩固': '用过提示后巩固',
  '新场景复测': '换新题复测',
  '新能力任务': '新能力练习',
})
export const purposeLabel = value => PURPOSE_LABELS[text(value)] || text(value)

// 后端文案里的评估术语（核验/证据等）收成学生用语；不改判断与结论。
const TERM_REPLACEMENTS = [
  [/尚未取得独立证据/g, '还没有独立完成过'],
  [/已有独立证据/g, '已独立完成'],
  [/独立证据/g, '独立完成'],
  [/核验未通过/g, '练习未通过'],
  [/核验通过/g, '练习通过'],
  [/重新核验/g, '重新确认'],
  [/核验服务异常/g, '平台暂时异常'],
  [/核验/g, '确认'],
  [/证据不足/g, '练习记录不足'],
  [/帮助记录缺失/g, '提示记录缺失'],
  [/使用了帮助/g, '用过提示或讲解'],
  [/受助后/g, '用过提示后'],
]
export function studentReason(value) {
  return TERM_REPLACEMENTS.reduce((result, [pattern, replacement]) => result.replace(pattern, replacement), text(value))
}

// 学生端推荐理由仍带目录稳定编码（G08）；呈现时收成教学用语，不用编码当文案。
export function sanitizeReason(value) {
  return studentReason(text(value)
    .replace(/目标能力\s+[A-Za-z0-9][A-Za-z0-9_-]*/g, '目标能力')
    .replace(/先修(?:能力)?\s+[A-Za-z0-9][A-Za-z0-9_-]*/g, '先修能力')
    .replace(/能力\s+[A-Z]{2,}[A-Z0-9_-]*/g, '该能力')
    .replace(/(目标能力|先修能力|该能力)\s+(?=[一-鿿])/g, '$1')
  )
    .replace(/\s{2,}/g, ' ')
    .trim()
}

export function recommendationView(item, track = 'both', generatedAt = null) {
  if (!item || !item.kind) return null
  const isTask = item.kind === 'task' && item.task
  return {
    kind: item.kind,
    priority: Number.isFinite(Number(item.priority)) ? Number(item.priority) : null,
    categoryLabel: text(item.category_label) || (isTask ? '任务推荐' : '基础诊断'),
    trackLabel: text(item.track_label),
    reason: sanitizeReason(item.reason_text),
    generatedAt,
    generatedLabel: formatDateTime(generatedAt),
    // 说明这是主线推荐，不是节点关联（没有精确映射）。
    relationNote: '本主线推荐',
    task: isTask ? {
      id: item.task.id,
      title: text(item.task.title) || '未命名任务',
      versionLabel: text(item.task.version_label),
      purposeLabel: purposeLabel(item.task.purpose_label),
    } : null,
    diagnosisTrack: item.kind === 'diagnosis'
      ? (item.track_label === '数据安全' ? 'data' : item.track_label === '网络安全' ? 'network' : (track === 'network' ? 'network' : 'data'))
      : null,
  }
}

export function recommendationViews(payload, track = 'both') {
  const items = Array.isArray(payload) ? payload : (Array.isArray(payload?.items) ? payload.items : [])
  return items.map(item => recommendationView(item, track, payload?.generated_at)).filter(Boolean)
}

// 诊断只安排学习顺序，不作为掌握依据；未答不记为不会。
export function diagnosisView(result) {
  if (!result) return null
  return {
    questionCount: Number(result.question_count) || 0,
    answeredCount: Number(result.answered_count) || 0,
    items: (Array.isArray(result.items) ? result.items : []).map(entry => ({
      title: text(entry?.title) || '未命名能力',
      label: text(entry?.result_label) || '已记录',
    })),
    note: '诊断只用来安排学习顺序，不代表已经学会；没有作答的题不会算作不会。',
  }
}

export function questionView(question) {
  return {
    key: text(question?.question_key),
    capabilityTitle: text(question?.capability_title) || '能力未知',
    dimensionLabel: text(question?.dimension_label) || '维度未知',
    prompt: text(question?.prompt),
    options: (Array.isArray(question?.options) ? question.options : []).map(option => ({
      key: text(option?.key), label: text(option?.label),
    })),
  }
}

export function changelogViews(payload) {
  const items = Array.isArray(payload) ? payload : (Array.isArray(payload?.items) ? payload.items : [])
  return items.map(entry => ({
    title: text(entry?.capability_title) || '学习路径',
    from: studentLabel(text(entry?.from_state_label)) || '未记录',
    to: studentLabel(text(entry?.to_state_label)) || '状态未知',
    reason: studentReason(text(entry?.reason_label)) || '原因未记录',
    time: entry?.created_at || null,
    timeLabel: formatDateTime(entry?.created_at),
  }))
}

export function catalogSummary(map) {
  const catalog = map?.catalog || {}
  return {
    versionLabel: text(catalog.version_label) || '版本未知',
    statusLabel: text(catalog.status_label) || '状态未知',
    published: Boolean(catalog.is_published),
    updatedLabel: formatDateTime(catalog.updated_at),
    openCapabilities: Number(map?.summary?.open_capabilities) || 0,
    independentCount: Number(map?.summary?.independent_count) || 0,
    assistedCount: Number(map?.summary?.assisted_count) || 0,
    needsPracticeCount: Number(map?.summary?.needs_practice_count) || 0,
    // 后端来源名是内部口径（如“平台核验记录”），展示时换成学生用语。
    dataSource: text(map?.versions?.data_source_label).replace(/核验/g, '练习') || '来源未提供',
  }
}

// 领取必须使用服务器返回的真实领取结果；当前站点没有对应任务工作面时如实说明。
export function claimResult(payload) {
  if (!payload || payload.attempt_id === undefined || payload.attempt_id === null) {
    return {
      ok: false,
      reason: '领取已受理，但暂时无法核对这次任务；请刷新后重试。',
    }
  }
  const task = payload.task || {}
  return {
    ok: true,
    attemptId: String(payload.attempt_id),
    taskTitle: text(task.title) || '任务',
    created: payload.created === true,
    message: payload.created === true
      ? `已领取《${text(task.title) || '任务'}》，可以开始完成了。`
      : `《${text(task.title) || '任务'}》已经领取过，可以继续完成。`,
    workSurface: null,
    reason: '这类任务目前还没有在线练习页面；请按任务材料完成后再提交，不要用材料阅读页代替练习。',
  }
}

export function errorText(error) {
  const data = error?.response?.data
  if (!data) return '网络或服务异常，请稍后重试。'
  if (typeof data === 'string') return data
  if (typeof data.detail === 'string') return data.detail
  if (data.detail && typeof data.detail.detail === 'string') return data.detail.detail
  return '操作未完成，请稍后重试。'
}
