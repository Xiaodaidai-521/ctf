import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import { asList, finiteNumber, pageInfo, ratioPercent } from './contracts.js'
import { createHubState } from './practice/hubStore.js'
import { createWorkspace } from './practice/workspaceStore.js'
import { countdown, normalizeEnvironment, phaseFor } from './practice/environment.js'
import { submissionsForChallenge } from './practice/submissions.js'
import { sanitizeContext, contextLabel } from './agent/context.js'

// 纯模块若用 @/api 别名则无法在 node --test 直接解析，这里剥掉 import 后取导出函数。
function loadPure(url, names, sandbox = {}) {
  const source = readFileSync(url, 'utf8')
    .replace(/^import .*$/gm, '')
    .replace(/^export \{.*\}$/gm, '')
    .replace(/^export /gm, '')
  return vm.runInNewContext(`${source}\n;({${names.join(',')}})`, sandbox)
}
const here = name => new URL(name, import.meta.url)

const exams = loadPure(here('./exams/api.js'), ['levelInfo', 'recordView', 'resultView'], { asList, finiteNumber })
const paths = loadPure(here('./paths/api.js'), ['membership', 'moduleTarget', 'progressSummary'], { asList, finiteNumber })
const capability = loadPure(here('./capability/api.js'), ['capabilityState', 'evidenceSummary', 'claimDestination'], { asList, finiteNumber })
const growth = loadPure(here('./growth/api.js'), ['completionFrom', 'growthWindow', 'weeklyReport'], { asList, ratioPercent })
const agentApi = loadPure(here('./agent/api.js'), ['conversationMessages', 'restorableConversation'], {})
const growthStoreModule = loadPure(here('./growth/store.js'), ['createGrowthState'], {
  asList, finiteNumber, completionFrom: growth.completionFrom, growthWindow: growth.growthWindow,
  weeklyReport: growth.weeklyReport, growthApi: {},
})

const plain = value => JSON.parse(JSON.stringify(value))

test('pagination keeps the read range instead of presenting the first page as everything', () => {
  const page = pageInfo({ count: 37, next: 'http://x?page=2', results: Array.from({ length: 20 }, (_, i) => ({ id: i })) })
  assert.equal(page.count, 37)
  assert.equal(page.loaded, 20)
  assert.equal(page.hasNext, true)
  const complete = pageInfo({ count: 2, next: null, results: [{ id: 1 }, { id: 2 }] })
  assert.equal(complete.hasNext, false)
  assert.deepEqual(asList(null), [])
  assert.deepEqual(asList({ detail: 'not a list' }), [])
})

test('completion rates convert per source and never turn missing into zero', () => {
  assert.equal(ratioPercent(0.426, 'progress-report'), 42.6)
  assert.equal(ratioPercent(42.6, 'submission-stats'), 42.6)
  assert.equal(ratioPercent(0, 'progress-report'), 0)
  assert.equal(ratioPercent(null, 'progress-report'), null)
  assert.equal(ratioPercent('', 'submission-stats'), null)
  assert.equal(ratioPercent(-1, 'submission-stats'), null)
  assert.equal(ratioPercent(140, 'submission-stats'), 100)
  const fromBoth = growth.completionFrom({ completion_rate: 0.5 }, { completion_rate: 50 })
  assert.deepEqual(plain(fromBoth), { report: 50, submissions: 50 })
})

test('hub applies only the newest filter result, including on repeated clicks', async () => {
  const pending = []
  const hub = createHubState({ apiClient: {
    list: query => new Promise(resolve => pending.push({ category: query.category, resolve })),
    categories: async () => [], solved: async () => [], stats: async () => ({}),
  } })
  const first = hub.loadList({ category: 1 })
  const second = hub.loadList({ category: 2 })
  pending[1].resolve([{ id: 22, title: 'B' }])
  await second
  pending[0].resolve([{ id: 11, title: 'A' }])
  await first
  assert.deepEqual(hub.state.challenges.map(item => item.id), [22])
  assert.equal(hub.state.loading.list, false)

  const third = hub.loadList({ category: 2 })
  const fourth = hub.loadList({ category: 2 })
  pending[2].resolve([{ id: 33, title: 'A' }])
  pending[3].resolve([{ id: 44, title: 'C' }])
  await Promise.all([third, fourth])
  assert.deepEqual(hub.state.challenges.map(item => item.id), [44])
})

