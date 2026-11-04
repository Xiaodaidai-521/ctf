import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { computed, effectScope, nextTick, reactive, ref, watch } from 'vue'
import { cockpitError, cockpitPriorities, cockpitTiles } from './model.js'

function harness(api) {
  const source = readFileSync(new URL('../TeacherDashboard.vue', import.meta.url), 'utf8')
  const script = source.match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '')
  const user = reactive({ userInfo: { id: 2, role: 'teacher' } })
  const scope = effectScope()
  let dispose
  const page = scope.run(() => runInNewContext(`${script}\n;({load,sources,loading,tiles,priorities})`, {
    computed, reactive, ref, watch, onMounted() {}, onUnmounted(fn) { dispose = fn },
    useUserStore: () => user, names: {}, cockpitApi: api, cockpitError, cockpitPriorities, cockpitTiles,
  }))
  return { page, user, close() { dispose(); scope.stop() } }
}
const deferred = () => { let resolve; return { promise: new Promise(done => { resolve = done }), resolve: value => resolve(value) } }

test('cockpit resolves independent real sources and retains readable denied state', async () => {
  const h = harness({
    resources: async () => { throw { response: { status: 403 } } },
    materials: async () => ({ results: [{ review_status: 'in_review' }] }),
    reviews: async () => ({ counts: { manual_pending: 0, sampling_pending: 2, disputes_pending: 1 } }),
    feedback: async () => ({ counts: { pending_fact_review: 0, pending_evidence: 0, confirmed: 0, reopened: 0 }, items: [] }),
    paths: async () => [{ is_published: false }],
  })
  try {
    await h.page.load()
    assert.equal(h.page.loading.value, false)
    const tile = key => h.page.tiles.value.find(item => item.key === key)
    assert.equal(tile('resources').count, null)
    assert.match(tile('resources').error, /核对授权/)
    assert.equal(tile('manual').count, 0)
    assert.equal(tile('sampling').count, 2)
    assert.equal(tile('paths').count, 1)
    assert.equal(tile('materials').count, 1)
    assert.equal(tile('feedback').count, 0)
  } finally { h.close() }
})

test('older refresh and identity-switched responses never restore cockpit data', async () => {
  const first = deferred(), second = deferred()
  let calls = 0
  const h = harness({ resources: () => ++calls === 1 ? first.promise : second.promise })
  try {
    const old = h.page.load(), current = h.page.load()
    second.resolve({ counts: { pending: 2 } }); await current
    first.resolve({ counts: { pending: 99 } }); await old
    assert.equal(h.page.sources.resources.data.counts.pending, 2)
    const late = deferred()
    const j = harness({ resources: () => late.promise })
    try {
      const pending = j.page.load()
      j.user.userInfo = { id: 8, role: 'teacher' }; await nextTick()
      late.resolve({ count: 99 }); await pending
      assert.equal(j.page.sources.resources.data, null)
      assert.equal(j.page.loading.value, false)
    } finally { j.close() }
  } finally { h.close() }
})

test('unmounted cockpit cannot be repopulated by a late request', async () => {
  const late = deferred(), h = harness({ resources: () => late.promise })
  const pending = h.page.load(); h.close(); late.resolve({ count: 12 }); await pending
  assert.equal(h.page.sources.resources.data, null)
})
