import test from 'node:test'
import assert from 'node:assert/strict'
import { createWorkspaceSession } from './workspaceSession.js'
import { submissionScopeNote } from './workspaceView.js'

// 工作台会话：题目读取、相关题目、提交记录与环境轮询都只反映服务端真实状态。
function make(apiClient, options = {}) {
  const scheduled = []
  const cancelled = []
  const session = createWorkspaceSession({
    apiClient, challengeId: 41, userId: 7,
    schedule: (fn, ms) => { scheduled.push({ fn, ms }); return scheduled.length },
    cancel: timer => cancelled.push(timer),
    ...options,
  })
  return { session, scheduled, cancelled }
}

test('a late detail response cannot replace a newer challenge', async () => {
  const pending = []
  const { session } = make({
    detail: () => new Promise(resolve => pending.push(resolve)),
    list: async () => ({ results: [], count: 0 }),
  })
  const first = session.load()
  const second = session.load()
  pending[1]({ id: 41, title: '新题目' })
  await second
  pending[0]({ id: 41, title: '旧题目' })
  await first
  assert.equal(session.challenge.value.title, '新题目')
  assert.equal(session.loading.value, false)
})

test('destroyed sessions ignore late responses and cancel timers', async () => {
  let resolveDetail
  const { session, scheduled, cancelled } = make({ detail: () => new Promise(resolve => { resolveDetail = resolve }) })
  const loading = session.load()
  session.destroy()
  resolveDetail({ id: 41, title: '迟到题目' })
  await loading
  assert.equal(session.challenge.value, null)
  assert.deepEqual(cancelled, [])
  assert.deepEqual(scheduled, [])
})

test('related practice only lists real same-category items and excludes the current challenge', async () => {
  const listCalls = []
  const { session } = make({
    detail: async () => ({ id: 41, title: '当前题', category: 8 }),
    list: async params => {
      listCalls.push(params)
      return { results: [
        { id: 41, title: '当前题', difficulty: 'easy' },
        { id: 42, title: '同分类一', difficulty: 'hard' },
        { id: 43, title: '已停用', is_active: false },
        { id: 44, title: '同分类二', difficulty: 'medium' },
        { id: 45, title: '同分类三' }, { id: 46, title: '同分类四' }, { id: 47, title: '同分类五' }, { id: 48, title: '同分类六' },
      ] }
    },
  })
  await session.load()
  assert.deepEqual(listCalls, [{ category: 8, page_size: 6 }])
  const ids = session.related.value.sameCategory.map(item => item.id)
  assert.deepEqual(ids, [42, 44, 45, 46, 47])
})

test('submission history is scoped to this challenge and merges pages without duplicates', async () => {
  const pages = []
  const { session } = make({
    mySubmissions: async ({ page }) => {
      pages.push(page)
      if (page === 1) {
        return { results: [
          { id: 1, challenge_id: 41, is_correct: true, created_at: '2026-11-03T03:00:00Z' },
          { id: 2, challenge_id: 99, is_correct: false, created_at: '2026-11-03T02:00:00Z' },
        ], count: 3, next: 'http://x?page=2' }
      }
      return { results: [
        { id: 1, challenge_id: 41, is_correct: true, created_at: '2026-11-03T03:00:00Z' },
        { id: 3, challenge_id: 41, is_correct: false, created_at: '2026-11-03T01:00:00Z' },
      ], count: 3, next: null }
    },
  })
  await session.loadSubmissions()
  assert.deepEqual(session.submissions.value.items.map(item => item.id), [1])
  assert.equal(session.submissions.value.hasNext, true)
  assert.equal(session.submissions.value.loaded, 1)

  await session.loadSubmissions({ more: true })
  assert.deepEqual(pages, [1, 2])
  assert.deepEqual(session.submissions.value.items.map(item => item.id), [1, 3])
  assert.equal(session.submissions.value.hasNext, false)
  assert.equal(session.submissions.value.loaded, 2)
})

