import api from '@/api'
import { asList, finiteNumber } from '@/learning/contracts.js'

export const pathsApi = {
  list: params => api.learningPaths.list(params),
  detail: id => api.learningPaths.detail(id),
  start: id => api.learningPaths.start(id),
  progress: id => api.learningPaths.progress(id),
  my: () => api.learningPaths.my(),
  recommendations: () => api.learningPaths.recommendations(),
  modules: params => api.pathModules.list(params),
  module: id => api.pathModules.detail(id),
  startModule: id => api.pathModules.start(id),
  completeModule: id => api.pathModules.complete(id),
  labs: id => api.pathModules.labs(id),
  concepts: params => api.knowledgeGraph.concepts(params),
}

// 本人是否已加入：以后端返回的 progress 记录为准，读失败不等于未加入。
export function membership(progress, pathId) {
  const list = asList(progress)
  const match = list.find(item => String(item.learning_path) === String(pathId))
  return { joined: Boolean(match), record: match || null, known: true }
}

export function moduleTarget(path) {
  const pathId = finiteNumber(path?.learning_path ?? path?.id)
  const moduleId = finiteNumber(path?.current_module)
  if (!pathId) return '/learning-paths'
  return moduleId ? `/learning-paths/${pathId}/modules/${moduleId}` : `/learning-paths/${pathId}`
}

// 完成率/时长缺失时不补 0 或假时长。
export function progressSummary(record) {
  if (!record) return { percent: null, anomaly: false, rawPercent: null, completed: null, total: null, hourLabel: '—' }
  const completed = finiteNumber(record.completed_modules)
  const total = finiteNumber(record.total_modules)
  let percent = finiteNumber(record.completion_rate)
  if (percent !== null && percent <= 1) percent *= 100
  if (percent === null && completed !== null && total) percent = (completed / total) * 100
  const raw = percent === null ? null : Math.round(percent)
  return {
    percent: raw === null ? null : Math.max(0, Math.min(100, raw)),
    // 超过 100% 属于数据异常，页面据此如实提示而不是当成正常满进度。
    anomaly: raw !== null && raw > 100,
    rawPercent: raw,
    completed, total,
    hourLabel: finiteNumber(record.hours_spent) !== null ? `${finiteNumber(record.hours_spent)} 小时` : '—',
  }
}

export function readableRequires(requires, modules) {
  return asList(requires).map(ref => {
    const id = finiteNumber(ref)
    const module = asList(modules).find(item => finiteNumber(item.id) === id)
    return module?.title || null
  })
}
