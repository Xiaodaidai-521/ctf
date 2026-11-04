// 六方向能力对比的纯计算层：缺值不是 0 分，单次评分不制造前后差值。
// 组件只负责画图与呈现；测试直接核对这里的判断。
export const ABILITY_DIRECTIONS = Object.freeze([
  { key: 'web', label: 'Web' }, { key: 'crypto', label: 'Crypto' },
  { key: 'pwn', label: 'Pwn' }, { key: 'reverse', label: 'Reverse' },
  { key: 'forensics', label: 'Forensics' }, { key: 'misc', label: 'Misc' },
])

export function abilityScore(value) {
  if (value === null || value === undefined || value === '') return null
  const number = Number(value)
  if (!Number.isFinite(number)) return null
  return Math.max(0, Math.min(100, number))
}

const scoreMap = (scores) => ABILITY_DIRECTIONS.map(item => abilityScore(scores?.[item.key]))

export function abilityModel({ initialScores = {}, dynamicScores = {}, eligibleForAi = false } = {}) {
  const labels = ABILITY_DIRECTIONS.map(item => item.label)
  const initial = scoreMap(initialScores)
  const dynamic = scoreMap(dynamicScores)
  const hasInitial = initial.some(value => value !== null)
  const hasDynamic = Boolean(eligibleForAi) && dynamic.some(value => value !== null)
  const current = hasDynamic ? dynamic : initial
  const known = current.map((value, index) => ({ value, index })).filter(entry => entry.value !== null)
  const strongest = known.length
    ? (() => { const top = known.reduce((best, entry) => (entry.value > best.value ? entry : best)); return { name: labels[top.index], score: top.value } })()
    : { name: '-', score: null }
  const weakest = known.length
    ? (() => { const bottom = known.reduce((best, entry) => (entry.value < best.value ? entry : best)); return { name: labels[bottom.index], score: bottom.value } })()
    : { name: '-', score: null }
  const deltas = []
  // 后台未允许动态画像时，不拿未启用的分数计算“提升最大”。
  for (let index = 0; hasDynamic && index < ABILITY_DIRECTIONS.length; index += 1) {
    const before = initial[index]
    const after = dynamic[index]
    if (before === null || after === null) continue
    deltas.push({ name: labels[index], delta: Math.round((after - before) * 100) / 100 })
  }
  const topDelta = deltas.length ? deltas.reduce((best, entry) => (entry.delta > best.delta ? entry : best)) : null
  return {
    labels,
    initial,
    dynamic,
    current,
    hasInitial,
    hasDynamic,
    hasAnyScore: hasInitial || hasDynamic,
    strongest,
    weakest,
    improved: topDelta ? { name: topDelta.name, text: `${topDelta.delta >= 0 ? '+' : ''}${topDelta.delta} 分` } : { name: '-', text: '待积累' },
  }
}
