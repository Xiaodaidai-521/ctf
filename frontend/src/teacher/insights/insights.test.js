import test from 'node:test'
import assert from 'node:assert/strict'
import { createInsightsState } from './state.js'
import { GROWTH_SECTIONS, filterStudents, metricRows, reportMastery } from './presentation.js'
import { createLearningReadApi } from '../../shared/learning/api.js'
import * as shared from '../../shared/learning/presentation.js'
import * as student from '../../learning/growth/presentation.js'
const defer = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no }); return { promise, resolve, reject } }
const payload = (id, days, extra = {}) => ({ student: { id }, period: { days, start_date: '2026-10-28', end_date: '2026-11-03' }, snapshot: null, daily_stats: [], ...extra })
async function setup(overrides = {}) {
  const api = { students: async () => [{ id: 1, username: '甲' }, { id: 2, username: '乙' }], effect: async (id, days) => payload(id, days), plan: async student => ({ student }), ...overrides }
  const model = createInsightsState({ api }); model.setAccount('teacher:8'); await model.loadStudents(); return { model, state: model.state, api }
}
test('student compatibility exports are the exact shared pure presentation functions', () => {
  for (const key of Object.keys(student)) assert.equal(student[key], shared[key], key)
  assert.equal(student.normalizeEffect, shared.normalizeEffect)
})
test('real backend day seconds and snapshot timestamp now render identically in both views', () => {
  const raw = payload(1, 7, { snapshot: { calculated_at: '2026-11-03T10:00:00Z' }, daily_stats: [{ date: '2026-11-03', effective_learning_seconds: 3600 }, { date: '2026-11-02', effective_learning_seconds: 0 }, { date: '2026-11-01' }] })
  const a = shared.normalizeEffect(raw, 7), b = student.normalizeEffect(raw, 7)
  assert.deepEqual(a, b); assert.equal(a.snapshotAt, '2026-11-03T10:00:00Z'); assert.deepEqual(a.dailyStats.map(row => row.minutes), [60, 0, null])
})
test('authorized shared effect contract requires explicit student and legal window, never calls me', async () => {
  const calls = []; const api = createLearningReadApi({ learningEffectSummary: (...args) => { calls.push(args); return {} } })
  for (const id of [undefined, null, '']) assert.throws(() => api.effectForStudent(id, 7), /Student/)
  assert.throws(() => api.effectForStudent(1, 14), /window/)
  await api.effectForStudent(1, 30); assert.deepEqual(calls, [[1, 30]])
})
test('all seven original growth sections are retained in teacher view', () => {
  assert.deepEqual(GROWTH_SECTIONS.map(item => item.key), ['overview', 'activity', 'mastery', 'recommendations', 'reviews', 'results', 'report'])
})
test('eight effect indices use missing versus zero, with no invented excellent or risk judgement', () => {
  const rows = metricRows({ snapshot: { dimensions: { time_score: 0, completion_score: null, mastery_score: 42, retention_score: '' } } })
  assert.equal(rows.length, 8); assert.equal(rows[0].value, 0); assert.equal(rows[1].value, null); assert.equal(rows[2].value, 42); assert.equal(rows[3].value, null)
  assert.match(rows[0].label, /指数/)
})
test('student filters and date/mastery sort preserve true zero and do not mutate the roster', () => {
  const rows = [{ username: '甲', mastery: 0, self_assessed_at: '2026-11-03' }, { username: '乙', mastery: 90, self_assessed_at: '2026-11-01' }]
  assert.equal(filterStudents(rows, '', 'mastery')[0].username, '乙'); assert.equal(filterStudents(rows, '  甲 ', '')[0].username, '甲'); assert.equal(rows[0].username, '甲')
})
test('individual insight requests always name the selected authorized student, not the logged-in teacher', async () => {
  const calls = []; const { model, state } = await setup({ effect: async (id, days) => { calls.push([id, days]); return payload(id, days) } })
  await model.selectStudent(2); await model.loadEffect(90)
  assert.deepEqual(calls, [[2, 7], [2, 90]]); assert.equal(state.studentId, 2)
  await model.selectStudent(999); assert.equal(calls.length, 2); assert.equal(state.effect, null)
})
test('wrong student or wrong window response cannot masquerade as a growth report', async () => {
  const { model, state, api } = await setup({ effect: async () => payload(2, 7) })
  await model.selectStudent(1); assert.equal(state.effect, null); assert.match(state.effectError, /未能读取/)
  api.effect = async id => payload(id, 30); await model.loadEffect(7); assert.equal(state.effect, null)
})
test('out-of-order windows and students discard old successes and errors', async () => {
  const pending = []; const { model, state, api } = await setup()
  api.effect = (id, days) => { const request = defer(); pending.push({ id, days, ...request }); return request.promise }
  const first = model.selectStudent(1), second = model.loadEffect(30)
  pending[0].resolve(payload(1, 7)); await first; assert.equal(state.effectLoading, true); assert.equal(state.effect, null)
  pending[1].resolve(payload(1, 30)); await second; assert.equal(state.effect.days, 30)
  const third = model.loadEffect(90), fourth = model.selectStudent(2)
  pending[2].reject(Error('old failure')); await third; assert.equal(state.effectError, '')
  pending[3].resolve(payload(2, 90)); await fourth; assert.equal(state.studentId, 2); assert.equal(state.effect.days, 90)
})
test('empty snapshot is a readable missing partition, not a fake zero report', async () => {
  const { model, state } = await setup(); await model.selectStudent(1)
  assert.equal(state.effect.hasSnapshot, false); assert.equal(state.effect.hasDaily, false); assert.deepEqual(state.effect.recommendations, [])
  assert.ok(metricRows(state.rawEffect).every(row => row.value === null))
})
test('account changes immediately clear teacher and student-specific data and guard late responses', async () => {
  const { model, state, api } = await setup(); const late = defer(); api.effect = () => late.promise
  const reading = model.selectStudent(1); model.setAccount('teacher:9')
  assert.deepEqual(state.students, []); assert.equal(state.plan, null); assert.equal(state.studentId, '')
  late.resolve(payload(1, 7)); await reading; assert.equal(state.effect, null); assert.equal(state.effectError, '')
})
test('roster and per-section failures allow retry without fabricated replacements', async () => {
  const { model, state, api } = await setup(); api.students = async () => { throw Error() }
  await model.loadStudents(); assert.deepEqual(state.students, []); assert.match(state.rosterError, /重试/)
  api.students = async () => [{ id: 1 }]; await model.loadStudents(); assert.equal(state.rosterError, '')
  api.plan = async () => { throw Error() }; await model.selectStudent(1); assert.equal(state.effect.days, 7); assert.match(state.planError, /重试/)
  api.plan = async student => ({ student }); await model.loadPlan(); assert.equal(state.planError, '')
})
test('shared seconds preserve missing authoritative data and reject containers or negative values', () => {
  const raw = payload(1, 7, { snapshot: {}, daily_stats: [{ date: '2026-11-03', effective_learning_seconds: null, study_seconds: 3600 }, { date: '2026-11-02', effective_learning_seconds: -30 }, { date: '2026-11-01', effective_learning_seconds: [] }] })
  const result = shared.normalizeEffect(raw, 7)
  assert.equal(result.hasSnapshot, false)
  assert.deepEqual(result.dailyStats.map(row => [row.minutes, row.rawSeconds]), [[null, null], [null, null], [null, null]])
  assert.deepEqual(result, student.normalizeEffect(raw, 7))
})
test('default report zeros without concept evidence remain missing, real zero concept mastery is retained', () => {
  assert.equal(reportMastery({ mastery: 0, concepts: [] }), null)
  assert.equal(reportMastery({ mastery: 0, concepts: [{ name: '真实记录', mastery: 0 }] }), 0)
})
test('explicit teacher read contract rejects malformed or container student IDs', () => {
  let calls = 0; const api = createLearningReadApi({ learningEffectSummary: () => calls++ })
  for (const id of [0, -1, 1.5, true, [], [1], {}, 'me', '1?days=7', '9007199254740993']) assert.throws(() => api.effectForStudent(id, 7), /Student/)
  assert.equal(calls, 0)
})
test('insights role and roster guards reject non-teachers and non-student options', async () => {
  let calls = 0; const model = createInsightsState({ api: { students: async () => { calls++; return [] } } })
  model.setAccount('student:1'); await model.loadStudents(); assert.equal(calls, 0)
  const { model: next, state } = await setup({ students: async () => [{ id: 1, role: 'student' }, { id: 2, role: 'teacher' }, { id: true }] })
  assert.equal(state.students.length, 1); await next.selectStudent(2); assert.equal(state.studentId, '')
})
