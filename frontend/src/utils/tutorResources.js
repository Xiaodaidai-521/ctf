const RESOURCE_CENTER_TYPES = new Set([
  'resource', 'document', 'video', 'report', 'zip', 'course', 'textbook', 'ai_resource'
])

export const TUTOR_SURFACED_RESOURCES_KEY = 'tutorSurfacedResources'
const MAX_REMEMBERED_RESOURCES = 50

const browserSessionStorage = () => {
  try {
    return typeof window !== 'undefined' ? window.sessionStorage : null
  } catch {
    return null
  }
}

const resourceStorageKey = (item) => `${item.type}:${item.id || item.entry}`

export const normalizeTutorResource = (item) => {
  if (!item || typeof item !== 'object') return null
  const title = String(item.title || '').trim()
  const entry = String(item.entry || item.url || '').trim()
  if (!title || !entry) return null

  const type = String(item.type || item.resource_type || item.source_type || 'resource').trim().toLowerCase() || 'resource'
  const label = String(
    item.ai_generated_label || (RESOURCE_CENTER_TYPES.has(type) && entry.startsWith('/resources') ? 'AI多模态生成' : '')
  ).trim()
  const location = String(item.location || '').trim() || (
    label
      ? `资源中心 / ${label} / ${title}`
      : type === 'article'
        ? `社区 / 文章 / ${title}`
        : `资源中心 / ${title}`
  )

  return {
    id: String(item.id || item.object_id || item.resource_id || entry),
    title,
    type,
    entry,
    summary: String(item.summary || item.description || '').trim(),
    ai_generated_label: label,
    location
  }
}

export const normalizeTutorResources = (items) => {
  if (!Array.isArray(items)) return []
  const seen = new Set()
  return items
    .map(normalizeTutorResource)
    .filter((item) => {
      if (!item) return false
      const key = resourceStorageKey(item)
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
}

export const tutorResourceListFromResponse = (response) => {
  const direct = response?.resourceList || response?.resources
  const prepared = response?.resourcePreparation?.resourceList || response?.resourcePreparation?.resources
  return normalizeTutorResources(Array.isArray(direct) ? direct : prepared)
}

export const loadRememberedTutorResources = () => {
  const storage = browserSessionStorage()
  if (!storage) return []
  try {
    return normalizeTutorResources(JSON.parse(storage.getItem(TUTOR_SURFACED_RESOURCES_KEY) || '[]'))
  } catch {
    return []
  }
}

export const rememberTutorResources = (items) => {
  const incoming = normalizeTutorResources(items)
  if (!incoming.length) return loadRememberedTutorResources()
  const existing = loadRememberedTutorResources()
  const merged = []
  const seen = new Set()
  for (const item of [...incoming, ...existing]) {
    const key = resourceStorageKey(item)
    if (seen.has(key)) continue
    seen.add(key)
    merged.push(item)
    if (merged.length >= MAX_REMEMBERED_RESOURCES) break
  }
  const storage = browserSessionStorage()
  if (storage) storage.setItem(TUTOR_SURFACED_RESOURCES_KEY, JSON.stringify(merged))
  return merged
}

export const clearRememberedTutorResources = () => {
  const storage = browserSessionStorage()
  if (storage) storage.removeItem(TUTOR_SURFACED_RESOURCES_KEY)
}

const resourceIdFromEntry = (entry) => {
  const text = String(entry || '').trim()
  if (!text.startsWith('/resources')) return null
  try {
    const url = new URL(text, 'https://local.invalid')
    const raw = url.searchParams.get('highlight_resource') || url.searchParams.get('resource')
    const value = Number(raw)
    return Number.isFinite(value) && value > 0 ? value : null
  } catch {
    return null
  }
}

export const tutorResourceCenterIds = (items = loadRememberedTutorResources()) => {
  const ids = []
  const seen = new Set()
  for (const item of normalizeTutorResources(items)) {
    if (!RESOURCE_CENTER_TYPES.has(item.type) || !item.entry.startsWith('/resources')) continue
    const numericId = Number(item.id)
    const id = Number.isFinite(numericId) && numericId > 0 ? numericId : resourceIdFromEntry(item.entry)
    if (!id || seen.has(id)) continue
    seen.add(id)
    ids.push(id)
  }
  return ids
}