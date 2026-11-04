// 成长总览的分区定位：URL 契约沿用 shared/navigation/phase2.js 的四个真实分区，
// 这里只把分区映射到页面锚点，避免页面内再造一套 section 名称。
import { parseGrowthSection } from '../../shared/navigation/phase2.js'

export const GROWTH_SECTION_TARGETS = Object.freeze({
  overview: 'growth-overview',
  capability: 'growth-mastery',
  activity: 'growth-activity',
  results: 'growth-results',
})

const SECTION_QUERY = Object.freeze({
  'growth-overview': 'overview',
  'growth-mastery': 'capability',
  'growth-activity': 'activity',
  'growth-results': 'results',
})

// 旧页面参数与锚点仍可定位；未知值返回 null，由页面决定是否停在顶部。
const ALIASES = Object.freeze({
  overview: 'overview',
  activity: 'activity',
  analysis: 'activity',
  analytics: 'activity',
  results: 'results',
  review: 'results',
  capability: 'capability',
  mastery: 'capability',
  'growth-overview': 'overview',
  'growth-mastery': 'capability',
  'growth-activity': 'activity',
  'growth-results': 'results',
  'growth-report': 'overview',
  'growth-review': 'results',
  'growth-recommend': 'overview',
})

export function growthSection(value) {
  if (typeof value !== 'string') return null
  return ALIASES[value.trim()] || null
}

export function growthSectionTarget(value) {
  const section = growthSection(value)
  return section ? GROWTH_SECTION_TARGETS[section] : null
}

export function growthSectionQuery(id) {
  return SECTION_QUERY[id] || null
}

// 学习活动窗口只允许 7/30/90；其他值不纳入 URL 契约。
export function growthWindow(value) {
  const number = Number(value)
  return [7, 30, 90].includes(number) ? number : null
}

export { parseGrowthSection }
