import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { splitCodepoints } from './codepoints.js'
import { readableError } from './errors.js'
import { currentReplays, latestRevealedReplays } from './replaySelection.js'

const splitCases = [
  ['ASCII half-open span', 'abcde', { start: 1, end: 3 }, { before: 'a', selected: 'bc', after: 'de' }],
  ['Chinese codepoints', '甲乙丙', { start: 1, end: 2 }, { before: '甲', selected: '乙', after: '丙' }],
  ['astral character is one codepoint', '甲\u{1F9EA}乙', { start: 1, end: 2 }, { before: '甲', selected: '\u{1F9EA}', after: '乙' }],
  ['offset after astral character', '\u{1F9EA}甲乙', { start: 1, end: 3 }, { before: '\u{1F9EA}', selected: '甲乙', after: '' }],
  ['combining mark is a separate codepoint', 'éx', { start: 1, end: 2 }, { before: 'e', selected: '́', after: 'x' }],
  ['ZWJ sequence is not a single codepoint', '\u{1F469}‍\u{1F4BB}', { start: 1, end: 2 }, { before: '\u{1F469}', selected: '‍', after: '\u{1F4BB}' }],
  ['whitespace and newlines are preserved', ' \n甲 ', { start: 0, end: 4 }, { before: '', selected: ' \n甲 ', after: '' }],
]
for (const [name, text, span, expected] of splitCases) {
  test(`splitCodepoints: ${name}`, () => {
    assert.deepEqual(splitCodepoints(text, span), expected)
    assert.equal(Object.values(splitCodepoints(text, span)).join(''), text)
  })
}
test('splitCodepoints: invalid spans never truncate or highlight text', () => {
  for (const span of [undefined, null, {}, { start: -1, end: 1 }, { start: 1, end: 1 },
    { start: 2, end: 1 }, { start: 0, end: 4 }, { start: 0.5, end: 2 },
    { start: '0', end: 1 }, { start: 0, end: Infinity }, { start: NaN, end: 1 }]) {
    assert.deepEqual(splitCodepoints('甲\u{1F9EA}乙', span), { before: '甲\u{1F9EA}乙', selected: '', after: '' })
  }
})
test('splitCodepoints: empty and null text are safe', () => {
  for (const text of ['', null, undefined]) {
    assert.deepEqual(splitCodepoints(text, { start: 0, end: 1 }), { before: '', selected: '', after: '' })
  }
})
test('splitCodepoints: inputs are not mutated', () => {
  const span = Object.freeze({ start: 0, end: 1 })
  assert.equal(splitCodepoints('甲乙', span).selected, '甲')
  assert.deepEqual(span, { start: 0, end: 1 })
})

const scan = Object.freeze({ scan_id: 'current-scan', profile_id: 'current-profile' })
const round = (variant, id, extra = {}) => Object.freeze({
  replay_id: id, scenario_variant: variant, ...scan, revealed: true, ...extra,
})
test('replay selection: excludes other scans, older profiles, hidden rounds and unknown variants', () => {
  const replays = Object.freeze([
    round('A1', 'a1'), round('A2', 'a2'), round('A3', 'a3'), round('A4', 'a4'),
    round('A1', 'old-scan', { scan_id: 'old-scan' }),
    round('A2', 'old-profile', { profile_id: 'old-profile' }),
    round('A3', 'not-revealed', { revealed: false }),
    round('other', 'unexpected'),
  ])
  assert.deepEqual(latestRevealedReplays(replays, scan).map(r => r.replay_id), ['a1', 'a2', 'a3', 'a4'])
})
test('replay selection: latest revealed per variant, not last four rows', () => {
  const replays = [round('A4', 'a4'), round('A2', 'a2'), round('A3', 'a3'),
    round('A1', 'a1-old'), round('A1', 'a1-new'), round('A1', 'a1-hidden', { revealed: false })]
  assert.deepEqual(latestRevealedReplays(replays, scan).map(r => r.replay_id), ['a1-new', 'a2', 'a3', 'a4'])
})
test('replay selection: timestamps determine latest even if response order differs', () => {
  const replays = [round('A1', 'new', { created_at: '2026-10-29T12:01:00Z' }),
    round('A1', 'old', { created_at: '2026-10-29T12:00:00Z' })]
  assert.equal(latestRevealedReplays(replays, scan)[0].replay_id, 'new')
})
test('replay selection: missing variants are not filled by duplicates or obsolete rows', () => {
  const selected = latestRevealedReplays([
    round('A1', 'first'), round('A1', 'second'), round('A1', 'third'), round('A4', 'old', { profile_id: 'old' }),
  ], scan)
  assert.deepEqual(selected.map(r => r.scenario_variant), ['A1'])
})
test('replay selection: absent scan, profile or association is not eligible', () => {
  assert.deepEqual(latestRevealedReplays([round('A1', 'a1')], null), [])
  assert.deepEqual(latestRevealedReplays([round('A1', 'a1')], { scan_id: 'current-scan' }), [])
  assert.deepEqual(latestRevealedReplays([round('A1', 'a1', { scan_id: undefined })], scan), [])
  assert.deepEqual(latestRevealedReplays(undefined, scan), [])
})
test('current replay list keeps unrevealed current rounds but not obsolete rounds', () => {
  const replays = [round('A1', 'current', { revealed: false }), round('A2', 'old', { profile_id: 'old' })]
  assert.deepEqual(currentReplays(replays, scan).map(r => r.replay_id), ['current'])
})

