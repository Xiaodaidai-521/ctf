// 成长图谱的表现层：只做“真实字段 → 展示值”的换算，不补造数据。
// 这里的所有函数都是纯函数，测试直接加载本文件核对每个来源的口径。

export const ACTIVITY_WINDOWS = Object.freeze([7, 30, 90])

const isBlank = value => value === null || value === undefined || (typeof value === 'string' && value.trim() === '')

export function finite(value) {
  if (isBlank(value) || !['number', 'string'].includes(typeof value)) return null
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

export function clampPercent(value) {
  const number = finite(value)
  if (number === null) return null
  return Math.max(0, Math.min(100, Math.round(number)))
}

// analytics.progressReport.completion_rate 是 0–1 的比例。
export function percentFromRatio(value) {
  const number = finite(value)
  if (number === null) return null
  return clampPercent(number * 100)
}

// submission.stats.completion_rate 已经是 0–100 的百分数，不能再乘 100。
export function percentFromScale(value) {
  return clampPercent(value)
}

export function formatPercent(value) {
  const number = finite(value)
  return number === null ? '—' : `${Math.round(number)}%`
}

// 两个来源各自换算、各自标注分母；不把二者合并成一个“总完成率”。
export function progressSources(report, stats) {
  return {
    modules: {
      percent: percentFromRatio(report?.completion_rate),
      completed: finite(report?.completed_modules),
      total: finite(report?.total_modules),
      label: '本人已产生模块进度的记录',
    },
    submissions: {
      percent: percentFromScale(stats?.completion_rate),
      completed: finite(stats?.completed_modules),
      total: finite(stats?.total_modules),
      label: '本人做题与模块记录',
    },
  }
}

export function defaultPersonaSummary(persona) {
  if (!persona) return ''
  return typeof persona.summary === 'string' ? persona.summary : ''
}

export function personaTags(persona) {
  const tags = persona?.persona_traits?.tags ?? persona?.tags ?? persona?.persona_tags
  return Array.isArray(tags) ? tags.filter(tag => typeof tag === 'string' && tag.trim()) : []
}

export function nextActionsFrom(persona, recommendations) {
  const fromPersona = Array.isArray(persona?.persona_traits?.next_actions) ? persona.persona_traits.next_actions : []
  if (fromPersona.length) return fromPersona.slice(0, 3).map(text => ({ text, source: '画像建议' }))
  const fromRecommendations = (Array.isArray(recommendations) ? recommendations : []).slice(0, 3)
  return fromRecommendations.map(item => ({ text: item?.title || item?.reason || '查看学习推荐', source: '学习推荐' }))
}

export function canUseWindow(days) {
  return ACTIVITY_WINDOWS.includes(Number(days))
}

// 学习效果接口：只接受 7/30/90 且必须回显同一窗口，避免旧窗口响应覆盖新窗口。
export function normalizeEffect(payload, days) {
  if (!payload || !canUseWindow(days)) return null
  const requested = Number(days)
  const returned = finite(payload?.period?.days)
  if (returned !== requested) return null
  const snapshot = payload?.snapshot ?? null
  const daily = Array.isArray(payload?.daily_stats) ? payload.daily_stats : []
  const dailyStats = daily.map(item => {
    // 已返回的正式秒数字段即使为空也不能被旧字段的数值覆盖。
    const field = ['effective_learning_seconds', 'study_seconds', 'seconds', 'total_seconds'].find(key => Object.hasOwn(item || {}, key))
    const seconds = finite(item?.[field])
    const rawSeconds = seconds !== null && seconds >= 0 ? seconds : null
    return { date: item?.date ?? '', minutes: secondsToMinutes(rawSeconds), rawSeconds }
  }).filter(item => typeof item.date === 'string' && item.date)
  return {
    days: requested,
    startDate: payload?.period?.start_date ?? '',
    endDate: payload?.period?.end_date ?? '',
    periodLabel: payload?.period?.start_date && payload?.period?.end_date ? `${payload.period.start_date} 至 ${payload.period.end_date}` : '',
    hasSnapshot: snapshot !== null && typeof snapshot === 'object' && !Array.isArray(snapshot) && Object.keys(snapshot).length > 0,
    snapshotAt: snapshot?.calculated_at ?? snapshot?.snapshot_time ?? snapshot?.generated_at ?? payload?.snapshot_time ?? '',
    dailyStats,
    hasDaily: dailyStats.length > 0,
    recommendations: Array.isArray(payload?.recommendations) ? payload.recommendations : [],
    message: payload?.message ?? '',
  }
}

// 秒 → 分钟唯一入口；缺失保持缺失，0 秒就是 0 分钟。
export function secondsToMinutes(seconds) {
  const number = finite(seconds)
  if (number === null || number < 0) return null
  return Math.round(number / 60)
}

export function formatMinutes(value) {
  const number = finite(value)
  return number === null ? '—' : `${number} 分钟`
}

export function formatMemoryRate(value) {
  const number = finite(value)
  if (number === null || number < 0 || number > 1) return '—'
  return `${Math.round(number * 100)}%`
}

export function formatDate(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' })
}

// 周报只使用接口真实字段；字段不足或空响应都视为“暂无周报”，不填固定值。
const WEEKLY_FIELDS = ['week_start', 'total_study_minutes', 'modules_completed', 'exercises_completed', 'concepts_mastered', 'ai_interactions', 'sandbox_executions', 'generated_at']
export function weeklyReport(payload, now = new Date()) {
  if (!payload || typeof payload !== 'object') return null
  if (!payload.week_start) return null
  const report = {}
  for (const field of WEEKLY_FIELDS) report[field] = payload[field] ?? null
  // 周报字段本身就是分钟，不再做秒换算；缺失保持 null。
  report.total_study_minutes = finite(payload.total_study_minutes)
  const start = parseWeekStart(payload.week_start)
  const current = startOfWeek(now)
  const isCurrent = Boolean(start && start.getTime() === current.getTime())
  return { ...report, isCurrentWeek: isCurrent, label: isCurrent ? '本周周报' : '最近一期周报' }
}

// 纯日期字符串按本地日历解释，避免 UTC 解析后与本地周一错开一天。
function parseWeekStart(value) {
  const text = String(value)
  const match = text.match(/^(\d{4})-(\d{2})-(\d{2})/)
  if (!match) {
    const date = new Date(value)
    return Number.isNaN(date.getTime()) ? null : date
  }
  return new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]))
}

