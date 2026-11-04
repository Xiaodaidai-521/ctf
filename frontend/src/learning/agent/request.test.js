import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import { trackRequest, resetLifecycle } from './lifecycle.js'

function adapter(api, http = {}) {
  const source = readFileSync(new URL('./request.js', import.meta.url), 'utf8')
    .replace(/^import .*$/gm, '').replace('export function', 'function')
  return vm.runInNewContext(`${source}\n;requestTeaching`, {
    api, http, trackRequest, tutorResourceListFromResponse: data => data.resourceList || [],
  })
}
const plain = value => JSON.parse(JSON.stringify(value))

test('tutoring adapter preserves the teaching contract without persisting response resources', async () => {
  resetLifecycle()
  let payload
  const resources = [{ id: 3, title: '授权学习资料' }]
  const request = adapter({
    studentProfile: { get: async () => ({ preference: { difficulty_bias: 0.5 } }) },
    learningAgent: { tutoring: async body => {
      payload = plain(body)
      return { conversation_id: 7, resourceList: resources, noMatchedResource: false, steps: [
        { step: 1, step_name: '评估', content: '先检查理解。' },
        { step: 2, step_name: '讲解', content: '再梳理原理。' },
        { step: 3, step_name: '练习', content: '请独立尝试。' },
        { step: 4, step_name: '检验', content: '检验掌握。' },
      ] }
    } },
  })
  // No storage or remember helper is provided: only the current renderer may persist resources.
  const result = await request({ agentIds: ['tutor'], message: '学习问题', activeAgent: { id: 'tutor', name: '教学辅导师' }, conversationId: 7, model: { id: 'existing-model', provider: 'existing-provider' } })
  assert.deepEqual(payload, { concept_name: '学习问题', question: '学习问题', student_level: 'advanced', conversation_id: 7, selected_model: 'existing-model', selected_provider: 'existing-provider' })
  assert.equal(result.resources, resources)
  assert.equal(result.conversation_id, 7)
  assert.deepEqual(plain(result.responses.map(step => step.step)), [1, 2, 3, 4])
})

test('non-tutor collaboration preserves specialist selection and challenge scope', async () => {
  let sent
  const request = adapter({}, { post: async (url, payload) => { sent = { url, payload: plain(payload) }; return 'response' } })
  const result = await request({ agentIds: ['local', 'legal'], message: '问题', challengeId: 9, conversationId: 7, forceAI: true, mode: 'custom', knowledgeScope: 'all', model: { id: 'existing-model', provider: 'existing-provider' } })
  assert.equal(result, 'response')
  assert.deepEqual(sent, { url: '/ai/multi-agent/chat/', payload: { message: '问题', agent_ids: ['local', 'legal'], mode: 'challenge_solution', challenge_id: 9, force_ai: true, conversation_id: 7, selected_model: 'existing-model', selected_provider: 'existing-provider', knowledge_scope: 'current' } })
})
