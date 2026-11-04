import { countValue, directionLabel, listValue, numberValue } from '../governance/data.js'
export function platformStats(sources) {
  const data = key => sources[key]?.error ? null : sources[key]?.data
  const rows = data('challenges') == null ? null : listValue(data('challenges'))
  const rate = numberValue(data('submissions')?.success_rate)
  return { rankedUsers: countValue(data('leaderboard')?.total), totalUsers: countValue(data('users')?.total),
    totalChallenges: rows?.length ?? null, totalSubmissions: countValue(data('submissions')?.total_submissions),
    successRate: rate !== null && rate >= 0 && rate <= 100 ? rate : null,
    newUsers: null, activeChallenges: null, totalScore: null, avgScore: null }
}
export function challengeDistributions(data) {
  if (data == null) return { categories: [], difficulties: [] }
  const rows = listValue(data), categories = new Map(), difficulties = new Map()
  const labels = { easy: '简单', medium: '中等', hard: '困难', expert: '专家' }
  for (const row of rows) {
    const category = row.category_name || '未分类', difficulty = labels[row.difficulty] || '未标注'
    categories.set(category, (categories.get(category) || 0) + 1)
    difficulties.set(difficulty, (difficulties.get(difficulty) || 0) + 1)
  }
  const distribution = map => [...map].map(([name, count]) => ({ name, count, percentage: Math.round(count / rows.length * 100) }))
  return { categories: distribution(categories), difficulties: distribution(difficulties) }
}
export function studentSummary(rows) {
  const mastery = rows.map(row => numberValue(row.mastery)).filter(value => value !== null && value >= 0 && value <= 100)
  const solved = rows.map(row => countValue(row.solved_count))
  const onboarded = rows.filter(row => typeof row.onboarded === 'boolean')
  return { students: rows.length, onboarded: onboarded.filter(row => row.onboarded).length, onboardedSamples: onboarded.length,
    averageMastery: mastery.length ? Math.round(mastery.reduce((sum, value) => sum + value, 0) / mastery.length) : null,
    masterySamples: mastery.length,
    correctSubmissions: solved.every(value => value !== null) ? solved.reduce((sum, value) => sum + value, 0) : null }
}
export const validityLabel = value => ({ effective: '有效', filtered: '间隔过短', expired: '已过期', invalid: '日期无效', unknown: '待确认' }[value] || '待确认')
export function scoreTrend(rows, direction = 'total') {
  return [...rows].sort((a, b) => String(a.measured_at).localeCompare(String(b.measured_at))).map(row => {
    const value = numberValue(direction === 'total' ? row.total_score : row.dimension_scores?.[direction])
    return { date: row.measured_at || '日期未提供', value: value !== null && value >= 0 && value <= 100 ? value : null, validity: validityLabel(row.validity_status) }
  })
}
export const directions = ['web', 'crypto', 'pwn', 'reverse', 'forensics', 'misc'].map(key => ({ key, label: directionLabel(key) }))
export const percentLabel = value => { const number = numberValue(value); return number !== null && number >= 0 && number <= 100 ? `${number}%` : '未提供' }
export const conceptLabel = value => { const number = numberValue(value); return number !== null && number >= 0 && number <= 1 ? `${Math.round(number * 100)}%` : '未提供' }
export const selfRatingLabel = value => { const number = numberValue(value); return number !== null && number >= 0 && number <= 5 ? `${number} / 5` : '未填写' }