test('readable errors: local validation preserves the actual message', () => {
  assert.equal(readableError(new Error('请选择原文中的逻辑单元格')), '请选择原文中的逻辑单元格')
})
test('readable errors: DRF strings, lists and field validation are readable', () => {
  assert.equal(readableError({ response: { data: { detail: '请先保存依据' } } }), '请先保存依据')
  assert.equal(readableError({ response: { data: ['第一项', '第二项'] } }), '第一项；第二项')
  assert.equal(readableError({ response: { data: { reason: ['请填写理由'], non_field_errors: ['请重试'] } } }), 'reason：请填写理由；请重试')
})
test('readable errors: network and service fallback never show HTML', () => {
  assert.match(readableError({ code: 'ERR_NETWORK', message: 'Network Error' }), /连接中断/)
  assert.match(readableError({ code: 'ECONNABORTED' }), /请求超时/)
  assert.match(readableError({ response: { status: 503, data: '<html>proxy error</html>' } }), /服务暂不可用/)
  assert.match(readableError({ response: { status: 403 } }), /没有此操作权限/)
  assert.equal(readableError(undefined, '读取失败'), '读取失败')
})

// Exercise the existing guard with stubbed imports, without a browser or mounting UI.
function routerFor(user) {
  const source = readFileSync(new URL('../../router/index.js', import.meta.url), 'utf8')
  return runInNewContext(source.trimStart().replace(/^import .*$/gm, '').replace('export default router', 'router'), {
    createRouter: options => ({ ...options, beforeEach(guard) { this.guard = guard } }),
    createWebHistory: () => ({}), useUserStore: () => user, document: {},
    TeacherLayout: {}, TeacherDashboard: {}, LearningEffectAnalysis: {},
  })
}
test('module routes: student is authenticated and teacher is an independent teacher/admin route', () => {
  const router = routerFor({})
  const student = router.routes.find(route => route.path === '/data-lab')
  const teacher = router.routes.find(route => route.path === '/data-lab/teacher')
  assert.ok(student.meta.requiresAuth)
  assert.ok(teacher.meta.requiresAuth)
  assert.ok(teacher.meta.requiresTeacher)
  assert.equal(teacher.meta.requiresTeacherOnly, undefined)
})
for (const [role, authenticated, expected] of [
  ['guest', false, '/login'], ['student', true, '/'], ['teacher', true, undefined], ['admin', true, undefined],
]) {
  test(`module teacher guard: ${role}`, () => {
    const router = routerFor({ isAuthenticated: authenticated, userInfo: { role } })
    const route = router.routes.find(route => route.path === '/data-lab/teacher')
    const decisions = []
    router.guard(route, {}, value => decisions.push(value))
    assert.deepEqual(decisions, [expected])
  })
}
test('module student guard: guests must log in', () => {
  const router = routerFor({ isAuthenticated: false })
  const route = router.routes.find(route => route.path === '/data-lab')
  const decisions = []
  router.guard(route, {}, value => decisions.push(value))
  assert.deepEqual(decisions, ['/login'])
})