test('hub reports failure as failure and scopes solved counts to loaded items', async () => {
  const hub = createHubState({ apiClient: {
    list: async () => { throw new Error('offline') }, categories: async () => [], solved: async () => [], stats: async () => ({}),
  } })
  await hub.loadList({})
  assert.equal(hub.state.challenges.length, 0)
  assert.match(hub.state.errors.list, /未能加载/)
  const feed = createHubState({ apiClient: {
    list: async () => ({ count: 30, next: 'x', results: [{ id: 1, is_solved: true }, { id: 2, is_solved: false }] }),
    categories: async () => [], solved: async () => [], stats: async () => ({}),
  } })
  await feed.loadList({})
  assert.deepEqual(feed.solvedInFilter(), { solved: 1, scope: 'loaded' })
  feed.state.totalCount = 2
  assert.deepEqual(feed.solvedInFilter(), { solved: 1, scope: 'filter' })
})

test('hub keeps last visit as a minimal reference and reports it unavailable when gone', async () => {
  const memory = new Map()
  const storage = { getItem: key => memory.get(key) ?? null, setItem: (key, value) => memory.set(key, value) }
  const hub = createHubState({ apiClient: {
    list: async () => [{ id: 5, title: '当前题目' }], categories: async () => [], solved: async () => [], stats: async () => ({}),
  }, storage, now: () => 1000 })
  hub.rememberVisit({ id: 5, title: '上次题目', flag: 'flag{never}' })
  assert.deepEqual(JSON.parse(memory.get('ctf:practice:last-visit')), { id: 5, title: '上次题目', at: 1000 })
  await hub.loadList({})
  assert.equal(hub.resumeCandidate().available, true)
  hub.state.challenges = []
  assert.deepEqual(plain(hub.resumeCandidate()), { id: 5, title: '上次题目', at: 1000, available: false })
})

test('challenge submissions are scoped to the challenge and keep the page range', () => {
  const value = {
    count: 21, next: 'next',
    results: [
      { id: 1, challenge_id: 9, status: 'correct' },
      { id: 2, challenge: { id: 9 }, status: 'incorrect' },
      { id: 3, challenge_id: 10, status: 'correct' },
    ],
  }
  const scoped = submissionsForChallenge(value, 9)
  assert.deepEqual(scoped.items.map(item => item.id), [1, 2])
  assert.equal(scoped.scoped, true)
  assert.equal(scoped.count, 21)
  assert.equal(submissionsForChallenge({ results: [] }, 9).scoped, false)
})

test('workspace submission loading pages through to the challenge record instead of stopping at page one', async () => {
  const pages = []
  const workspace = createWorkspace({ challengeId: 9, apiClient: {
    mySubmissions: async ({ page } = {}) => {
      pages.push(page)
      if (page === 1) return { count: 25, next: 'http://x?page=2', results: [{ id: 1, challenge_id: 10 }] }
      return { count: 25, next: null, results: [{ id: 2, challenge_id: 9 }] }
    },
  } })
  await workspace.loadSubmissions()
  assert.deepEqual(pages, [1, 2])
  assert.deepEqual(workspace.state.submissions.items.map(item => item.id), [2])
  assert.equal(workspace.state.submissions.hasNext, false)
  assert.equal(workspace.state.submissions.pagesRead, 2)
})

test('workspace guard blocks a duplicate submit and reports 503 without pretending success', async () => {
  let calls = 0
  let resolveSubmit
  const workspace = createWorkspace({ challengeId: 9, apiClient: {
    submit: () => { calls++; return new Promise(resolve => { resolveSubmit = resolve }) },
    detail: async () => ({ id: 9, title: '题目' }), mySubmissions: async () => ({ results: [] }),
  } })
  workspace.state.flag = 'flag{test}'
  const first = workspace.submit()
  const second = await workspace.submit()
  assert.deepEqual(second, { ok: false, busy: true, message: '正在提交，请稍候。' })
  assert.equal(calls, 1)
  resolveSubmit({ success: false, message: 'Flag 不正确' })
  assert.equal((await first).ok, false)
  assert.equal(workspace.state.submitType, 'error')

  const unavailable = createWorkspace({ challengeId: 9, apiClient: {
    submit: async () => { const error = new Error('down'); error.response = { status: 503 }; throw error },
    detail: async () => ({}), mySubmissions: async () => ({ results: [] }),
  } })
  unavailable.state.flag = 'flag{test}'
  await unavailable.submit()
  assert.match(unavailable.state.submitMessage, /提交服务暂时不可用/)
  assert.equal(unavailable.state.submitType, 'error')
})

