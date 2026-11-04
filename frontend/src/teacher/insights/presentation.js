import { finite } from '../../shared/learning/presentation.js'
export const GROWTH_SECTIONS = Object.freeze([
  { key: 'overview', title: '成长总览' }, { key: 'activity', title: '学习活动' },
  { key: 'mastery', title: '掌握与能力' }, { key: 'recommendations', title: '推荐与航线' },
  { key: 'reviews', title: '复习提醒' }, { key: 'results', title: '结果与复盘' }, { key: 'report', title: '学习结论与报告' },
])
export const METRICS = Object.freeze([
  ['time_score', '学习投入指数'], ['completion_score', '课程进度指数'], ['mastery_score', '知识掌握指数'],
  ['retention_score', '记忆保持指数'], ['consistency_score', '学习连续性指数'], ['efficiency_score', '学习效率指数'],
  ['engagement_score', '练习参与指数'], ['focus_score', '学习专注指数'],
])
export function metricRows(payload) {
  return METRICS.map(([key, label]) => ({ key, label, value: finite(payload?.snapshot?.dimensions?.[key]) }))
}
// 报表在无概念/自评来源时返回的默认 0 不是实际掌握证据。
export const reportMastery = student => Array.isArray(student?.concepts) && student.concepts.length === 0 ? null : finite(student?.mastery)
export function filterStudents(students, query, sort) {
  const list = students.filter(student => String(student.username || '').toLowerCase().includes(String(query).trim().toLowerCase()))
  const date = item => Date.parse(item.self_assessed_at) || 0
  return [...list].sort((a, b) => sort === 'mastery' ? (reportMastery(b) ?? -1) - (reportMastery(a) ?? -1) : date(b) - date(a))
}
export const countText = value => finite(value) === null ? '—' : String(finite(value))
export const metricText = value => finite(value) === null ? '—' : `${finite(value).toFixed(2)} / 100`
