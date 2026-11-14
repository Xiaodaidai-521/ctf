import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'

// 剥掉 @/api 依赖，直接测控制器契约。
function load(url) {
  return readFileSync(url, 'utf8')
}
const apiSource = load(new URL('./api.js', import.meta.url))
const host = vm.runInNewContext(apiSource
  .replace(/^import .*$/gm, '')
  .replace(/^export const /gm, 'const ')
  .replace(/^export function /gm, 'function ')
  .replace(/^export \{.*\}$/gm, '') + '\n;({ conversationMessages, restorableConversation })', {})
const contextSource = load(new URL('./context.js', import.meta.url))
  .replace(/^export function /gm, 'function ')
  .replace(/^const ALLOWED_KINDS/, 'const ALLOWED_KINDS')
const sanitizeContext = vm.runInNewContext(`${contextSource}\n;sanitizeContext`, {})
const controllerSource = load(new URL('./sessionController.js', import.meta.url))
  .replace(/^import .*$/gm, '')
  .replace('export function createSessionController', 'function createSessionController')
const make = sandbox => vm.runInNewContext(
  `${controllerSource}\n;createSessionController`,
  { conversationMessages: host.conversationMessages, restorableConversation: host.restorableConversation, sanitizeContext, ...sandbox },
)

const plain = value => JSON.parse(JSON.stringify(value))

test('restore picks the latest conversation that actually has messages', async () => {
  const asked = []
  const session = make({})({
    userId: 1,
    apiClient: {
      conversations: async () => [
        { id: 1, message_count: 0, updated_at: '2026-11-03T00:00:00Z' },
        { id: 2, message_count: 2, updated_at: '2026-11-01T00:00:00Z' },
      ],
      conversation: async id => { asked.push(id); return { messages: [{ id: 1, role: 'user', content: '学什么' }] } },
      removeConversation: async () => {},
    },
    request: async () => ({}),
  })
  const result = await session.restore()
  assert.deepEqual(plain(result), { restored: true, conversationId: 2 })
  assert.deepEqual(plain(asked), [2])
  assert.equal(session.state.messages.length, 1)
  assert.equal(session.state.restoring, false)
})

test('empty account history stays empty and says so instead of fabricating welcome messages', async () => {
  const session = make({})({
    userId: 1,
    apiClient: { conversations: async () => [], conversation: async () => ({}), removeConversation: async () => {} },
    request: async () => ({}),
  })
  assert.deepEqual(plain(await session.restore()), { restored: false, reason: 'empty' })
  assert.deepEqual(plain(session.state.messages), [])
  assert.equal(session.state.hasHistory, false)
})

test('send keeps one conversation and appends all real teaching steps', async () => {
  const sent = []
  const session = make({})({
    userId: 1,
    apiClient: { conversations: async () => [], conversation: async () => ({}), removeConversation: async () => {} },
    request: async payload => { sent.push(payload); return { conversation_id: 9, resources: [{ id: 1 }], responses: [
      { agent_name: '教学辅导师', content: '先讲思路' }, { agent_name: '教学辅导师', content: '再练习', step: 2 },
    ] } },
  })
  assert.equal((await session.send({ message: '  ' })).reason, 'empty')
  const result = await session.send({ message: '授权边界怎么判断', agentIds: ['tutor'] })
  assert.equal(result.ok, true)
  assert.equal(session.state.conversationId, 9)
  assert.deepEqual(plain(session.state.messages.map(item => item.role)), ['user', 'assistant', 'assistant'])
  assert.equal(session.state.resources.length, 1)
  assert.equal(session.state.phase, 'complete')
  assert.equal(sent[0].conversationId, null)
  await session.send({ message: '继续', agentIds: ['tutor'] })
  assert.equal(sent[1].conversationId, 9)
})

test('a second submit while working is refused, and late results never land after account switch', async () => {
  let release
  const session = make({})({
    userId: 1,
    apiClient: { conversations: async () => [], conversation: async () => ({}), removeConversation: async () => {} },
    request: () => new Promise(resolve => { release = resolve }),
  })
  const first = session.send({ message: '问题一' })
  await new Promise(resolve => setTimeout(resolve, 0))
  assert.deepEqual(plain(await session.send({ message: '问题二' })), { ok: false, reason: 'busy' })
  session.setAccount(2)
  release({ conversation_id: 5, responses: [{ content: '旧账号的讲解' }] })
  const result = await first
  assert.equal(result.reason, 'stale')
  assert.deepEqual(plain(session.state.messages), [])
  assert.equal(session.state.conversationId, null)
  assert.equal(session.state.sending, false)
})

test('reset clears locally by default and only deletes server history on explicit request', async () => {
  const removed = []
  const session = make({})({
    userId: 1,
    apiClient: {
      conversations: async () => [], conversation: async () => ({}),
      removeConversation: async id => { removed.push(id) },
    },
    request: async () => ({ conversation_id: 8, responses: [{ content: '讲解' }] }),
  })
  await session.send({ message: '问题' })
  await session.reset()
  assert.deepEqual(plain(removed), [])
  assert.deepEqual(plain(session.state.messages), [])
  assert.equal(session.state.conversationId, null)

  await session.send({ message: '问题' })
  await session.reset({ deleteServer: true })
  assert.deepEqual(plain(removed), [8])
})

test('context accepts only authorized references and never a flag', () => {
  const session = make({})({
    userId: 1, apiClient: { conversations: async () => [] }, request: async () => ({}),
  })
  session.setContext({ kind: 'challenge', id: 12, title: '授权练习', flag: 'flag{secret}', answer: 'x' })
  assert.deepEqual(plain(session.state.context), { kind: 'challenge', ref: '12', title: '授权练习', reason: '' })
  session.setContext({ kind: 'exam', ref: 1 })
  assert.equal(session.state.context, null)
})

test('saved protection is cleared during send and late verification cannot cross accounts', async () => {
  let finishVerification
  const session = make({})({ userId: 1,
    apiClient: { protection: () => new Promise(resolve => { finishVerification = resolve }) },
    request: async () => ({ conversation_id: 5, responses: [{ content: 'Saved answer' }] }),
  })
  const sending = session.send({ message: 'Question' })
  assert.equal(session.state.protection, null)
  await new Promise(resolve => setImmediate(resolve))
  session.setAccount(2)
  finishVerification({ protection: { content: { storage: 'encrypted' } } })
  assert.equal((await sending).ok, false)
  assert.equal(session.state.protection, null)
  assert.equal(session.state.messages.length, 0)
})

test('verification failure keeps completed response without claiming encrypted storage', async () => {
  const session = make({})({ userId: 1,
    apiClient: { protection: async () => { throw new Error('Unavailable') } },
    request: async () => ({ conversation_id: 5, responses: [{ content: 'Answer' }] }),
  })
  assert.equal((await session.send({ message: 'Question' })).ok, true)
  assert.equal(session.state.phase, 'complete')
  assert.equal(session.state.protection, null)
})
