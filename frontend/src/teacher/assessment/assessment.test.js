import test from 'node:test'
import assert from 'node:assert/strict'
import { createAssessmentState } from './state.js'
import { DIRECTIONS, emptyScoreForm, scorePayload, scoreText, trendRows } from './presentation.js'
const defer = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no }); return { promise, resolve, reject } }
const today = '2026-11-03'
const students = [{ id: 1, username: '学生甲' }, { id: 2, username: '学生乙' }]
const scores = id => ({ results: [{ id: id * 10, student: id, measured_at: today, total_score: 0 }], effective_score_ids: [], score_summary: { final_score: null }, filter_rules: { valid_score_days: 90, min_interval_days: 7 } })
async function setup(overrides = {}) {
  const api = { students: async () => students, scores: async id => scores(id), plan: async student => ({ student, title: '真实安排', plan_items: [] }), save: async data => ({ ...data, id: 77 }), ...overrides }
  const model = createAssessmentState({ api, today }); model.setAccount('teacher:8'); await model.loadStudents()
  return { model, api, state: model.state }
}
function fill(state) { Object.assign(state.form, { total_score: 0, dimension_scores: Object.fromEntries(DIRECTIONS.map(item => [item.key, 0])), tagsText: '基础, 复盘，专项', remark: '实际观察' }) }
test('score input preserves all six directions, date, tags and remark without invented scores', () => {
  const form = emptyScoreForm(today)
  assert.equal(form.total_score, null)
  assert.equal(Object.keys(form.dimension_scores).length, 6)
  assert.throws(() => scorePayload(form, 1, today), /完整填写/)
  fill({ form })
  const payload = scorePayload(form, 1, today)
  assert.equal(payload.measured_at, today); assert.equal(payload.total_score, 0)
  assert.deepEqual(payload.dimension_scores, { web: 0, crypto: 0, pwn: 0, reverse: 0, forensics: 0, misc: 0 })
  assert.deepEqual(payload.tags, ['基础', '复盘', '专项']); assert.equal(payload.remark, '实际观察')
})
test('invalid, future and impossible calendar dates and incomplete scores cannot write', async () => {
  let writes = 0
  const { model, state } = await setup({ save: async () => { writes++ } })
  fill(state)
  for (const date of ['', '2026-02-30', '2026-11-04']) { state.form.measured_at = date; assert.equal(await model.save(), false) }
  state.form.measured_at = today
  for (const value of [null, '', undefined, true, 101, -1]) { state.form.dimension_scores.web = value; assert.equal(await model.save(), false) }
  assert.equal(writes, 0)
})
test('missing and zero scores remain distinct, trends retain direction filter and actual dates', () => {
  assert.equal(scoreText(null), '—'); assert.equal(scoreText(undefined), '—'); assert.equal(scoreText(0), '0.00 分')
  const rows = [{ id: 1, measured_at: '2026-11-03', total_score: 90, dimension_scores: { web: 0 } }, { id: 2, measured_at: '2026-10-01', total_score: null }]
  assert.deepEqual(trendRows(rows, 'web').map(row => [row.date, row.value]), [['2026-10-01', null], ['2026-11-03', 0]])
  assert.equal(trendRows(rows, 'total')[1].value, 90)
})
test('roster failure has no demo students, retry reads the real roster', async () => {
  let fail = true
  const model = createAssessmentState({ api: { students: async () => { if (fail) throw Error(); return [] } }, today })
  model.setAccount('teacher:8'); await model.loadStudents()
  assert.deepEqual(model.state.students, []); assert.match(model.state.rosterError, /重试/)
  fail = false; await model.loadStudents(); assert.equal(model.state.rosterError, '')
})
test('assessment never requests data without an authorized selected roster student', async () => {
  const calls = []
  const { model, state } = await setup({ scores: async id => { calls.push(id); return scores(id) } })
  await model.selectStudent(999); await model.readSelection(); await model.save()
  assert.deepEqual(calls, [1]); assert.equal(state.studentId, '')
})
test('changing student clears drafts and ignores late score and plan responses', async () => {
  const first = defer(), second = defer(), plan = defer()
  const { model, api, state } = await setup()
  fill(state); api.scores = id => id === 1 ? first.promise : second.promise; api.plan = id => id === 1 ? plan.promise : Promise.resolve({ student: id })
  const older = model.selectStudent(1), newer = model.selectStudent(2)
  assert.equal(state.form.remark, ''); assert.equal(state.summary, null)
  first.resolve(scores(1)); plan.resolve({ student: 1 }); await older
  assert.equal(state.loading, true); assert.equal(state.plan?.student, 2); assert.deepEqual(state.rows, [])
  second.resolve(scores(2)); await newer; assert.equal(state.rows[0].student, 2)
})
test('scores and plan failures are isolated and old successful data is not retained', async () => {
  const { model, api, state } = await setup()
  api.scores = async () => { throw Error('failed') }
  await model.readSelection()
  assert.deepEqual(state.rows, []); assert.equal(state.summary, null); assert.match(state.scoresError, /重试/); assert.equal(state.plan.student, 1)
  api.scores = async id => scores(id); api.plan = async () => { throw Error('failed') }
  await model.readSelection(); assert.equal(state.rows.length, 1); assert.match(state.planError, /不影响/); assert.equal(state.plan, null)
})
test('confirmed write is followed by genuine readback, not local fake history or total', async () => {
  const writes = []; let persisted = false
  const { model, state } = await setup({ save: async data => { writes.push(data); persisted = true; return { ...data, id: 77 } }, scores: async id => persisted ? { ...scores(id), results: [{ id: 77, student: id }], score_summary: { final_score: 37.5 } } : scores(id) })
  fill(state); assert.equal(await model.save(), true)
  assert.equal(writes.length, 1); assert.equal(writes[0].student, 1); assert.equal(state.rows[0].id, 77); assert.equal(state.summary.final_score, 37.5); assert.match(state.message, /已读回/); assert.equal(state.form.remark, '')
})
test('failed and unconfirmed writes retain input and cannot create optimistic success', async () => {
  for (const save of [async () => { throw Error('offline') }, async () => ({}), async () => ({ id: 77, student: 2 })]) {
    const { model, state } = await setup({ save }); fill(state)
    assert.equal(await model.save(), false); assert.equal(state.form.remark, '实际观察'); assert.equal(state.rows[0].id, 10); assert.match(state.message, /未能确认/)
  }
})
test('readback failure after confirmed POST is not called unsaved and does not repeat the write', async () => {
  let writes = 0
  const { model, api, state } = await setup({ save: async data => { writes++; return { ...data, id: 77 } } })
  fill(state); api.scores = async () => { throw Error('read failed') }
  assert.equal(await model.save(), true); assert.equal(writes, 1); assert.match(state.message, /评分已保存.*不要重复提交/)
})
test('double submission is blocked, and account switch discards late write effects', async () => {
  const pending = defer(); let writes = 0
  const { model, state } = await setup({ save: () => { writes++; return pending.promise } })
  fill(state); const first = model.save(); assert.equal(await model.save(), false)
  model.setAccount('teacher:9'); assert.equal(state.studentId, ''); assert.equal(state.form.remark, '')
  pending.resolve({ id: 77, student: 1 }); await first
  assert.equal(writes, 1); assert.deepEqual(state.rows, []); assert.equal(state.message, '')
})
test('account switch, logout and disposal reject late rosters and reads', async () => {
  const pending = defer(); const model = createAssessmentState({ api: { students: () => pending.promise }, today })
  model.setAccount('teacher:8'); const request = model.loadStudents(); model.setAccount(null); pending.resolve(students); await request
  assert.deepEqual(model.state.students, [])
  let calls = 0; const { model: next, api, state } = await setup(); const late = defer(); api.scores = () => { calls++; return late.promise }
  const read = next.readSelection(); next.dispose(); late.resolve(scores(1)); await read
  assert.deepEqual(state.rows, []); assert.equal(calls, 1)
})
test('POST with an ID followed by stale history or an empty plan never claims full readback', async () => {
  for (const plan of [async student => ({ student }), async () => null]) {
    const { model, state } = await setup({ plan }); fill(state)
    assert.equal(await model.save(), true)
    assert.equal(state.rows[0].id, 10)
    assert.match(state.message, /评分已保存.*暂未读回/)
    assert.doesNotMatch(state.message, /评分记录与教学方案已读回/)
  }
})
test('unconfirmed score writes require a successful history reload before resubmission', async () => {
  let writes = 0
  const { model, api, state } = await setup({ save: async () => { writes++; throw Error('lost response') } }); fill(state)
  await model.save(); assert.equal(state.needsReconciliation, true)
  await model.save(); assert.equal(writes, 1)
  api.scores = async () => { throw Error('offline') }
  await model.readSelection(); await model.save(); assert.equal(writes, 1); assert.equal(state.form.remark, '实际观察')
  api.scores = async id => scores(id); await model.readSelection(); assert.equal(state.needsReconciliation, false)
  api.save = async data => ({ ...data, id: 77 }); assert.equal(await model.save(), true)
})
test('score reads without student binding and plans for a different student are rejected', async () => {
  const { model, api, state } = await setup()
  api.scores = async () => ({ results: [{ id: 77 }], effective_score_ids: [] })
  api.plan = async () => ({ title: 'Unbound plan' })
  await model.readSelection(); assert.equal(state.rows.length, 0); assert.equal(state.plan, null)
  assert.match(state.scoresError, /未能读取/); assert.match(state.planError, /未能读取/)
})
test('non-teacher accounts and non-student roster entries cannot enable score writes', async () => {
  let calls = 0
  const model = createAssessmentState({ api: { students: async () => { calls++; return [] } }, today })
  model.setAccount('admin:8'); await model.loadStudents(); assert.equal(calls, 0)
  const { model: next, state } = await setup({ students: async () => [{ id: 1, role: 'student' }, { id: 2, role: 'teacher' }, { id: true }, { id: '' }] })
  assert.equal(state.students.length, 1); await next.selectStudent(2); assert.equal(state.studentId, '')
})
test('container values are not accepted as numeric scores', () => {
  const form = emptyScoreForm(today); fill({ form })
  for (const value of [[], [50], {}, { valueOf: () => 20 }]) {
    form.total_score = value; assert.throws(() => scorePayload(form, 1, today), /完整填写/)
  }
})
