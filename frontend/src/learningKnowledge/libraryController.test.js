import test from 'node:test'
import assert from 'node:assert/strict'
import { canManageLibrary, createLibraryController, initialLibraryState, safeSourceLink } from './libraryController.js'
import { createRequestGeneration } from './requestGeneration.js'

const attempt = '00000000-0000-4000-8000-000000000001'
const row = { id: 'article:12', object_id: 12, source_type: 'article', title: '授权文章' }
function harness(role = 'student', overrides = {}) {
  const state = initialLibraryState()
  const generations = createRequestGeneration()
  const calls = []
  const api = Object.fromEntries(['search', 'evidence', 'materialSearch', 'materials', 'inspect', 'library', 'libraryDetail', 'upload'].map(name => [name, async (...args) => {
    calls.push({ name, args })
    if (overrides[name]) return overrides[name](...args)
    return { results: [], count: 0, next: null, previous: null }
  }]))
  const controller = createLibraryController({ state, privacy: { begin: () => generations.begin() }, api, getRole: () => role })
  return { state, calls, controller, clear: () => { generations.invalidate(); controller.clear() } }
}
function deferred() {
  let resolve
  const promise = new Promise(done => { resolve = done })
  return { promise, resolve }
}

test('only teacher/admin are management identities', () => {
  for (const role of ['student', 'staff', 'superuser', '', null, undefined]) assert.equal(canManageLibrary(role), false)
  for (const role of ['teacher', 'admin']) assert.equal(canManageLibrary(role), true)
})

for (const group of ['teaching', 'legal', 'platform']) {
  for (const action of ['search', 'inspect', 'upload']) {
    test(`student cannot ${action} in ${group}, even with a valid task UUID`, async () => {
      const h = harness()
      Object.assign(h.state, {
        group, rows: [row], count: 1, detail: row, attemptId: attempt, activeAttempt: attempt,
        file: new File(['text'], 'lesson.txt'), uploadOpen: true, uploadResult: { status: 'completed' },
      })
      await h.controller[action](action === 'inspect' ? { ...row, evidence_id: 'ev-1' } : undefined)
      assert.equal(h.calls.length, 0)
      assert.deepEqual(h.state.rows, [])
      assert.equal(h.state.count, 0)
      assert.equal(h.state.detail, null)
      assert.equal(h.state.file, null)
      assert.equal(h.state.uploadOpen, false)
      assert.equal(h.state.uploadResult, null)
      assert.match(h.state.error, /无权/)
    })
  }
}

test('unrecognized identities cannot select any library endpoint', async () => {
  for (const role of ['guest', 'staff', '', null]) {
    const h = harness(role)
    await h.controller.search()
    await h.controller.inspect(row)
    await h.controller.upload()
    assert.equal(h.calls.length, 0)
  }
})

for (const role of ['teacher', 'admin']) {
  for (const status of [401, 403, 404, 503]) {
    test(`${role}: denied detail ${status} clears both old list and old detail`, async () => {
      const denied = async () => { throw { response: { status } } }
      const h = harness(role, { inspect: denied })
      Object.assign(h.state, { rows: [row], detail: { excerpt: '旧内容' }, count: 1 })
      await h.controller.inspect({ ...row, material_id: 'm1', revision: 1 })
      assert.deepEqual(h.state.rows, [])
      assert.equal(h.state.count, 0)
      assert.equal(h.state.detail, null)
      assert.ok(h.state.error)
    })
  }
}

test('teacher material body matches are retained without title-only filtering', async () => {
  const match = { material_id: 'm1', title: '数据库实践', revision: 3, material_class: 'lesson' }
  const h = harness('teacher', { materialSearch: async () => ({ results: [match] }) })
  h.state.query = 'SQL注入'
  await h.controller.search()
  assert.equal(h.calls[0].name, 'materialSearch')
  assert.equal(h.calls[0].args[0], 'SQL注入')
  assert.deepEqual(h.state.rows, [match])
  await h.controller.inspect(match)
  assert.equal(h.calls[1].name, 'inspect')
  assert.deepEqual(h.calls[1].args.slice(0, 2), ['m1', 3])
})

