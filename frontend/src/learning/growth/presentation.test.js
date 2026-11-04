import test from 'node:test'
import assert from 'node:assert/strict'
import {
  ACTIVITY_WINDOWS, REFERENCE_LABEL, clampPercent, directionRows, extremeDirections,
  formatMemoryRate, improvedDirection, nextActionsFrom, normalizeEffect, percentFromRatio,
  percentFromScale, progressSources, reviewRows, secondsToMinutes, weeklyReport,
} from './presentation.js'

test('completion rates keep their source scale instead of being squashed together', () => {
  // analytics.progressReport.completion_rate 是 0–1；1 必须是 100%，不是 1%。
  assert.equal(percentFromRatio(0.01), 1)
  assert.equal(percentFromRatio(1), 100)
  assert.equal(percentFromRatio(0.756), 76)
  assert.equal(percentFromRatio(null), null)
  // submission.stats.completion_rate 已经是 0–100，不能再乘 100。
  assert.equal(percentFromScale(76), 76)
  assert.equal(percentFromScale(100), 100)
  assert.equal(percentFromScale(undefined), null)
  assert.equal(clampPercent(-4), 0)
  assert.equal(clampPercent(140), 100)

  const sources = progressSources({ completion_rate: 0.5, completed_modules: 2, total_modules: 4 }, { completion_rate: 76, completed_modules: 19, total_modules: 25 })
  assert.equal(sources.modules.percent, 50)
  assert.equal(sources.modules.completed, 2)
  assert.match(sources.modules.label, /模块进度/)
  assert.equal(sources.submissions.percent, 76)
  assert.notEqual(sources.modules.label, sources.submissions.label)
})

test('learning activity only accepts 7/30/90 and converts seconds to minutes explicitly', () => {
  assert.deepEqual(ACTIVITY_WINDOWS, [7, 30, 90])
  assert.equal(secondsToMinutes(0), 0)
  assert.equal(secondsToMinutes(59), 1)
  assert.equal(secondsToMinutes(3600), 60)
  assert.equal(secondsToMinutes(null), null)
  const payload = {
    period: { days: 7, start_date: '2026-10-28', end_date: '2026-11-03' },
    snapshot: { snapshot_time: '2026-11-03T10:00:00Z' },
    daily_stats: [{ date: '2026-11-02', study_seconds: 3660 }, { date: '2026-11-03', seconds: 30 }],
    recommendations: [{ action_text: '继续练习', reason: '近一周投入稳定', evidence: { days: 7 } }],
  }
  const effect = normalizeEffect(payload, 7)
  assert.equal(effect.hasSnapshot, true)
  assert.equal(effect.snapshotAt, '2026-11-03T10:00:00Z')
  assert.equal(effect.periodLabel, '2026-10-28 至 2026-11-03')
  assert.deepEqual(effect.dailyStats.map(item => item.minutes), [61, 1])
  assert.equal(effect.dailyStats[0].rawSeconds, 3660)
  // 旧窗口或非法窗口的响应不得写入当前窗口。
  assert.equal(normalizeEffect(payload, 30), null)
  assert.equal(normalizeEffect(payload, 14), null)
  const empty = normalizeEffect({ period: { days: 30, start_date: '2026-10-05', end_date: '2026-11-03' }, snapshot: null, daily_stats: [], message: 'Analytics snapshot is not available yet.' }, 30)
  assert.equal(empty.hasSnapshot, false)
  assert.equal(empty.hasDaily, false)
  assert.equal(empty.message, 'Analytics snapshot is not available yet.')
})

