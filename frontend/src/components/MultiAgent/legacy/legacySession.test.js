import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import * as Vue from 'vue'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import { compile } from '@vue/compiler-dom'
import { tutorResourceListFromResponse } from '../../../utils/tutorResources.js'

const read = path => readFileSync(new URL(path, import.meta.url), 'utf8')
const chatSource = read('./LegacyMultiAgentChat.vue')
const pageSource = read('../../../views/MultiAgent/MultiAgentView.vue')
const chatScript = compileScript(parse(chatSource).descriptor, { id: 'legacy-session' }).content
  .replace(/^import[\s\S]*?from\s*['"][^'"]+['"]\s*;?/gm, '')
  .replace('export default', 'const component =') + '\n;component'
const plain = value => JSON.parse(JSON.stringify(value))
const deferred = () => {
  let resolve, reject
  const promise = new Promise((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
const specialistResponse = (content = '协作回答') => ({
  conversation_id: 'collaboration-9', responses: [{ agent_id: 'xiaohei', agent_name: '小黑', content }],
})

// Execute the actual compiled SFC setup with real Vue reactivity; only I/O and
// lifecycle scheduling are substituted so pending requests can be controlled.
function makeChat({ storage = new Map(), request = async () => specialistResponse(), detail = async () => ({ messages: [] }), removeTeaching = async () => {} } = {}) {
  const hooks = { mounted: [], activated: [], deactivated: [], unmount: [] }
  const requests = [], teachingRequests = [], detailIds = [], removedIds = [], events = []
  const listeners = new Set()
  const drafts = vm.runInNewContext(read('../../../learning/agent/draft.js').replace(/^export /gm, '') + '\n;({ queueDraft, takeDraft, subscribeDraft })')
  const session = {
    state: { conversationId: 'teaching-7', messages: [{ id: 't-1', role: 'user', content: '教学问题' }], sending: false, restoring: false, error: '' },
    subscribe(listener) { listeners.add(listener); listener(this.state); return () => listeners.delete(listener) },
    publish(patch = {}) { Object.assign(this.state, patch); for (const listener of listeners) listener(this.state) },
    async send(input) { teachingRequests.push(input); return { ok: true } },
    async reset() {
      this.publish({ conversationId: null, messages: [], sending: false, restoring: false, error: '' })
      await removeTeaching()
      this.publish()
    },
  }
  const props = Vue.reactive({
    challengeId: null, initialMode: 'collaborative', selectedAgentIds: ['tutor'],
    initialAgents: [
      { id: 'tutor', name: '教学辅导师', status: 'available' },
      { id: 'xiaohei', name: '小黑', status: 'available' },
    ],
  })
  const component = vm.runInNewContext(chatScript, {
    ...Vue,
    onMounted: fn => hooks.mounted.push(fn), onActivated: fn => hooks.activated.push(fn),
    onDeactivated: fn => hooks.deactivated.push(fn), onBeforeUnmount: fn => hooks.unmount.push(fn),
    requestTeaching: input => { requests.push(input); return request(input) }, agentSession: session,
    resetLifecycle() {}, takeDraft: drafts.takeDraft, subscribeDraft: drafts.subscribeDraft,
    useRouter: () => ({ push() {} }), useUserStore: () => ({ isAuthenticated: true, userInfo: { id: 7 } }),
    Message: { warning() {}, info() {}, success() {}, error() {} },
    marked: { parse: text => text }, sanitizeHtml: text => text, RecordView: {},
    clearRememberedTutorResources() {}, rememberTutorResources() {}, tutorResourceListFromResponse,
    api: { conversation: {
      list: async () => { throw new Error('Teaching history must not be used for collaboration') },
      detail: id => { detailIds.push(id); return detail(id) },
      remove: async id => { removedIds.push(id) },
    } },
    sessionStorage: { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key) },
    console: { warn() {}, error() {} },
  })
  const scope = Vue.effectScope()
  const state = scope.run(() => component.setup(props, { expose() {}, emit: (...args) => events.push(args) }))
  return {
    state, props, session, drafts, requests, teachingRequests, detailIds, removedIds, storage, events,
    mount: () => Promise.all(hooks.mounted.map(fn => fn())),
    activate: () => hooks.activated.forEach(fn => fn()), deactivate: () => hooks.deactivated.forEach(fn => fn()),
    dispose() { hooks.unmount.forEach(fn => fn()); scope.stop() },
    async select(id) { props.selectedAgentIds = [id]; await Vue.nextTick() },
    send(text) { state.inputText.value = text; return state.sendMessage() },
  }
}

test('a specialist request completes in its own transcript while tutor is selected and the workbench is deactivated', async t => {
  const pending = deferred()
  const chat = makeChat({ request: () => pending.promise })
  t.after(() => chat.dispose())
  await chat.mount()
  await chat.select('xiaohei')
  const sending = chat.send('协作问题')
  assert.equal(chat.state.isProcessing.value, true)
  await chat.select('tutor')
  chat.deactivate()
  pending.resolve(specialistResponse())
  await sending
  assert.equal(chat.props.initialAgents[1].status, 'available')
  assert.equal(chat.state.collaborationProcessing.value, false)
  assert.equal(chat.session.state.conversationId, 'teaching-7')
  assert.equal(chat.state.conversationId.value, 'collaboration-9')
  assert.equal(chat.storage.get('multiAgentConversationId'), 'collaboration-9')
  chat.activate()
  assert.deepEqual(plain(chat.state.messages.value.map(item => item.content)), ['教学问题'])
  await chat.select('xiaohei')
  assert.deepEqual(plain(chat.state.messages.value.map(item => item.content)), ['协作问题', '协作回答'])
  assert.equal(chat.state.messages.value.some(item => item.type === 'thinking'), false)
  assert.equal(chat.state.isProcessing.value, false)
  await chat.send('继续协作')
  assert.equal(chat.requests[1].conversationId, 'collaboration-9')
})

test('switching away and back does not unlock a pending specialist request or discard a failed response', async t => {
  const pending = deferred()
  const chat = makeChat({ request: () => pending.promise })
  t.after(() => chat.dispose())
  await chat.mount()
  await chat.select('xiaohei')
  const sending = chat.send('第一问')
  await chat.select('tutor')
  assert.equal(chat.state.isProcessing.value, false)
  await chat.select('xiaohei')
  assert.equal(chat.state.isProcessing.value, true)
  await chat.send('重复提交')
  assert.equal(chat.requests.length, 1)
  await chat.select('tutor')
  pending.reject(new Error('offline'))
  await sending
  await chat.select('xiaohei')
  assert.equal(chat.props.initialAgents[1].status, 'available')
  assert.equal(chat.state.isProcessing.value, false)
  assert.equal(chat.state.messages.value.some(item => item.type === 'thinking'), false)
  assert.match(chat.state.messages.value.at(-1).content, /暂时无法完成讲解/)
})

test('a remounted workbench restores only its saved collaboration ID while projecting the tutor session separately', async t => {
  const storage = new Map([['multiAgentConversationId', 'collaboration-9']])
  const history = deferred()
  const chat = makeChat({ storage, detail: () => history.promise })
  t.after(() => chat.dispose())
  const mounting = chat.mount()
  assert.deepEqual(chat.detailIds, ['collaboration-9'])
  assert.equal(chat.state.conversationId.value, 'collaboration-9')
  assert.deepEqual(plain(chat.state.messages.value.map(item => item.content)), ['教学问题'])
  await chat.select('xiaohei')
  assert.equal(chat.state.isProcessing.value, true)
  await chat.send('恢复未完不能另开会话')
  assert.equal(chat.requests.length, 0)
  await chat.select('tutor')
  history.resolve({ messages: [
    { id: 1, role: 'user', content: '旧协作问题' },
    { id: 2, role: 'assistant', agent_id: 'xiaohei', agent_name: '小黑', content: '旧协作回答' },
  ] })
  await mounting
  assert.deepEqual(plain(chat.state.messages.value.map(item => item.content)), ['教学问题'])
  await chat.select('xiaohei')
  assert.deepEqual(plain(chat.state.messages.value.map(item => item.content)), ['旧协作问题', '旧协作回答'])
  await chat.send('继续旧协作')
  assert.equal(chat.requests[0].conversationId, 'collaboration-9')
  assert.equal(chat.session.state.conversationId, 'teaching-7')
})

test('a new specialist conversation never inherits the global tutor conversation ID', async t => {
  const chat = makeChat()
  t.after(() => chat.dispose())
  await chat.mount()
  assert.deepEqual(chat.detailIds, [])
  await chat.select('xiaohei')
  await chat.send('新的协作')
  assert.equal(chat.requests[0].conversationId, null)
  assert.equal(chat.session.state.conversationId, 'teaching-7')
})

test('a deactivated workbench cannot steal a draft from the visible teaching host', async t => {
  const chat = makeChat()
  t.after(() => chat.dispose())
  await chat.mount()
  await chat.select('xiaohei')
  chat.deactivate()
  const received = []
  const unsubscribeHost = chat.drafts.subscribeDraft(() => received.push(chat.drafts.takeDraft(7)))
  t.after(unsubscribeHost)
  chat.drafts.queueDraft('交给可见教学页', 7)
  assert.deepEqual(received, ['交给可见教学页'])
  assert.equal(chat.requests.length, 0)
  assert.equal(chat.teachingRequests.length, 0)
  chat.activate()
  assert.equal(chat.requests.length, 0)
})

test('structured tutor resources, empty-resource notices and chart-gated image URLs survive projection', async t => {
  const chat = makeChat({ storage: new Map([['learningCenterChartMode', 'enabled']]) })
  t.after(() => chat.dispose())
  await chat.mount()
  const resource = { id: 5, title: '学习资料', type: 'article', entry: '/articles/5' }
  const rag = { title: '检索依据', entry: '/articles/6' }
  chat.session.publish({ messages: [
    { id: 1, role: 'assistant', content: '讲解', resources: [rag], resourceList: [], imageUrl: '/chart.png' },
    { id: 2, role: 'assistant', content: '总结', resourceList: [resource], noMatchedResource: false },
    { id: 3, role: 'assistant', content: '暂无资料', resourceList: [], noMatchedResource: true },
  ] })
  const projected = chat.state.messages.value
  assert.equal(chat.state.messageResources(projected[0]).length, 0)
  assert.deepEqual(plain(projected[0].rag_sources), [rag])
  assert.equal(chat.state.messageResources(projected[1])[0].entry, '/articles/5')
  assert.equal(projected[2].noMatchedResource, true)
  assert.equal(projected[0].image_url, '/chart.png')
  chat.state.chartModeEnabled.value = false
  chat.session.publish()
  assert.equal(chat.state.messages.value[0].image_url, null)
})

test('legacy chart mode retains its per-round fallback image on only the final tutor reply', async t => {
  const chat = makeChat({ storage: new Map([['learningCenterChartMode', 'enabled']]) })
  t.after(() => chat.dispose())
  await chat.mount()
  chat.session.publish({ messages: [
    { id: 1, role: 'user', content: '请分析我的学习进度表' },
    { id: 2, role: 'assistant', content: '分析' },
    { id: 3, role: 'assistant', content: '总结' },
    { id: 4, role: 'user', content: '普通问题' },
    { id: 5, role: 'assistant', content: '普通回答' },
  ] })
  assert.equal(chat.state.messages.value[1].image_url, null)
  assert.equal(chat.state.messages.value[2].image_url, '/assets/demo_images/learning_progress_analysis.png?v=2')
  assert.equal(chat.state.messages.value[4].image_url, null)
})

test('restarting tutor clears only the old draft before slow deletion and leaves collaboration untouched', async t => {
  const deletion = deferred()
  const chat = makeChat({ removeTeaching: () => deletion.promise })
  t.after(() => chat.dispose())
  await chat.mount()
  await chat.select('xiaohei')
  await chat.send('保留协作')
  await chat.select('tutor')
  chat.state.inputText.value = '旧草稿'
  const resetting = chat.state.clearSession()
  assert.equal(chat.state.inputText.value, '')
  chat.state.inputText.value = '删除期间的新草稿'
  deletion.resolve()
  await resetting
  assert.equal(chat.state.inputText.value, '删除期间的新草稿')
  assert.equal(chat.state.conversationId.value, 'collaboration-9')
  assert.equal(chat.storage.get('multiAgentConversationId'), 'collaboration-9')
  await chat.select('xiaohei')
  assert.deepEqual(plain(chat.state.messages.value.map(item => item.content)), ['保留协作', '协作回答'])
})

// A tiny non-DOM renderer exercises the real page template and Vue KeepAlive.
// It verifies caching/lifecycle rather than merely matching a KeepAlive tag.
function memoryRenderer() {
  const node = type => ({ type, children: [], parent: null, text: '' })
  return Vue.createRenderer({
    createElement: node, createText: text => ({ ...node('text'), text }), createComment: text => ({ ...node('comment'), text }),
    setText: (node, text) => { node.text = text }, setElementText: (node, text) => { node.text = text; node.children = [] },
    parentNode: node => node.parent,
    nextSibling: node => node.parent?.children[node.parent.children.indexOf(node) + 1] || null,
    patchProp() {},
    insert(node, parent, anchor = null) {
      if (node.parent) node.parent.children.splice(node.parent.children.indexOf(node), 1)
      node.parent = parent
      const index = anchor ? parent.children.indexOf(anchor) : -1
      parent.children.splice(index < 0 ? parent.children.length : index, 0, node)
    },
    remove(node) { if (node.parent) node.parent.children.splice(node.parent.children.indexOf(node), 1); node.parent = null },
  })
}

test('the actual staff page caches both work surfaces, preserving drafts and firing deactivation hooks', async () => {
  const instances = {}, counts = { tutor: 0, collaboration: 0 }
  const stub = name => Vue.defineComponent({
    setup() {
      counts[name]++
      const draft = Vue.ref(''), active = Vue.ref(false)
      instances[name] = { draft, active }
      Vue.onActivated(() => { active.value = true })
      Vue.onDeactivated(() => { active.value = false })
      return () => Vue.h('div', draft.value)
    },
  })
  const collaboration = Vue.ref(false)
  const template = parse(pageSource).descriptor.template.content
  const render = new Function('Vue', compile(template, { mode: 'function', prefixIdentifiers: true }).code)(Vue)
  const page = Vue.defineComponent({
    components: { TutorHost: stub('tutor'), LegacyMultiAgentView: stub('collaboration') },
    setup: () => ({ collaboration, isStudent: false, names: { guide: '智航' } }), render,
  })
  const app = memoryRenderer().createApp(page)
  app.mount({ children: [] })
  try {
    instances.tutor.draft.value = '教学草稿'
    collaboration.value = true
    await Vue.nextTick()
    assert.equal(instances.tutor.active.value, false)
    instances.collaboration.draft.value = '协作草稿'
    collaboration.value = false
    await Vue.nextTick()
    assert.equal(instances.collaboration.active.value, false)
    assert.equal(instances.tutor.draft.value, '教学草稿')
    collaboration.value = true
    await Vue.nextTick()
    assert.equal(instances.collaboration.draft.value, '协作草稿')
    assert.deepEqual(counts, { tutor: 1, collaboration: 1 })
  } finally { app.unmount() }
})

test('the changed workbench and page compile and retain the existing host branch contracts', () => {
  for (const [id, source] of [['legacy-chat', chatSource], ['multi-agent-page', pageSource]]) {
    const { descriptor, errors } = parse(source)
    assert.deepEqual(errors, [])
    const script = compileScript(descriptor, { id })
    const result = compileTemplate({ source: descriptor.template.content, id, filename: id + '.vue', compilerOptions: { bindingMetadata: script.bindings } })
    assert.deepEqual(result.errors, [])
  }
  assert.match(pageSource, /<TutorHost mode="page" \/>/)
  assert.match(pageSource, /<LegacyMultiAgentView v-else/)
  assert.match(pageSource, /v-if="isStudent \|\| !collaboration"/)
})
