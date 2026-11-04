// 靶场最小非敏感本机状态：筛选、滚动位置与上次题目引用；绝不保存 Flag。
export const FILTER_KEY = 'ctf:practice:filters'
export const VISIT_KEY = 'ctf:practice:last-visit'

export function defaultFilters() {
  return { category: null, difficulty: null, status: null }
}

export function readPreferences(storage = null) {
  if (!storage) return { filters: defaultFilters(), scrollTop: 0, lastVisit: null }
  try {
    const saved = JSON.parse(storage.getItem(FILTER_KEY) || 'null')
    const filters = saved && typeof saved === 'object'
      ? { category: saved.category ?? null, difficulty: saved.difficulty ?? null, status: saved.status ?? null }
      : defaultFilters()
    const visit = JSON.parse(storage.getItem(VISIT_KEY) || 'null')
    const lastVisit = visit && Number.isFinite(Number(visit.id))
      ? { id: Number(visit.id), title: String(visit.title || ''), at: Number(visit.at) || null }
      : null
    return { filters, scrollTop: Number(saved?.scrollTop) || 0, lastVisit }
  } catch {
    return { filters: defaultFilters(), scrollTop: 0, lastVisit: null }
  }
}

export function writeFilters(storage = null, filters, scrollTop = 0) {
  if (!storage) return
  try {
    storage.setItem(FILTER_KEY, JSON.stringify({
      category: filters?.category ?? null, difficulty: filters?.difficulty ?? null,
      status: filters?.status ?? null, scrollTop: Number(scrollTop) || 0,
    }))
  } catch { /* 本机存储不可用不影响练习。 */ }
}

// 只记录题目引用、标题与访问时间。
export function writeLastVisit(storage = null, challenge, at = Date.now()) {
  const id = Number(challenge?.id)
  if (!Number.isFinite(id)) return
  if (!storage) return
  try { storage.setItem(VISIT_KEY, JSON.stringify({ id, title: String(challenge.title || ''), at })) } catch { /* 忽略 */ }
}
