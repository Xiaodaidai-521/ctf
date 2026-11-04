import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import { createPinia } from 'pinia'
import { usePetStore } from '../../store/pet.js'
import { connectPetSession, latestPetTurn } from './petBridge.js'
const read = path => readFileSync(new URL(path, import.meta.url), 'utf8')
const strip = source => source.replace(/^import .*$/gm, '').replace(/^export /gm, '')
const helpers = vm.runInNewContext(strip(read('./api.js')) + '\n;({ conversationMessages, restorableConversation })')
const sanitizeContext = vm.runInNewContext(strip(read('./context.js')) + '\n;sanitizeContext')
const create = vm.runInNewContext(strip(read('./sessionController.js')) + '\n;createSessionController', { ...helpers, sanitizeContext })
const plain = value => JSON.parse(JSON.stringify(value))
const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no }); return { promise, resolve, reject } }
const response = (content = '一起学习') => ({ conversation_id: 71, responses: [{ content, agent_name: '教学辅导师' }] })
const make = (request = async () => response(), apiClient = {}) => create({ userId: 'student-1', request, apiClient: { conversations: async () => [], ...apiClient } })

test('pet latest round clears immediately when the next user message arrives without deleting history', () => {
  const messages = [{ id: 1, role: 'user', content: '第一问' }, { id: 2, role: 'assistant', content: '第一答' }]
  assert.equal(latestPetTurn(messages).replies[0].content, '第一答')
  messages.push({ id: 3, role: 'user', content: '第二问' })
  assert.deepEqual(latestPetTurn(messages), { id: 3, question: '第二问', replies: [] })
  assert.equal(messages.length, 3)
  messages.push({ id: 4, role: 'assistant', content: '讲解' }, { id: 5, role: 'assistant', content: '练习' })
  assert.deepEqual(latestPetTurn(messages).replies.map(x => x.content), ['讲解', '练习'])
})

test('pet never shows an orphan assistant response as a made-up user round', () => {
  assert.deepEqual(latestPetTurn([{ role: 'assistant', content: '旧记录' }]), { id: null, question: '', replies: [] })
})

test('pet and complete conversation observe identical records and reuse the server conversation id', async () => {
  const sent = [], petSnapshots = [], fullSnapshots = []
  const session = make(async request => { sent.push(request); return response(request.message + '的讲解') })
  const pet = usePetStore(createPinia())
  const disconnect = connectPetSession(session, pet, value => petSnapshots.push(value))
  session.subscribe(value => fullSnapshots.push(value))
  await session.send({ message: '宠物里问', agentIds: ['tutor'] })
  await session.send({ message: '完整页继续', agentIds: ['tutor'] })
  assert.equal(sent[0].conversationId, null)
  assert.equal(sent[1].conversationId, 71)
  assert.deepEqual(plain(petSnapshots.at(-1).messages), plain(fullSnapshots.at(-1).messages))
  assert.equal(session.state.messages.length, 4)
  assert.equal(latestPetTurn(session.state.messages).question, '完整页继续')
  disconnect()
})

test('pet follows real pending, completion, acknowledgment, failure and retry lifecycle events', async () => {
  let pending = deferred()
  const session = make(() => pending.promise)
  const pet = usePetStore(createPinia())
  const disconnect = connectPetSession(session, pet, () => {})
  assert.equal(pet.state, 'idle')
  const first = session.send({ message: '第一问' })
  assert.equal(pet.state, 'working')
  pending.resolve(response()); await first
  assert.equal(pet.state, 'ready')
  pet.acknowledge('teaching-session')
  assert.equal(pet.state, 'idle')
  pending = deferred()
  const failed = session.send({ message: '第二问' })
  pending.reject(new Error('offline')); await failed
  assert.equal(pet.state, 'failed')
  pending = deferred()
  const retry = session.send({ message: '再试' })
  assert.equal(pet.state, 'working')
  pending.resolve(response()); await retry
  assert.equal(pet.state, 'ready')
  disconnect()
})

