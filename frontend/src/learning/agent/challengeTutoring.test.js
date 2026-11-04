import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import { challengeSwitchNote, taskBindingFrom, tutoringPolicy } from './tutoring.js'
import { resetLifecycle, trackRequest } from './lifecycle.js'

const plain = value => JSON.parse(JSON.stringify(value))
const read = path => readFileSync(new URL(path, import.meta.url), 'utf8')
const hostSource = read('./components/TutorHost.vue')
const guideSource = read('./components/ChallengeTutoringGuide.vue')
const drawerSource = read('./components/TutorDrawer.vue')
const bodySource = read('../practice/components/ChallengeBody.vue')
const workspaceSource = read('../practice/ChallengeWorkspace.vue')

function loadController() {
  const contextSource = read('./context.js')
    .replace(/^export function /gm, 'function ')
  const sanitizeContext = vm.runInNewContext(`${contextSource}\n;sanitizeContext`, {})
  const apiSource = read('./api.js').replace(/^import .*$/gm, '')
  const host = vm.runInNewContext(apiSource
    .replace(/^export const /gm, 'const ')
    .replace(/^export function /gm, 'function ')
    .replace(/^export \{.*\}$/gm, '') + '\n;({ conversationMessages, restorableConversation })', {})
  const controllerSource = read('./sessionController.js')
    .replace(/^import .*$/gm, '')
    .replace('export function createSessionController', 'function createSessionController')
  const make = sandbox => vm.runInNewContext(`${controllerSource}\n;createSessionController`, {
    conversationMessages: host.conversationMessages,
    restorableConversation: host.restorableConversation,
    sanitizeContext, ...sandbox,
  })
  return { make, sanitizeContext }
}

test('challenge tutoring names the target and keeps author hints separate from agent tiers', () => {
  const policy = tutoringPolicy({
    context: { kind: 'challenge', ref: '41', title: '边界检查' },
    metadata: null,
    authorHint: true,
  })
  assert.equal(policy.isChallenge, true)
  assert.equal(policy.target, '当前题目：边界检查')
  assert.equal(policy.authorHint.available, true)
  assert.equal(policy.authorHint.label, '题目作者公开提示')
  assert.match(policy.authorHint.note, /不是智能体已解锁的下一层/)
  // 后台没给层级时既不显示第 1 层，也不画成已解锁。
  assert.equal(policy.level, null)
  assert.deepEqual(policy.tiers.map(tier => tier.state), ['policy', 'policy', 'policy', 'policy'])
  assert.match(policy.levelLabel, /后台未返回当前提示层级/)
  assert.equal(policy.canRequestLevel, false)
  assert.equal(policy.autoAdvance, false)
  assert.equal(policy.fullAnswer, false)
  assert.match(policy.note, /不提供“完整答案”开关/)
})

test('a real task binding level is shown, and no level exists without attempt association', () => {
  const bound = tutoringPolicy({
    context: { kind: 'challenge', ref: '41', title: '边界检查' },
    metadata: { taskBinding: { attemptId: '9f1c', runId: 'run-1', hintLevel: 2 } },
    authorHint: false,
  })
  assert.equal(bound.level, 2)
  assert.match(bound.levelLabel, /第 2 级/)
  assert.deepEqual(bound.tiers.map(tier => tier.state), ['available', 'available', 'later', 'later'])
  assert.equal(bound.authorHint.available, false)

  // 只有题目 id 或难度不是任务关联；越界层级也不照搬。
  assert.deepEqual(plain(taskBindingFrom({ taskBinding: { challengeId: 41, hintLevel: 3 } })), {
    available: false, hintLevel: 3, attemptId: null, runId: null,
  })
  assert.equal(taskBindingFrom({ taskBinding: { hintLevel: 9 } }).hintLevel, null)
  assert.equal(taskBindingFrom(null).hintLevel, null)
  const unbound = tutoringPolicy({ context: { kind: 'challenge', ref: '41', title: '题' }, metadata: { taskBinding: { hintLevel: 3 } } })
  assert.equal(unbound.level, 3)
  assert.match(unbound.note, /不会自动连续请求下一层/)
})

test('non-challenge contexts do not claim a tutoring target', () => {
  const policy = tutoringPolicy({ context: { kind: 'path', ref: '2', title: 'Web 基础' }, authorHint: true })
  assert.equal(policy.isChallenge, false)
  assert.equal(policy.target, '')
  assert.equal(policy.authorHint.available, true)
})

test('switching challenges states the boundary instead of silently merging threads', () => {
  const previous = { kind: 'challenge', ref: '41', title: '边界检查' }
  assert.equal(challengeSwitchNote(previous, { kind: 'challenge', ref: '41', title: '换名' }), '')
  assert.equal(challengeSwitchNote(previous, { kind: 'path', ref: '1', title: '航线' }), '')
  assert.equal(challengeSwitchNote(previous, { kind: 'challenge', ref: '42', title: '输入过滤' }), '已切换到《输入过滤》，辅导从这道题重新开始。')
})