test('weekly report uses real fields only and labels stale reports', () => {
  assert.equal(weeklyReport(null), null)
  assert.equal(weeklyReport({}), null)
  assert.equal(weeklyReport({ total_study_minutes: 320 }), null)
  const now = new Date('2026-11-03T12:00:00')
  const report = weeklyReport({
    week_start: '2026-11-02', total_study_minutes: 140, modules_completed: 2, exercises_completed: 5,
    concepts_mastered: 3, ai_interactions: 4, sandbox_executions: 1, generated_at: '2026-11-03T09:00:00Z',
    accuracy: 0.76, summary: 'keep out',
  }, now)
  assert.equal(report.isCurrentWeek, true)
  assert.equal(report.label, '本周周报')
  assert.equal(report.total_study_minutes, 140)
  assert.equal(report.modules_completed, 2)
  assert.equal(report.accuracy, undefined)
  assert.equal(report.summary, undefined)
  const stale = weeklyReport({ week_start: '2026-10-26', total_study_minutes: 90 }, now)
  assert.equal(stale.isCurrentWeek, false)
  assert.equal(stale.label, '最近一期周报')
  // 字段缺失保持 null，不补 0。
  assert.equal(stale.exercises_completed, null)
})

test('six-direction radar never turns missing evidence into a zero score', () => {
  const directions = [
    { key: 'web', label: 'Web 安全' }, { key: 'crypto', label: '密码学' },
    { key: 'pwn', label: '二进制安全' }, { key: 'reverse', label: '逆向工程' },
  ]
  const growth = {
    initial_scores: { web: 0, crypto: 0, pwn: 0, reverse: 0 },
    dynamic_scores: { web: 7.67, crypto: 0, pwn: 0, reverse: 5.3 },
    growth_evidence: {
      web: { status: 'grown', attempts: 3, correct_rate: 33.33 },
      crypto: { status: 'insufficient_data', attempts: 0 },
      pwn: { status: 'insufficient_data', attempts: 0 },
      reverse: { status: 'grown', attempts: 27, correct_rate: 3.7 },
    },
  }
  const rows = directionRows(directions, growth)
  assert.equal(rows[0].current, 7.67)
  assert.equal(rows[0].initial, null) // 没有自评时初始 0 不等于真实基线
  assert.equal(rows[1].current, null)
  assert.equal(rows[1].insufficient, true)
  assert.equal(rows[3].current, 5.3)
  const { strongest, weakest } = extremeDirections(rows)
  assert.equal(strongest.key, 'web')
  assert.equal(weakest.key, 'reverse')
  // 只有一次评分时没有 delta，不能造“上次减 8”。
  assert.equal(improvedDirection(rows), null)
  const withBaseline = directionRows(directions, growth, { hasSelfAssessment: true })
  assert.equal(withBaseline[0].initial, 0)
  assert.equal(withBaseline[0].delta, 7.67)
})

test('review reminders keep probability, due date and reason; completion stays self-reported', () => {
  assert.equal(formatMemoryRate(0.842), '84%')
  assert.equal(formatMemoryRate(1), '100%')
  assert.equal(formatMemoryRate(null), '—')
  assert.equal(formatMemoryRate(1.4), '—')
  const rows = reviewRows({ results: [{ id: 3, concept_name: '访问控制', recall_probability: 0.7, due_at: '2026-11-05', challenge: { id: 9, title: '边界检查' }, reason: '上次答错' }] })
  assert.equal(rows.length, 1)
  assert.equal(rows[0].memoryRate, '70%')
  assert.equal(rows[0].challengeId, 9)
  assert.equal(rows[0].dueLabel.includes('2026'), true)
  assert.equal(rows[0].reason, '上次答错')
  assert.deepEqual(reviewRows({ results: [] }), [])
  assert.deepEqual(reviewRows(null), [])
  assert.match(REFERENCE_LABEL, /不计入本人学情/)
})

test('next actions prefer persona advice and fall back to recommendations', () => {
  assert.deepEqual(nextActionsFrom({ persona_traits: { next_actions: ['先复盘错题'] } }), [{ text: '先复盘错题', source: '画像建议' }])
  assert.deepEqual(nextActionsFrom(null, [{ title: '练习 Web' }]), [{ text: '练习 Web', source: '学习推荐' }])
  assert.deepEqual(nextActionsFrom(null, []), [])
})
