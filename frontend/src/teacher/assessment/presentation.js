import { finite } from '../../shared/learning/presentation.js'
export const DIRECTIONS = Object.freeze([
  { key: 'web', label: 'Web安全' }, { key: 'crypto', label: '密码学' },
  { key: 'pwn', label: '二进制安全' }, { key: 'reverse', label: '逆向工程' },
  { key: 'forensics', label: '数字取证' }, { key: 'misc', label: '综合杂项' },
])
export function localToday(now = new Date()) {
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`
}
export function emptyScoreForm(today = localToday()) {
  return { measured_at: today, total_score: null, dimension_scores: Object.fromEntries(DIRECTIONS.map(item => [item.key, null])), tagsText: '', remark: '' }
}
export function scorePayload(form, student, today = localToday()) {
  const date = String(form.measured_at || '')
  const parsed = new Date(`${date}T12:00:00`)
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || Number.isNaN(parsed.getTime()) || localToday(parsed) !== date || date > today) throw new Error('请填写真实测评日期，不能晚于今天。')
  const score = value => {
    const number = finite(value)
    if (number === null || number < 0 || number > 100) throw new Error('请完整填写总分与六个方向评分，范围为 0–100。')
    return number
  }
  return { student, measured_at: date, total_score: score(form.total_score),
    dimension_scores: Object.fromEntries(DIRECTIONS.map(item => [item.key, score(form.dimension_scores[item.key])])),
    tags: String(form.tagsText || '').split(/[,，]/).map(item => item.trim()).filter(Boolean), remark: String(form.remark || '') }
}
export const scoreText = value => finite(value) === null ? '—' : `${finite(value).toFixed(2)} 分`
export const validityLabel = value => ({ effective: '有效', filtered: '频繁或非最新评分', expired: '已过期', invalid: '无效日期' }[value] || '待确认')
export function trendRows(rows, mode) {
  return [...rows].sort((a, b) => String(a.measured_at).localeCompare(String(b.measured_at))).map(row => ({
    id: row.id, date: row.measured_at, value: finite(mode === 'total' ? row.total_score : row.dimension_scores?.[mode]), validity: validityLabel(row.validity_status),
  }))
}
