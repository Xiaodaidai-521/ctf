import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compile, computed, createSSRApp, h, ref } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { parse } from 'vue/compiler-sfc'
import { canManageLibrary, libraryError } from './libraryController.js'
import { createRequestGeneration } from './requestGeneration.js'
import { errorMessage } from './api.js'

// Execute the component's real setup/load logic with the browser lifecycle boundary injected.
function sourcePage(role, concept = '3', fetch = async id => ({ id, name: '原始知识点', description: '原始正文' })) {
  const source = parse(readFileSync(new URL('./KnowledgeConceptSource.vue', import.meta.url), 'utf8')).descriptor.scriptSetup.content
  const calls = []
  const user = { userInfo: { role } }
  let clear
  const page = runInNewContext(source.replace(/^import .*$/gm, '') + '\n;({ load, source, busy, error })', {
    computed, ref, onMounted() {}, useRoute: () => ({ query: { concept } }), useUserStore: () => user,
    canManageLibrary, errorMessage,
    knowledgeApi: { conceptSource: async (...args) => { calls.push(args); return fetch(...args) } },
    usePrivatePage: clearContent => {
      const generations = createRequestGeneration()
      const paused = ref(true)
      clear = () => { generations.invalidate(); paused.value = true; clearContent() }
      return {
        paused, sessionChanged: ref(false),
        resume() { clear(); paused.value = false; return true },
        begin: () => generations.begin(),
      }
    },
  })
  return { page, calls, clear: () => clear() }
}

for (const role of ['teacher', 'admin']) {
  test(`${role}: original concept template shows name and body without ids or mechanism notes`, async () => {
    const template = parse(readFileSync(new URL('./KnowledgeConceptSource.vue', import.meta.url), 'utf8')).descriptor.template.content
    const app = createSSRApp({
      render: compile(template),
      setup: () => ({
        user: { userInfo: { role } }, managing: true, paused: false, busy: false, error: '',
        sessionChanged: false, privacy: {}, load() {}, libraryError,
        source: { id: 987654, concept_type: 'engineering_type', updated_at: 'private-timestamp', name: '授权测试', description: '<script>正文</script>' },
      }),
    })
    app.component('router-link', { props: ['to'], setup: (props, { slots }) => () => h('a', { href: props.to }, slots.default?.()) })
    for (const name of ['a-alert', 'a-button']) app.component(name, { setup: (_, { slots }) => () => h('div', slots.default?.()) })
    const html = await renderToString(app)
    assert.match(html, /知识点原文|授权测试/)
    assert.match(html, /&lt;script&gt;正文&lt;\/script&gt;/)
    assert.doesNotMatch(html, /987654|engineering_type|private-timestamp|ID|接口|索引|任务授权|<script>/)
    assert.ok(html.includes(`href="${role === 'teacher' ? '/teacher/knowledge' : '/admin/legal/kb'}"`))
  })
}

test('concept deep-link fetches original source, not copied index chunks', async () => {
  const h = sourcePage('teacher')
  await h.page.load()
  assert.equal(h.calls[0][0], '3')
  assert.equal(h.page.source.value.description, '原始正文')
})

test('student concept deep-link panel never fetches source', async () => {
  const h = sourcePage('student')
  await h.page.load()
  assert.equal(h.calls.length, 0)
  assert.equal(h.page.source.value, null)
})

test('invalid concept ids fail closed without issuing source request', async () => {
  for (const id of ['bad', '-1', '1.5', '9999999999999999999999999', ['1', '2']]) {
    const h = sourcePage('admin', id)
    await h.page.load()
    assert.equal(h.calls.length, 0)
    assert.match(h.page.error.value, /链接无效/)
  }
})

test('denied original source clears previous concept body', async () => {
  const h = sourcePage('teacher', '3', async () => { throw { response: { status: 403 } } })
  h.page.source.value = { description: '旧正文' }
  await h.page.load()
  assert.equal(h.page.source.value, null)
  assert.match(h.page.error.value, /拒绝/)
})

test('blur/route privacy reset prevents late original source from reappearing', async () => {
  let resolve
  const deferred = new Promise(done => { resolve = done })
  const h = sourcePage('teacher', '3', () => deferred)
  const request = h.page.load()
  h.clear()
  assert.equal(h.calls[0][1].aborted, true)
  resolve({ description: '延迟正文' })
  await request
  assert.equal(h.page.source.value, null)
  assert.equal(h.page.busy.value, false)
})
