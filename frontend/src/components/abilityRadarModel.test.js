import test from 'node:test'
import assert from 'node:assert/strict'
import { ABILITY_DIRECTIONS, abilityModel, abilityScore } from './abilityRadarModel.js'

test('missing ability scores stay missing instead of becoming zero', () => {
  assert.equal(abilityScore(null), null)
  assert.equal(abilityScore(undefined), null)
  assert.equal(abilityScore(''), null)
  assert.equal(abilityScore('not-a-number'), null)
  assert.equal(abilityScore(0), 0)
  assert.equal(abilityScore(-6), 0)
  assert.equal(abilityScore(120), 100)

  const empty = abilityModel()
  assert.equal(empty.hasInitial, false)
  assert.equal(empty.hasAnyScore, false)
  assert.equal(empty.strongest.score, null)
  assert.equal(empty.weakest.score, null)
  assert.equal(empty.improved.text, '待积累')

  // 有一个真实方向分时，优势/短板只在该方向内比较，不把其余缺值当 0。
  const partial = abilityModel({ initialScores: { web: 70 } })
  assert.equal(partial.hasInitial, true)
  assert.equal(partial.strongest.name, 'Web')
  assert.equal(partial.strongest.score, 70)
  assert.equal(partial.weakest.name, 'Web')
  assert.equal(partial.weakest.score, 70)
})

test('dynamic series requires backend eligibility and real scores', () => {
  const ineligible = abilityModel({ initialScores: { web: 40 }, dynamicScores: { web: 60 }, eligibleForAi: false })
  assert.equal(ineligible.hasDynamic, false)
  assert.equal(ineligible.improved.text, '待积累')

  const eligible = abilityModel({ initialScores: { web: 40 }, dynamicScores: { web: 60 }, eligibleForAi: true })
  assert.equal(eligible.hasDynamic, true)
  assert.equal(eligible.improved.name, 'Web')
  assert.equal(eligible.improved.text, '+20 分')

  // 只有一个方向两次评分，其他方向缺值不参与提升最大计算。
  const single = abilityModel({ initialScores: { web: 40, crypto: 80 }, dynamicScores: { web: 45, pwn: 90 }, eligibleForAi: true })
  assert.equal(single.improved.name, 'Web')
  assert.equal(single.improved.text, '+5 分')
  assert.equal(ABILITY_DIRECTIONS.length, 6)
})
