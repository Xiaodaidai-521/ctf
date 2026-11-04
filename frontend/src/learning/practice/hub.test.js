import test from 'node:test'
import assert from 'node:assert/strict'
import { createHubState } from './hubStore.js'
import { FILTER_KEY, VISIT_KEY, readPreferences } from './preferences.js'

function memoryStorage(seed = {}) {
  const map = new Map(Object.entries(seed))
  return {
    getItem: key => (map.has(key) ? map.get(key) : null),
    setItem: (key, value) => map.set(key, String(value)),
    dump: () => Object.fromEntries(map),
  }
}
function deferred() {
  let resolve, reject
  const promise = new Promise((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}
const plain = value => JSON.parse(JSON.stringify(value))

test('hub restores filters, scroll position and a minimal last visit', () => {
  const storage = memoryStorage({
    [FILTER_KEY]: JSON.stringify({ category: 2, difficulty: 'hard', status: 'unsolved', scrollTop: 480 }),
    [VISIT_KEY]: JSON.stringify({ id: 7, title: '栈溢出入门', at: 1000, flag: 'flag{leak}' }),
  })
  const hub = createHubState({ storage })
  hub.restore()
  assert.deepEqual(plain(hub.state.filters), { category: 2, difficulty: 'hard', status: 'unsolved' })
  assert.equal(hub.state.scrollTop, 480)
  assert.deepEqual(plain(hub.state.lastVisit), { id: 7, title: '栈溢出入门', at: 1000 })
  hub.rememberVisit({ id: 7, title: '栈溢出入门', flag: 'flag{leak}' })
  assert.equal(storage.getItem(VISIT_KEY).includes('flag{'), false)

  hub.setFilter({ category: 3, difficulty: null, status: 'solved' })
  assert.deepEqual(readPreferences(storage).filters, { category: 3, difficulty: null, status: 'solved' })
})

test('only a reference, title and time are stored when remembering a visit', () => {
  const storage = memoryStorage()
  const hub = createHubState({ storage, now: () => 42 })
  hub.rememberVisit({ id: 9, title: '命令注入', flag: 'flag{secret}', description: 'answer' })
  assert.deepEqual(plain(hub.state.lastVisit), { id: 9, title: '命令注入', at: 42 })
  const saved = JSON.parse(storage.getItem(VISIT_KEY))
  assert.deepEqual(saved, { id: 9, title: '命令注入', at: 42 })
  assert.equal(JSON.stringify(saved).includes('secret'), false)
  hub.rememberVisit({ title: '无编号' })
  assert.equal(hub.state.lastVisit.id, 9)
})

test('a late list response cannot replace newer filters or clear their loading state', async () => {
  const pending = []
  const hub = createHubState({ apiClient: { list: params => new Promise(resolve => pending.push({ params, resolve })) } })
  const first = hub.loadList({ category: 1 })
  const second = hub.loadList({ category: 2 })
  assert.deepEqual(pending.map(item => item.params), [{ category: 1 }, { category: 2 }])
  pending[0].resolve({ results: [{ id: 1 }], count: 1 })
  await first
  assert.deepEqual(hub.state.challenges, [])
  assert.equal(hub.state.loading.list, true)
  pending[1].resolve({ results: [{ id: 2 }], count: 1 })
  await second
  assert.deepEqual(plain(hub.state.challenges), [{ id: 2 }])
  assert.equal(hub.state.loading.list, false)
  assert.equal(hub.state.totalCount, 1)
})

test('list failures are stated and never leave an old list looking current', async () => {
  let fail = false
  const hub = createHubState({ apiClient: { list: async () => { if (fail) throw Error('offline'); return { results: [{ id: 4 }], count: 1 } } } })
  await hub.loadList()
  assert.equal(hub.state.challenges.length, 1)
  fail = true
  await hub.loadList()
  assert.match(hub.state.errors.list, /重试/)
  assert.deepEqual(hub.state.challenges, [])
})

test('filter solved counts only claim full coverage once every page is loaded', async () => {
  const hub = createHubState({ apiClient: { list: async () => ({ results: [{ id: 1, is_solved: true }, { id: 2, is_solved: false }], count: 5 }) } })
  await hub.loadList()
  assert.deepEqual(hub.solvedInFilter(), { solved: 1, scope: 'loaded' })

  hub.state.challenges.push({ id: 3, is_solved: true }, { id: 4, is_solved: true }, { id: 5, is_solved: false })
  assert.deepEqual(hub.solvedInFilter(), { solved: 3, scope: 'filter' })
})

test('an unavailable resume target stays visible with its reference intact', () => {
  const storage = memoryStorage({ [VISIT_KEY]: JSON.stringify({ id: 99, title: '已下架题目', at: 10 }) })
  const hub = createHubState({ storage })
  hub.restore()
  hub.state.challenges = [{ id: 1, title: '现有题目' }]
  assert.deepEqual(plain(hub.resumeCandidate()), { id: 99, title: '已下架题目', at: 10, available: false })

  hub.state.challenges.push({ id: 99, title: '改名后的题目' })
  assert.deepEqual(plain(hub.resumeCandidate()), { id: 99, title: '改名后的题目', at: 10, available: true })
})