test('catalog requests preserve source filter and one-based pagination contract', async () => {
  const h = harness('admin', { library: async () => ({ results: [row], count: 43, next: '/api/legal-kb/library/?page=3', previous: '/api/legal-kb/library/?page=1' }) })
  Object.assign(h.state, { group: 'platform', sourceType: 'article', query: '注入' })
  await h.controller.search(2)
  assert.deepEqual(h.calls[0].args[0], { group: 'platform', source_type: 'article', q: '注入', page: 2 })
  assert.equal(h.state.next, true)
  assert.equal(h.state.previous, true)
  assert.equal(h.state.count, 43)
  await h.controller.inspect(row)
  assert.equal(h.calls[1].name, 'libraryDetail')
  assert.deepEqual(h.calls[1].args.slice(0, 2), ['article', 12])
})

for (const event of ['blur', 'route change', 'session change', 'group change']) {
  test(`${event}: clears private inputs, aborts request, ignores late success`, async () => {
    const late = deferred()
    const h = harness('teacher', { materialSearch: () => late.promise })
    Object.assign(h.state, { query: '私密查询', uploadTitle: '未保存标题', file: new File(['secret'], 'a.txt'), uploadOpen: true })
    const request = h.controller.search()
    const signal = h.calls[0].args[1]
    h.clear()
    late.resolve({ results: [{ title: '不能复活的正文' }] })
    await request
    assert.equal(signal.aborted, true)
    assert.deepEqual(h.state, initialLibraryState())
  })
}

test('blur also ignores a late detail response', async () => {
  const late = deferred()
  const h = harness('admin', { libraryDetail: () => late.promise })
  h.state.group = 'platform'
  const request = h.controller.inspect(row)
  h.clear()
  late.resolve({ ...row, chunks: [{ text: '已离开页面的正文' }] })
  await request
  assert.equal(h.state.detail, null)
  assert.deepEqual(h.state.rows, [])
})

test('students cannot upload even by calling controller directly', async () => {
  const h = harness()
  h.state.file = new File(['text'], 'lesson.txt')
  await h.controller.upload()
  assert.equal(h.calls.length, 0)
})

test('teacher upload sends actual multipart contract and only completed is success', async () => {
  const job = { id: 4, title: '教师文档', status: 'completed', chunk_count: 2, embedded_count: 2 }
  const h = harness('teacher', { upload: async () => job })
  Object.assign(h.state, { file: new File(['正文'], 'lesson.txt'), uploadTitle: '教师文档', uploadVisibility: 'internal', rows: [row] })
  await h.controller.upload()
  const body = h.calls[0].args[0]
  assert.ok(body instanceof FormData)
  assert.deepEqual([...body.keys()].sort(), ['file', 'title', 'visibility'])
  assert.equal(body.get('file').name, 'lesson.txt')
  assert.equal(body.get('visibility'), 'internal')
  assert.equal(h.state.uploadResult, job)
  assert.equal(h.state.error, '')
  assert.equal(h.state.file, null)
  assert.deepEqual(h.state.rows, [])
})

test('422 preserves actual embedding failure and counts, never fake success', async () => {
  const job = { id: 5, status: 'failed', chunk_count: 2, embedded_count: 0, error_message: 'EMBEDDING_PROVIDER is not configured' }
  const h = harness('teacher', { upload: async () => { throw { response: { status: 422, data: job } } } })
  h.state.file = new File(['正文'], 'lesson.txt')
  await h.controller.upload()
  assert.equal(h.state.uploadResult.status, 'failed')
  assert.equal(h.state.uploadResult.embedded_count, 0)
  assert.equal(h.state.error, job.error_message)
})

test('successful transport with unfinished job still cannot claim indexing success', async () => {
  const h = harness('teacher', { upload: async () => ({ status: 'running', id: 6 }) })
  h.state.file = new File(['text'], 'lesson.txt')
  await h.controller.upload()
  assert.match(h.state.error, /未确认索引完成/)
})

test('unknown upload outcome remains unconfirmed', async () => {
  const h = harness('teacher', { upload: async () => { throw new Error('timeout') } })
  h.state.file = new File(['text'], 'lesson.txt')
  await h.controller.upload()
  assert.equal(h.state.uploadResult, null)
  assert.match(h.state.error, /未确认服务器结果/)
})

test('source links exclude executable schemes, protocol-relative paths and backslash redirects', () => {
  for (const unsafe of ['javascript:alert(1)', 'data:text/html,a', '//evil.example', '/\\evil.example', ' https://site.example', 'https://site.example\n']) assert.equal(safeSourceLink(unsafe), '')
  for (const safe of ['/community/article/1', '/resources?resource=2', '/capability-map', 'https://example.com/law']) assert.equal(safeSourceLink(safe), safe)
})
