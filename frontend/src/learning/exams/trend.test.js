import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { normalizeTrend, scoreTrendOption } from './trend.js'

test('exam trend never invents scores for missing practice attempts', () => {
  const source = { dates: ['一', '二', '三', '四'], scores: [0, 60, 80, 90], theory_scores: [0, 60], practice_scores: [null, 75, null] }
  const trend = normalizeTrend(source)
  assert.deepEqual(trend.practice_scores, [null, 75, null, null])
  assert.deepEqual(trend.theory_scores, [0, 60, null, null])
  assert.deepEqual(trend.scores, [0, 60, 80, 90])
  assert.deepEqual(source.practice_scores, [null, 75, null])
})
test('exam trend accepts absent series and excludes invalid nonnumeric data', () => {
  assert.deepEqual(normalizeTrend(null), { dates: [], scores: [], theory_scores: [], practice_scores: [] })
  assert.deepEqual(normalizeTrend({ dates: ['一', '二', '三'], scores: [NaN, Infinity, 'oops'] }).scores, [null, null, null])
})
test('chart theme keeps a single axis, stable series identity, labels and distinct marks', () => {
  const css = readFileSync(new URL('../../shared/design/tokens.css', import.meta.url), 'utf8')
  const values = Object.fromEntries([...css.matchAll(/(--[\w-]+):\s*([^;]+);/g)].map(match => [match[1], match[2]]))
  const token = name => { assert.ok(name in values, `undeclared token ${name}`); return values[name] }
  const trend = normalizeTrend({ dates: ['一'], scores: [70], theory_scores: [80] })
  const options = scoreTrendOption(trend, token)
  assert.equal(Array.isArray(options.yAxis), false)
  assert.deepEqual(options.legend.data, ['总分', '理论', '实战'])
  assert.equal(options.tooltip.trigger, 'axis')
  assert.equal(options.tooltip.confine, true)
  assert.equal(options.tooltip.valueFormatter(null), '—')
  assert.equal(options.tooltip.valueFormatter(0), '0%')
  assert.equal(new Set(options.series.map(item => item.symbol)).size, 3)
  assert.equal(new Set(options.series.map(item => item.lineStyle.type)).size, 3)
  assert.ok(options.series.every(item => item.endLabel.show && item.symbolSize >= 8 && item.connectNulls === false))
  assert.deepEqual(options.series[2].data, [null])
  assert.deepEqual(options.color, ['--series-1', '--series-2', '--series-3'].map(token))
  assert.equal(scoreTrendOption(trend, name => name.startsWith('--motion-') ? '0ms' : token(name)).animationDuration, 0)
})