test('hiding, collapsing and changing a pet never cancels or splits the real teaching request', async () => {
  const pending = deferred(), session = make(() => pending.promise), pet = usePetStore(createPinia())
  const off = connectPetSession(session, pet, () => {})
  const sending = session.send({ message: '跨页问题' })
  pet.setHidden(true); pet.setPack('/pets/xiaoju'); pet.reveal(); pet.setOpened(false)
  assert.equal(pet.state, 'working')
  pending.resolve(response()); await sending
  assert.equal(pet.state, 'ready')
  assert.equal(session.state.conversationId, 71)
  pet.reveal()
  assert.equal(pet.opened, true)
  off()
})

test('an actual new-conversation confirmation produces waiting without a synthetic timer', async () => {
  const pet = usePetStore(createPinia()), session = make()
  const off = connectPetSession(session, pet, () => {})
  await session.send({ message: '已完成' })
  const token = pet.requestInput('teaching-confirmation')
  assert.equal(pet.state, 'needs-input')
  pet.clear('teaching-confirmation', token)
  assert.equal(pet.state, 'ready')
  await session.reset()
  assert.equal(pet.state, 'idle')
  off()
})

test('cancelled or account-stale replies cannot switch the pet into a false completed state', async () => {
  let pending = deferred()
  const session = make(() => pending.promise), pet = usePetStore(createPinia())
  const off = connectPetSession(session, pet, () => {})
  const first = session.send({ message: '先停止' })
  session.cancelWaiting()
  assert.equal(pet.state, 'idle')
  pending.resolve(response('不应出现')); await first
  assert.equal(pet.state, 'idle')
  assert.equal(latestPetTurn(session.state.messages).replies.length, 0)
  pending = deferred()
  const second = session.send({ message: '旧账号' })
  session.setAccount('new-user'); pet.reset()
  pending.resolve(response('隐私回答')); await second
  assert.equal(pet.state, 'idle')
  assert.deepEqual(plain(session.state.messages), [])
  off()
})

test('send waits for real history restoration rather than racing into a new conversation', async () => {
  const pending = deferred(), calls = []
  const session = make(async input => { calls.push(input); return response() }, {
    conversations: () => pending.promise,
    conversation: async () => ({ messages: [{ id: 1, role: 'user', content: '原问题' }] }),
  })
  const restore = session.restore()
  assert.equal((await session.send({ message: '太早发送' })).reason, 'restoring')
  assert.equal(calls.length, 0)
  pending.resolve([{ id: 71, message_count: 1 }]); await restore
  await session.send({ message: '继续' })
  assert.equal(calls[0].conversationId, 71)
})

test('reset during restore clears the restore lock and rejects the old history response', async () => {
  const pending = deferred()
  const session = make(undefined, { conversations: () => pending.promise })
  const restore = session.restore()
  await session.reset()
  assert.equal(session.state.restoring, false)
  pending.resolve([{ id: 1, message_count: 2 }]); await restore
  assert.equal(session.state.conversationId, null)
  assert.equal((await session.send({ message: '新的问题' })).ok, true)
})

test('empty or error-only teaching output is failure, never a waving false success', async () => {
  for (const payload of [{}, { responses: [{ content: ' ', provider: 'local' }] }, { responses: [{ content: 'unavailable', provider: 'error' }] }]) {
    const session = make(async () => payload), pet = usePetStore(createPinia())
    const off = connectPetSession(session, pet, () => {})
    assert.equal((await session.send({ message: '问题' })).ok, false)
    assert.equal(pet.state, 'failed')
    assert.equal(latestPetTurn(session.state.messages).replies.length, 0)
    off()
  }
})

