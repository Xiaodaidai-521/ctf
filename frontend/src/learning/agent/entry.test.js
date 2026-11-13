import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import { openTutor, subscribeTutor } from './public.js'
import { setPageContext, requestTutorDrawer, closeTutorDrawer, resetTutorHost, tutorDrawerSnapshot } from './host.js'

const appSource = readFileSync(new URL('../../App.vue', import.meta.url), 'utf8')
const hostSource = readFileSync(new URL('./components/TutorHost.vue', import.meta.url), 'utf8')
const drawerSource = readFileSync(new URL('./components/TutorDrawer.vue', import.meta.url), 'utf8')
const exam = page => /^\/exam-taking[^/]*/.test(page)

test('exam-taking disables the teaching drawer after pet removal', () => {
  assert.doesNotMatch(appSource, /<TutorPet|usePetStore/)
  assert.match(appSource, /<TutorDrawer v-if="role === 'student' && !examPage"/)
  assert.match(appSource, /const examPage = computed\(\(\) => route\.path\.startsWith\('\/exam-taking'\)\)/)
  // 抽屉自身在路由进入答题页时也会关闭（防止从其他页带入）。
  assert.match(drawerSource, /path\.startsWith\('\/exam-taking'\)/)
  // 正式测评不开放教学问答或第二套助手。
  assert.equal(exam('/exam-taking/3'), true)
  assert.equal(exam('/exam-taking'), true)
  assert.equal(exam('/challenge/3'), false)
})

test('page and drawer retain the shared session controller', () => {
  assert.match(hostSource, /import \{ agentSession, syncAgentAccount \}/)
  assert.match(hostSource, /session\.send\(\{ message: text, agentIds: \['tutor'\] \}\)/)
  assert.match(hostSource, /session\.reset\(\)/)
  assert.match(hostSource, /session\.cancelWaiting\(\)/)
  assert.match(appSource, /signOutAgent\(\)/)
  assert.match(appSource, /syncAgentAccount\(user\.userInfo\?\.id\)/)
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