test('the context keeps the challenge reference and author-hint marker, never the flag', () => {
  const { sanitizeContext } = loadController()
  const context = sanitizeContext({
    kind: 'challenge', id: 41, title: '边界检查', authorHint: true,
    flag: 'flag{secret}', answer: 'x', description: '题面正文',
  })
  assert.deepEqual(plain(context), { kind: 'challenge', ref: '41', title: '边界检查', reason: '', authorHint: true })
  assert.equal(Object.hasOwn(context, 'flag'), false)
  assert.equal(Object.hasOwn(context, 'description'), false)
  assert.equal(sanitizeContext({ kind: 'challenge', ref: 1, authorHint: 'yes' }).authorHint, undefined)
})

test('the controller keeps real response metadata and drops it on reset or account switch', async () => {
  const { make } = loadController()
  const session = make({})({
    userId: 1,
    apiClient: { conversations: async () => [], conversation: async () => ({}), removeConversation: async () => {} },
    request: async () => ({
      conversation_id: 5,
      metadata: { taskBinding: { attemptId: 'attempt-1', hintLevel: 2 } },
      responses: [{ content: '先说说你的尝试。' }],
    }),
  })
  await session.send({ message: '卡住了' })
  assert.equal(JSON.parse(JSON.stringify(session.state.metadata)).taskBinding.hintLevel, 2)
  await session.reset()
  assert.equal(session.state.metadata, null)
  await session.send({ message: '再问' })
  assert.ok(session.state.metadata)
  session.setAccount(2)
  assert.equal(session.state.metadata, null)
})

test('challenge page opens the same drawer for hint and pet entries, with no auto question', () => {
  // 题面入口与侧栏入口都落到同一个 askTutor，而不是跳页重建聊天。
  assert.match(bodySource, /请给一点提示/)
  assert.match(bodySource, /\$emit\('ask-tutor'\)/)
  assert.match(workspaceSource, /@ask-tutor="askTutor"/)
  assert.match(workspaceSource, /requestTutorDrawer\(\)/)
  assert.match(drawerSource, /TutorHost mode="drawer"/)
  assert.match(hostSource, /session\.send\(\{ message: text, agentIds: \['tutor'\] \}\)/)
  // 打开抽屉只同步上下文并聚焦输入框，不自动提交问题或连续请求提示。
  const mounted = hostSource.slice(hostSource.indexOf('onMounted('), hostSource.indexOf('onBeforeUnmount('))
  assert.doesNotMatch(mounted, /submit\(|quickPrompt\(|session\.send/)
  assert.match(mounted, /composerRef\.value\?\.focus\(\)/)
})

test('drawer shows the tier guide, one manual hint action, and no full-answer control', () => {
  assert.match(hostSource, /<ChallengeTutoringGuide v-if="challengeContext"/)
  assert.match(hostSource, /tutoringPolicy\(\{ context: context\.value, metadata: metadata\.value/)
  assert.match(hostSource, /label: '请给一点提示'/)
  // 只有一个快捷动作，且是普通问题；没有“完整答案”按钮或自动逐层推进。
  assert.equal((hostSource.match(/label: '请给一点提示'/g) || []).length, 1)
  assert.doesNotMatch(hostSource, /给完整答案|完整解法开关:/)
  assert.doesNotMatch(guideSource, /<button/)
  // 普通题对话不调用需要真实 attempt UUID 的任务提示接口。
  assert.doesNotMatch(hostSource, /hints\/|teaching\/runs|attempt_id\s*=\s*challenge/i)
})

test('challenge questions still use the teaching chain with the challenge reference only', async () => {
  resetLifecycle()
  const source = read('./request.js').replace(/^import .*$/gm, '').replace('export function', 'function')
  let sent
  const request = vm.runInNewContext(`${source}\n;requestTeaching`, {
    api: {}, http: { post: async (url, payload) => { sent = { url, payload: plain(payload) }; return {} } },
    trackRequest, tutorResourceListFromResponse: () => [],
  })
  await request({
    agentIds: ['local'], message: '先说说思路', challengeId: 41, conversationId: 7,
    mode: 'learning', knowledgeScope: 'all', model: { id: 'default', provider: '' },
  })
  assert.equal(sent.url, '/ai/multi-agent/chat/')
  assert.equal(sent.payload.mode, 'challenge_solution')
  assert.equal(sent.payload.challenge_id, 41)
  assert.equal(sent.payload.knowledge_scope, 'current')
  assert.equal(Object.hasOwn(sent.payload, 'flag'), false)
})