test('environment shows real states only: no fake progress, no timeout-as-ready', () => {
  assert.equal(phaseFor(null), 'idle')
  assert.equal(phaseFor({ status: 'running', is_running: true }), 'waiting')
  assert.equal(phaseFor({ status: 'running', is_running: true, access_url: 'http://env' }), 'ready')
  assert.equal(phaseFor({ status: 'running', is_running: true, expires_at: '2020-01-01T00:00:00Z', is_expired: true }), 'expired')
  assert.equal(phaseFor({ status: 'error' }), 'error')
  assert.equal(normalizeEnvironment(null).label, '未启动')
  assert.deepEqual(countdown(null, 0), { text: '未提供', seconds: null })
  assert.deepEqual(countdown('2026-11-03T00:01:05Z', Date.parse('2026-11-03T00:00:00Z')), { text: '01:05', seconds: 65 })
  assert.deepEqual(countdown('2026-11-02T23:59:00Z', Date.parse('2026-11-03T00:00:00Z')), { text: '已到期', seconds: 0 })
  const workspace = createWorkspace({ challengeId: 9, now: () => 0, apiClient: {} })
  assert.equal(workspace.countdownSeconds(), null)
})

test('exam records label real statuses, keep missing scores missing and normalize result fields', () => {
  assert.equal(exams.recordView({ status: 'pending' }).statusLabel, '未开始')
  assert.equal(exams.recordView({ status: 'timeout' }).statusLabel, '已超时')
  assert.equal(exams.recordView({ status: 'completed', total_score: 0 }).score, 0)
  assert.equal(exams.recordView({ status: 'completed' }).score, null)
  const rules = [{ level: 'A', minScore: 0 }, { level: 'B', minScore: 60 }, { level: 'C', minScore: 85 }]
  assert.equal(exams.levelInfo(rules, 70).current.level, 'B')
  assert.equal(exams.levelInfo(rules, 70).next.level, 'C')
  assert.equal(exams.levelInfo(rules, 70).remaining, 15)
  const result = exams.resultView({
    theory_exam: { pass_score: 60 }, practice_exam: 12,
    questions: [{ theory_question: 3, question_text: '题干', user_answer: 'A', correct_answer: 'B', score: 4, max_score: 10 }],
  })
  assert.equal(result.passScore, 60)
  assert.equal(result.questions[0].questionRef, 3)
  assert.equal(result.questions[0].maxScore, 10)
  assert.equal(exams.resultView({ theory_exam: 4, practice_exam: { pass_score: 50 } }).passScore, 50)
})

test('path progress does not invent percent or hours and membership stays honest', () => {
  assert.deepEqual(plain(paths.progressSummary(null)), { percent: null, anomaly: false, rawPercent: null, completed: null, total: null, hourLabel: '—' })
  assert.deepEqual(plain(paths.progressSummary({ completed_modules: 2, total_modules: 4 })), { percent: 50, anomaly: false, rawPercent: 50, completed: 2, total: 4, hourLabel: '—' })
  assert.equal(paths.progressSummary({ completion_rate: 0.4 }).percent, 40)
  assert.equal(paths.progressSummary({ completion_rate: 140 }).percent, 100)
  assert.equal(paths.progressSummary({ completion_rate: 140 }).anomaly, true)
  assert.equal(paths.progressSummary({ completion_rate: 140 }).rawPercent, 140)
  assert.equal(paths.membership([{ learning_path: 3 }], 3).joined, true)
  assert.equal(paths.membership([], 3).joined, false)
  assert.equal(paths.moduleTarget({ learning_path: 3, current_module: 8 }), '/learning-paths/3/modules/8')
  assert.equal(paths.moduleTarget({ learning_path: 3 }), '/learning-paths/3')
  assert.equal(paths.moduleTarget(null), '/learning-paths')
})

