// 学习面共享的数据形状适配：只做形状识别与最小换算，不补造业务值。
export function asList(value) {
  if (Array.isArray(value)) return value
  if (Array.isArray(value?.results)) return value.results
  if (Array.isArray(value?.items)) return value.items
  return []
}

// 保留 count/next/分页范围，页面据此说明“当前已加载”而不是冒充全量。
export function pageInfo(value, pageSize = 20) {
  const list = asList(value)
  const count = Number.isFinite(Number(value?.count)) ? Number(value.count) : null
  return {
    items: list,
    count,
    hasNext: Boolean(value?.next) || (count !== null && list.length < count),
    loaded: list.length,
    pageSize,
  }
}

export function finiteNumber(value) {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

// analytics.progressReport.completion_rate 是 0–1；submission.stats.completion_rate 是 0–100。
export function ratioPercent(value, source) {
  const n = finiteNumber(value)
  if (n === null || n < 0) return null
  const percent = source === 'progress-report' && n <= 1 ? n * 100 : n
  return Math.max(0, Math.min(100, Math.round(percent * 100) / 100))
}

export function isoTime(value) {
  if (!value) return null
  const time = Date.parse(value)
  return Number.isFinite(time) ? new Date(time).toISOString() : null
}

export function latestBy(items, field = 'updated_at') {
  return asList(items)
    .map(item => ({ item, time: Date.parse(item?.[field]) || 0 }))
    .sort((a, b) => b.time - a.time)[0]?.item || null
}