test('shared replies preserve structured learning cards, unmatched notice and image without duplicating cards', async () => {
  const cards = [{ title: '复习课程', entry: '/resources' }]
  const session = make(async () => ({ ...response(), resources: cards, noMatchedResource: true,
    responses: [{ content: '第一步', image_url: '/lesson.png' }, { content: '第二步', rag_sources: [{ id: 'source-1' }] }] }))
  await session.send({ message: '继续学习' })
  const replies = session.state.messages.filter(message => message.role === 'assistant')
  assert.deepEqual(plain(replies[0].resourceList), [])
  assert.equal(replies[0].imageUrl, '/lesson.png')
  assert.deepEqual(plain(replies[1].resourceList), cards)
  assert.equal(replies[1].noMatchedResource, true)
  assert.deepEqual(plain(replies[1].resources), [{ id: 'source-1' }])
})

test('full-page draft handoff waits for restoration and busy completion before consuming once', () => {
  const source = read('./components/TutorHost.vue')
  const fn = source.match(/function takePendingDraft\(\) \{[\s\S]*?\n\}/)[0]
  let pending = '不能丢失的首问', taken = 0
  const submitted = []
  const session = { state: { restoring: true, sending: false } }
  const context = { active: true, account: { current: () => true }, session, user: { userInfo: { id: 7 } },
    takeDraft: () => { taken++; const value = pending; pending = ''; return value }, submit: value => submitted.push(value) }
  const drain = vm.runInNewContext(`${fn}; takePendingDraft`, context)
  drain(); assert.equal(taken, 0)
  session.state.restoring = false; session.state.sending = true
  drain(); assert.equal(taken, 0)
  session.state.sending = false; context.active = false
  drain(); assert.equal(taken, 0)
  context.active = true; drain(); drain()
  assert.deepEqual(submitted, ['不能丢失的首问'])
  assert.match(source, /watch\(\[restoring, sending\], \(\) => takePendingDraft\(\)\)/)
})

test('pet SFC compiles with actual Vue script and template compilers', () => {
  for (const file of ['../../components/PlatformPet.vue', './TutorPet.vue', '../../components/PetSelector.vue', '../../views/MultiAgent/MultiAgentView.vue']) {
    const { descriptor, errors } = parse(read(file))
    assert.deepEqual(errors, [])
    const script = compileScript(descriptor, { id: file })
    const template = compileTemplate({ id: file, source: descriptor.template.content, filename: file, compilerOptions: { bindingMetadata: script.bindings } })
    assert.deepEqual(template.errors, [])
  }
})

test('pet presentation stays bounded, keyboard-accessible, reduced-motion aware and timer-free', () => {
  const source = read('../../components/PlatformPet.vue')
  assert.match(source, /max-height: min\(var\(--content-short-height\), 28dvh\)/)
  assert.match(source, /overflow-y: auto/)
  assert.match(source, /@contextmenu\.prevent="openMenu"/)
  assert.match(source, /event\.key === 'ContextMenu'/)
  assert.match(source, /event\.isComposing \|\| composing\.value/)
  assert.match(source, /reducedMotion\.value \|\| !pageVisible\.value/)
  assert.doesNotMatch(source, /setTimeout|setInterval|v-html|localStorage|sessionStorage/)
  assert.match(source, /隐藏宠物以及智能体/)
  assert.match(source, /切换形象/)
})

test('all roles use the same full teaching host, preserving staff explicit collaboration and recall', () => {
  const app = read('../../App.vue'), page = read('../../views/MultiAgent/MultiAgentView.vue'), header = read('../../shared/layout/GlobalHeader.vue')
  assert.equal((app.match(/<TutorPet\b/g) || []).length, 1)
  assert.match(app, /<TutorPet v-if="user\.isAuthenticated"/)
  assert.doesNotMatch(app, /<PlatformPet/)
  assert.match(page, /v-if="isStudent \|\| !collaboration"/)
  assert.match(page, /<LegacyMultiAgentView v-else/)
  assert.match(header, /value="recall-pet"/)
  assert.match(header, /pet\.reveal\(\)/)
  assert.match(app, /pet\.reset\(\)/)
  const legacy = read('../../components/MultiAgent/legacy/LegacyMultiAgentChat.vue')
  assert.match(legacy, /if \(isTutorSelected\.value\) \{[\s\S]*agentSession\.send/)
  assert.match(legacy, /agentSession\.subscribe\(applyTeachingSession\)/)
})
