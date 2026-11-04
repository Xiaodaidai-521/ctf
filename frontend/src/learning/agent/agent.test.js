import test from 'node:test'
import assert from 'node:assert/strict'
import * as publicApi from './public.js'
import { subscribe, resetLifecycle, trackRequest } from './lifecycle.js'
import { clearDraft, queueDraft, takeDraft, subscribeDraft } from './draft.js'

const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no }); return { promise, resolve, reject } }
test('public boundary exposes opening and subscription only', () => {
  assert.deepEqual(Object.keys(publicApi).sort(), ['openTutor', 'subscribeTutor'])
})
test('pet follows actual request resolution, not an elapsed timer', async () => {
  resetLifecycle()
  const phases = []
  const off = subscribe(state => phases.push(state.phase))
  const request = deferred()
  const tracked = trackRequest(() => request.promise)
  assert.deepEqual(phases, ['idle', 'working'])
  request.resolve('response')
  assert.equal(await tracked, 'response')
  assert.deepEqual(phases, ['idle', 'working', 'complete'])
  off()
})
test('failed request reports error and propagates rejection', async () => {
  resetLifecycle()
  const phases = []
  const off = publicApi.subscribeTutor(state => phases.push(state))
  await assert.rejects(trackRequest(() => Promise.reject(new Error('offline'))), /offline/)
  assert.equal(phases.at(-1).phase, 'error')
  assert.match(phases.at(-1).label, /重试/)
  off()
})
test('reset or newer request invalidates late completion', async () => {
  resetLifecycle()
  const phases = []
  const off = subscribe(state => phases.push(state.phase))
  const old = deferred()
  const tracked = trackRequest(() => old.promise)
  resetLifecycle()
  old.resolve('late')
  await tracked
  assert.equal(phases.at(-1), 'idle')
  const a = deferred()
  const b = deferred()
  const first = trackRequest(() => a.promise)
  const second = trackRequest(() => b.promise)
  a.resolve('old')
  await first
  assert.equal(phases.at(-1), 'working')
  b.resolve('new')
  await second
  assert.equal(phases.at(-1), 'complete')
  off()
})
test('opening hands a question to the same mounted conversation without exposing it in URL', async () => {
  clearDraft()
  let notice = 0
  const off = subscribeDraft(() => notice++)
  const paths = []
  const router = { currentRoute: { value: { path: '/multi-agent' } }, push: async path => paths.push(path) }
  await publicApi.openTutor(router, { prompt: '  private question  ', userId: 4 })
  assert.equal(notice, 1)
  assert.deepEqual(paths, ['/multi-agent?mode=learning'])
  assert.equal(takeDraft(4), 'private question')
  assert.equal(takeDraft(4), '')
  off()
})
test('cross-account and denied navigation cannot leak a pending question', async () => {
  queueDraft('old question', 3)
  assert.equal(takeDraft(4), '')
  assert.equal(takeDraft(3), '')
  await publicApi.openTutor({ currentRoute: { value: { path: '/login' } }, push: async () => {} }, { prompt: 'private', userId: 4 })
  assert.equal(takeDraft(4), '')
})