function startOfWeek(date) {
  const copy = new Date(date.getFullYear(), date.getMonth(), date.getDate())
  const day = copy.getDay() || 7
  copy.setDate(copy.getDate() - day + 1)
  return copy
}

// 六方向雷达：只画后台有真实评分/学习证据的方向。数据不足的方向保持空值，
// 不用 0 分参与优势/短板比较，也不把“上次减分”造出来。
export function directionRows(directions, growth, { hasSelfAssessment = false } = {}) {
  const list = Array.isArray(directions) ? directions : []
  const initial = growth?.initial_scores || {}
  const dynamic = growth?.dynamic_scores || {}
  const evidence = growth?.growth_evidence || {}
  return list.map(direction => {
    const key = direction?.key
    if (!key) return null
    const record = evidence[key] || {}
    const status = record.status || ''
    const currentRaw = finite(dynamic[key])
    const initialRaw = finite(initial[key])
    // dynamic 为 0 且证据表明没有学习数据 → 视为未知；有真实尝试的 0 分保留。
    const currentKnown = currentRaw !== null && (currentRaw !== 0 || status === 'grown' || status === 'steady' || status === 'declining' || (record.attempts ?? 0) > 0)
    const initialKnown = initialRaw !== null && (initialRaw !== 0 || hasSelfAssessment)
    return {
      key,
      label: direction?.label || direction?.name || key,
      initial: initialKnown ? initialRaw : null,
      current: currentKnown ? currentRaw : null,
      delta: initialKnown && currentKnown ? Math.round((currentRaw - initialRaw) * 100) / 100 : null,
      status,
      attempts: finite(record.attempts),
      correctRate: finite(record.correct_rate),
      insufficient: status === 'insufficient_data' || !currentKnown,
    }
  }).filter(Boolean)
}

export function extremeDirections(rows, field = 'current') {
  const known = (Array.isArray(rows) ? rows : []).filter(row => finite(row?.[field]) !== null)
  if (!known.length) return { strongest: null, weakest: null }
  const sorted = known.slice().sort((a, b) => Number(b[field]) - Number(a[field]))
  return { strongest: sorted[0], weakest: sorted[sorted.length - 1] }
}

export function improvedDirection(rows) {
  const known = (Array.isArray(rows) ? rows : []).filter(row => finite(row?.delta) !== null)
  if (!known.length) return null
  return known.slice().sort((a, b) => Number(b.delta) - Number(a.delta))[0]
}

// 复习提醒：只呈现真实概率、到期与关联练习；“完成复习”是本人自报，不是掌握结论。
export function reviewRows(payload) {
  const list = Array.isArray(payload) ? payload : Array.isArray(payload?.results) ? payload.results : []
  return list.map((item, index) => ({
    id: item?.id ?? item?.state_id ?? `review-${index}`,
    concept: item?.concept_name || item?.concept || '复习项',
    memoryRate: formatMemoryRate(item?.recall_probability),
    dueAt: item?.due_at ?? item?.next_review_at ?? item?.scheduled_for ?? null,
    dueLabel: formatDate(item?.due_at ?? item?.next_review_at ?? item?.scheduled_for),
    challengeTitle: item?.challenge?.title || '',
    challengeId: item?.challenge?.id ?? null,
    reason: item?.reason || item?.review_reason || '',
    actionLink: item?.action_link || '',
  }))
}

export const REFERENCE_LABEL = '参考展示（不计入本人学情）'
