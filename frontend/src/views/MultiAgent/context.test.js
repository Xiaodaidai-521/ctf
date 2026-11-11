import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { computed, reactive } from 'vue'

const source = readFileSync(new URL('./MultiAgentView.vue', import.meta.url), 'utf8')
const script = source.match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '')
const deferred = () => {
  let resolve
  return { promise: new Promise(done => { resolve = done }), resolve: value => resolve(value) }
}
function harness(detail) {
  const route = reactive({ params: { challengeId: '7' }, query: {}, path: '/multi-agent/7' })
  const lifecycle = {}, contexts = []
  let epoch = 0
  const page = runInNewContext(`${script}\n;({ applyChallengeContext })`, {
    computed, watch() {},
    onMounted: fn => { lifecycle.mount = fn }, onActivated: fn => { lifecycle.activate = fn },
    onDeactivated: fn => { lifecycle.deactivate = fn }, onBeforeUnmount: fn => { lifecycle.unmount = fn },
    useUserStore: () => ({ isAuthenticated: true, userInfo: { id: 1, role: 'student' } }),
    useRoute: () => route, useRouter: () => ({ replace() {} }),
    captureAccount: () => { const currentEpoch = epoch; return { current: () => currentEpoch === epoch } },
    practiceApi: { detail }, setPageContext: value => contexts.push({ destination: 'host', value }),
    clearPageContext: () => contexts.push({ destination: 'host', value: null }),
    agentSession: { setContext: value => contexts.push({ destination: 'session', value }) },
  })
  return { page, route, lifecycle, contexts, replaceAccount: () => { epoch++ } }
}

test('leaving the challenge deep link invalidates its pending context request', async () => {
  const pending = deferred(), h = harness(() => pending.promise)
  const request = h.page.applyChallengeContext()
  h.route.params = {}
  await h.page.applyChallengeContext()
  pending.resolve({ title: '上一道题' }); await request
  assert.equal(h.contexts.filter(item => item.value).length, 0)
})

test('cached deactivation rejects late context, and activation reloads the current challenge', async () => {
  const pending = deferred()
  let reads = 0
  const h = harness(() => ++reads === 1 ? pending.promise : Promise.resolve({ title: '重新读取的题目' }))
  const request = h.page.applyChallengeContext()
  h.lifecycle.deactivate()
  pending.resolve({ title: '迟到的题目' }); await request
  assert.equal(h.contexts.filter(item => item.value).length, 0)
  await h.lifecycle.activate()
  assert.equal(reads, 2)
  assert.equal(h.contexts.filter(item => item.value).length, 2)
  assert.equal(h.contexts.at(-1).value.title, '重新读取的题目')
})

test('account replacement and unmount reject in-flight challenge context', async () => {
  for (const invalidate of ['replaceAccount', 'unmount']) {
    const pending = deferred(), h = harness(() => pending.promise)
    const request = h.page.applyChallengeContext()
    if (invalidate === 'replaceAccount') h.replaceAccount()
    else h.lifecycle.unmount()
    pending.resolve({ title: '旧账号题目' }); await request
    assert.equal(h.contexts.filter(item => item.value).length, 0)
  }
})