test('submission history pages past a first page that has no records for this challenge', async () => {
  const pages = []
  const { session } = make({
    mySubmissions: async ({ page }) => {
      pages.push(page)
      if (page === 1) {
        return {
          count: 33, next: 'http://x?page=2',
          results: Array.from({ length: 20 }, (_, i) => ({ id: 10 + i, challenge_id: 15 })),
        }
      }
      if (page === 2) {
        return {
          count: 33, next: 'http://x?page=3',
          results: [
            ...Array.from({ length: 12 }, (_, i) => ({ id: 40 + i, challenge_id: 15 })),
            { id: 1, challenge_id: 41, is_correct: true, created_at: '2026-11-03T09:23:32Z' },
          ],
        }
      }
      return { count: 33, next: null, results: [{ id: 2, challenge_id: 41, is_correct: false, created_at: '2026-11-02T00:00:00Z' }] }
    },
  })

  await session.loadSubmissions()
  // 本题唯一记录在第二页：不能只看第一页就说“没有提交”。
  assert.deepEqual(pages, [1, 2])
  assert.deepEqual(session.submissions.value.items.map(item => item.id), [1])
  assert.equal(session.submissions.value.hasNext, true)
  assert.equal(session.submissions.value.page, 2)
  assert.equal(session.submissions.value.pagesRead, 2)
  assert.equal(session.submissions.value.loaded, 1)

  await session.loadSubmissions({ more: true })
  assert.deepEqual(pages, [1, 2, 3])
  assert.deepEqual(session.submissions.value.items.map(item => item.id), [1, 2])
  assert.equal(session.submissions.value.hasNext, false)
})

test('submission scan stops at the page cap and keeps the unread range explicit', async () => {
  const pages = []
  const { session } = make({
    mySubmissions: async ({ page }) => {
      pages.push(page)
      return {
        count: 80, next: `http://x?page=${page + 1}`,
        results: Array.from({ length: 20 }, (_, i) => ({ id: page * 100 + i, challenge_id: 15 })),
      }
    },
  }, { maxSubmissionPages: 2 })

  await session.loadSubmissions()
  assert.deepEqual(pages, [1, 2])
  assert.deepEqual(session.submissions.value.items, [])
  assert.equal(session.submissions.value.hasNext, true)
  assert.equal(session.submissions.value.pagesRead, 2)
  assert.equal(submissionScopeNote(session.submissions.value), '已读取最近 2 页，暂未找到本题提交；仍有更早记录未加载。')
})

test('polling stops with an honest timeout instead of pretending the environment is ready', async () => {
  const { session, scheduled } = make({
    startEnvironment: async () => ({ success: true, container: { status: 'pending' } }),
    container: async () => ({ status: 'pending' }),
  }, { maxPolls: 2, pollInterval: 10 })
  await session.startEnvironment()
  assert.equal(scheduled.length, 1)
  await scheduled.shift().fn()
  assert.equal(session.environment.value.phase, 'waiting')
  assert.equal(scheduled.length, 1)
  await scheduled.shift().fn()
  assert.equal(session.environment.value.phase, 'timeout')
  assert.equal(session.environment.value.error, '环境状态读取超时，可重试读取或联系教师。')
  assert.equal(scheduled.length, 0)
})

test('guests cannot start an environment and no local fake state is created', async () => {
  let started = 0
  const { session } = make({ startEnvironment: async () => { started += 1; return { success: true } } }, { userId: null })
  const result = await session.startEnvironment()
  assert.equal(result.ok, false)
  assert.equal(started, 0)
  assert.equal(session.environment.value.error, '请先登录后再启动环境。')
  assert.equal(session.environment.value.info, null)

  const refreshed = await session.refreshEnvironment()
  assert.equal(refreshed.info, null)
  assert.equal(refreshed.phase, 'idle')
})

test('failed environment reading keeps the error visible and never claims readiness', async () => {
  const { session } = make({ container: async () => { const error = Error('x'); error.response = { status: 503 }; throw error } })
  await session.refreshEnvironment()
  assert.equal(session.environment.value.phase, 'error')
  assert.equal(session.environment.value.error, '练习环境状态暂时不可读取，请稍后重试。')
  assert.equal(session.environmentStatus.value.accessUrl, '')
  assert.equal(session.countdownText.value, '未提供')
})
