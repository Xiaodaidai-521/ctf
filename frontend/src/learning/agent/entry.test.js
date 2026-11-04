import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import { openTutor, subscribeTutor } from './public.js'
import { setPageContext, requestTutorDrawer, closeTutorDrawer, resetTutorHost, tutorDrawerSnapshot } from './host.js'

const appSource = readFileSync(new URL('../../App.vue', import.meta.url), 'utf8')
const petSource = readFileSync(new URL('./TutorPet.vue', import.meta.url), 'utf8')
const platformPetSource = readFileSync(new URL('../../components/PlatformPet.vue', import.meta.url), 'utf8')
const hostSource = readFileSync(new URL('./components/TutorHost.vue', import.meta.url), 'utf8')
const drawerSource = readFileSync(new URL('./components/TutorDrawer.vue', import.meta.url), 'utf8')
const exam = page => /^\/exam-taking[^/]*/.test(page)

test('exam-taking preserves the pet but disables tutoring and keeps the drawer closed', () => {
  // 六期跨页保留宠物；正式测评继续禁止在宠物处问答，不破坏独立作答边界。
  assert.match(appSource, /<TutorPet v-if="user\.isAuthenticated"[^>]*:exam-page="examPage"/)
  assert.match(platformPetSource, /<form v-if="!examPage"/)
  assert.match(platformPetSource, /props\.session\.restoring \|\| props\.examPage\) return/)
  assert.match(appSource, /<TutorDrawer v-if="role === 'student' && !examPage"/)
  assert.match(appSource, /const examPage = computed\(\(\) => route\.path\.startsWith\('\/exam-taking'\)\)/)
  // 抽屉自身在路由进入答题页时也会关闭（防止从其他页带入）。
  assert.match(drawerSource, /path\.startsWith\('\/exam-taking'\)/)
  // 正式测评保留陪伴形象，但不开放教学问答或第二套助手。
  assert.equal(exam('/exam-taking/3'), true)
  assert.equal(exam('/exam-taking'), true)
  assert.equal(exam('/challenge/3'), false)
})

test('page, drawer and pet share one session controller instead of separate chats', () => {
  assert.match(hostSource, /import \{ agentSession, syncAgentAccount \}/)
  assert.match(hostSource, /session\.send\(\{ message: text, agentIds: \['tutor'\] \}\)/)
  assert.match(hostSource, /session\.reset\(\)/)
  assert.match(hostSource, /session\.cancelWaiting\(\)/)
  // 六期点击唤出本体，不跳页；发送与完整对话共用一个控制器。
  assert.match(platformPetSource, /function togglePet\(\) \{ pet\.setOpened/)
  assert.match(petSource, /agentSession\.send\(\{ message, agentIds: \['tutor'\] \}\)/)
  assert.match(petSource, /openTutor\(router, \{ userId: user\.userInfo\?\.id \}\)/)
  assert.doesNotMatch(petSource, /AIAssistant|AITutorChat|MultiAgentChat/)
})

test('challenge workspace: hint entry keeps the drawer with the current challenge reference only', async () => {
  resetTutorHost()
  setPageContext({ kind: 'challenge', id: 3, title: '授权练习', flag: 'flag{secret}', answer: 'x' })
  requestTutorDrawer()
  const snapshot = tutorDrawerSnapshot()
  assert.equal(snapshot.open, true)
  assert.deepEqual(
    { kind: snapshot.context.kind, ref: snapshot.context.ref, title: snapshot.context.title },
    { kind: 'challenge', ref: '3', title: '授权练习' },
  )
  assert.equal(Object.hasOwn(snapshot.context, 'flag'), false)
  assert.equal(Object.hasOwn(snapshot.context, 'answer'), false)
  closeTutorDrawer()
  assert.equal(tutorDrawerSnapshot().open, false)
})

test('openTutor keeps the public contract and hands a draft only to its owner', async () => {
  const pushes = []
  const router = {
    currentRoute: { value: { path: '/multi-agent' } },
    push: async path => { pushes.push(path) },
  }
  const { takeDraft } = await import('./draft.js')
  await openTutor(router, { prompt: '帮我梳理授权边界', userId: 7 })
  assert.deepEqual(pushes, ['/multi-agent?mode=learning'])
  assert.equal(takeDraft(7), '帮我梳理授权边界')
  assert.equal(takeDraft(8), '')
  assert.equal(typeof subscribeTutor, 'function')
})

test('composer submits once, is IME-safe and keeps Ctrl+Enter', () => {
  const composerSource = readFileSync(new URL('./components/TutorComposer.vue', import.meta.url), 'utf8')
  assert.match(composerSource, /@compositionstart="composing = true"/)
  assert.match(composerSource, /@compositionend="composing = false"/)
  assert.match(composerSource, /event\.isComposing \|\| composing\.value/)
  assert.match(composerSource, /\(event\.ctrlKey \|\| event\.metaKey\) && event\.key === 'Enter'/)
  assert.match(composerSource, /if \(!value \|\| props\.busy \|\| props\.disabled\) return/)
  assert.match(composerSource, /@submit\.prevent="submit"/)
})

test('session controller exposes cancel without claiming the backend stopped', () => {
  const controllerSource = readFileSync(new URL('./sessionController.js', import.meta.url), 'utf8')
  assert.match(controllerSource, /后台请求可能仍在处理/)
  assert.doesNotMatch(controllerSource, /已取消后台|已终止请求/)
})

test('tutor compositor modules are present and no page imports internal stores', () => {
  const names = [
    'TutorHost', 'TutorComposer', 'TutorDrawer', 'ExecutionStatus',
    'ConversationStream', 'AgentMessage', 'TeachingProgress', 'TeachingReportMessage',
    'ResourceReferences', 'ConversationActions',
  ]
  for (const name of names) {
    const source = readFileSync(new URL(`./components/${name}.vue`, import.meta.url), 'utf8')
    assert.ok(source.length > 100, `${name} exists`)
  }
  assert.match(readFileSync(new URL('./public.js', import.meta.url), 'utf8'), /export async function openTutor/)
})