test('capability state is unknown rather than zero mastery, and claims only use real attempts', () => {
  assert.deepEqual(plain(capability.capabilityState({})), { key: 'unknown', label: '掌握情况未知' })
  assert.equal(capability.capabilityState({ state: 'mastered' }).label, '已掌握')
  assert.equal(capability.capabilityState({ state: 'weird' }).key, 'unknown')
  assert.deepEqual(capability.claimDestination({ attempt_id: 12 }).path, '/learning-knowledge/12')
  assert.equal(capability.claimDestination({}).available, false)
  assert.match(capability.claimDestination({}).reason, /暂未提供/)
  assert.deepEqual(plain(capability.evidenceSummary(null)), { result: '暂无证据', task: null, time: null, assisted: null, retestAt: null })
})

test('weekly report keeps real fields, missing values null, and labels non-current weeks as the latest issue', () => {
  const current = growth.weeklyReport({ week_start: '2026-10-31T00:00:00Z', total_study_minutes: 120 }, new Date('2026-11-03T00:00:00Z'))
  assert.equal(current.label, '本周周报')
  assert.equal(current.minutes, 120)
  assert.equal(current.modules, null)
  const old = growth.weeklyReport({ week_start: '2026-10-01T00:00:00Z' }, new Date('2026-11-03T00:00:00Z'))
  assert.equal(old.label, '最近一期周报')
  assert.equal(old.minutes, null)
  assert.equal(growth.weeklyReport(null), null)
  assert.equal(growth.growthWindow(30), 30)
  assert.equal(growth.growthWindow(15), 7)
})

test('growth store isolates sections, account switches and late responses', async () => {
  let releaseProfile
  const store = growthStoreModule.createGrowthState({
    userId: 1,
    now: () => 1000,
    apiClient: {
      profile: () => new Promise(resolve => { releaseProfile = resolve }),
      persona: async () => ({ tags: ['x'] }),
      progressReport: async () => { throw new Error('down') },
      insights: async () => ({}), weeklySummary: async () => null, teachingPlan: async () => null,
      recommendations: async () => [], reviewReminders: async () => [], myPaths: async () => [], submissionStats: async () => ({}),
      learningEffect: async () => ({ days: 30 }),
    },
  })
  const loading = store.loadCore()
  await new Promise(resolve => setTimeout(resolve, 0))
  assert.match(store.state.errors.report, /暂时未能读取/)
  assert.deepEqual(store.state.persona, { tags: ['x'] })
  assert.equal(store.state.loading, true)
  assert.equal(store.setAccount(2), true)
  assert.equal(store.state.persona, null)
  assert.equal(store.state.loading, false)
  releaseProfile({ name: '老账号' })
  await loading
  assert.equal(store.state.profile, null)
  await store.loadEffect(30)
  assert.equal(store.state.window, 30)
  assert.deepEqual(store.state.effect, { days: 30 })
})

test('agent context carries only authorized references, never flags or answers', () => {
  const context = sanitizeContext({
    kind: 'challenge', id: 9, title: '题目', flag: 'flag{secret}', answer: 'x',
    submissions: [{ flag: 'flag{secret}' }], otherUser: 'x',
  })
  assert.deepEqual(plain(context), { kind: 'challenge', ref: '9', title: '题目', reason: '' })
  assert.equal(sanitizeContext({ kind: 'exam', ref: 1 }), null)
  assert.equal(sanitizeContext({ kind: 'challenge', ref: '' }), null)
  assert.equal(sanitizeContext(null), null)
  assert.equal(contextLabel(context), '当前题目：题目')
})

test('conversation restore skips empty conversations and keeps real messages only', () => {
  assert.deepEqual(plain(agentApi.conversationMessages({ messages: [
    { id: 1, role: 'user', content: '问题' }, { id: 2, role: 'assistant', content: '讲解', agent_name: '教学辅导师' },
  ] })).map(item => [item.role, item.content, item.agentName]), [['user', '问题', ''], ['assistant', '讲解', '教学辅导师']])
  assert.deepEqual(plain(agentApi.conversationMessages(null)), [])
  const latest = agentApi.restorableConversation([
    { id: 1, message_count: 0, updated_at: '2026-11-03T00:00:00Z' },
    { id: 2, message_count: 3, updated_at: '2026-11-01T00:00:00Z' },
    { id: 3, message_count: 5, updated_at: '2026-11-02T00:00:00Z' },
  ])
  assert.equal(latest.id, 3)
  assert.equal(agentApi.restorableConversation([]), null)
})
