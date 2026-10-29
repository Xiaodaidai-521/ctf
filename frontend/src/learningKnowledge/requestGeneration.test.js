import test from 'node:test'
import assert from 'node:assert/strict'
import { createRequestGeneration, requestKey } from './requestGeneration.js'
import { materialExample, parseMaterialForm } from './materialForm.js'

function deferred() {
  let resolve
  const promise = new Promise(done => { resolve = done })
  return { promise, resolve }
}

test('latest request in a channel wins even when the old transport still resolves', async () => {
  const scope = createRequestGeneration()
  const response = deferred()
  const first = scope.begin()
  let displayed = ''
  const completion = response.promise.then(value => { if (first.isCurrent()) displayed = value })
  const second = scope.begin()
  assert.equal(first.signal.aborted, true)
  assert.equal(first.isCurrent(), false)
  assert.equal(second.isCurrent(), true)
  response.resolve('old source text')
  await completion
  assert.equal(displayed, '')
})

for (const event of ['user switch', 'attempt switch', 'route leave', 'blur', 'hidden', 'pagehide']) {
  test(`${event}: invalidate rejects old responses, including after resuming`, async () => {
    const scope = createRequestGeneration()
    const old = scope.begin()
    const response = deferred()
    let displayed = 'previous source'
    const completion = response.promise.then(value => { if (old.isCurrent()) displayed = value })
    scope.invalidate()
    displayed = ''
    const fresh = scope.begin()
    response.resolve('stale source')
    await completion
    assert.equal(old.signal.aborted, true)
    assert.equal(old.isCurrent(), false)
    assert.equal(fresh.isCurrent(), true)
    assert.equal(displayed, '')
  })
}

test('old finally handler cannot finish the new request', () => {
  const scope = createRequestGeneration()
  const old = scope.begin()
  const fresh = scope.begin()
  old.finish()
  assert.equal(fresh.isCurrent(), true)
  fresh.finish()
  assert.equal(fresh.isCurrent(), false)
})

test('context guard blocks display before browser or watcher handlers run', () => {
  let foregroundAndSameSession = true
  const scope = createRequestGeneration(() => foregroundAndSameSession)
  const request = scope.begin()
  foregroundAndSameSession = false
  assert.equal(request.isCurrent(), false)
})

test('invalidate cancels all channels and dispose is terminal', () => {
  const scope = createRequestGeneration()
  const first = scope.begin('read')
  const second = scope.begin('write')
  assert.equal(first.isCurrent(), true)
  scope.dispose()
  assert.equal(first.signal.aborted, true)
  assert.equal(second.signal.aborted, true)
  assert.equal(second.isCurrent(), false)
  assert.throws(() => scope.begin(), /disposed/)
})

test('request and idempotency keys are bounded and distinct', () => {
  const keys = Array.from({ length: 100 }, requestKey)
  assert.equal(new Set(keys).size, 100)
  assert.ok(keys.every(key => key.length > 0 && key.length <= 64 && /^[a-z0-9-]+$/i.test(key)))
})

test('register and revision examples follow their real serializer shapes', () => {
  const registration = parseMaterialForm(materialExample('register'), 'register')
  const revision = parseMaterialForm(materialExample('revise'), 'revise')
  assert.equal(registration.material_class, 'lesson')
  assert.deepEqual(Object.keys(revision).sort(), ['metadata', 'task_ids'])
  assert.equal(revision.metadata.source_snapshot.includes('\n\n'), true)
})

test('strict form refuses unsupported authority fields and bad task IDs', () => {
  const base = JSON.parse(materialExample('register'))
  for (const field of ['user_id', 'published_scope', 'review_status', 'expected_revision']) {
    assert.throws(() => parseMaterialForm(JSON.stringify({ ...base, [field]: 1 }), 'register'), /不支持字段/)
  }
  assert.throws(() => parseMaterialForm(JSON.stringify({ ...base, task_ids: ['TASK-1'] }), 'register'), /task_ids/)
  assert.throws(() => parseMaterialForm(JSON.stringify(base), 'revise'), /不支持字段/)
  assert.throws(() => parseMaterialForm('{"task_ids": [1],}', 'revise'), /严格 JSON/)
})

test('form preserves raw snapshot literally and validates required metadata', () => {
  const base = JSON.parse(materialExample('revise'))
  base.metadata.source_snapshot = '  <script>alert(1)</script>\n\nLiteral source  '
  assert.equal(parseMaterialForm(JSON.stringify(base), 'revise').metadata.source_snapshot, base.metadata.source_snapshot)
  base.metadata.source_date = '2026-02-30'
  assert.throws(() => parseMaterialForm(JSON.stringify(base), 'revise'), /有效 YYYY-MM-DD/)
  base.metadata.source_date = '2026-02-28'
  delete base.metadata.license_id
  assert.throws(() => parseMaterialForm(JSON.stringify(base), 'revise'), /license_id/)
})
