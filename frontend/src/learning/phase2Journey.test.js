import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { openTutor } from './agent/public.js'
import { clearDraft, queueDraft, takeDraft } from './agent/draft.js'
import {
  clearPageContext, closeTutorDrawer, requestTutorDrawer, resetTutorHost, setPageContext,
  tutorDrawerSnapshot,
} from './agent/host.js'
import { modulePosition } from './paths/moduleLearning.js'
import { nextStepView } from './paths/presentation.js'
import { growthDestination, parseGrowthSection, shouldKeepAlive } from '../shared/navigation/phase2.js'
import { landingFor } from '../shared/navigation/names.js'
import { guardDestination } from '../shared/navigation/access.js'
import { growthSectionTarget, growthWindow } from './growth/sections.js'

const routerSource = readFileSync(new URL('../router/index.js', import.meta.url), 'utf8')
const appSource = readFileSync(new URL('../App.vue', import.meta.url), 'utf8')
const runtimeSource = readFileSync(new URL('./agent/runtime.js', import.meta.url), 'utf8')
const examSource = readFileSync(new URL('./exams/api.js', import.meta.url), 'utf8')
const capabilitySource = readFileSync(new URL('../views/LearningMap/CapabilityMap.vue', import.meta.url), 'utf8')

const modules = [
  { id: 2, title: '授权范围确认', module_type: 'theory', estimated_minutes: 20 },
  { id: 3, title: '证据链核对', module_type: 'practice', estimated_minutes: 30 },
]

test('one student journey keeps every stop on a real route and hands context forward', async () => {
  resetTutorHost()
  clearDraft()

  // 智航：统一对话入口，旧 mode 参数只用于兼容，不携带学生配置。
  const pushes = []
  const router = {
    push: async value => { pushes.push(value) },
    currentRoute: { value: { path: '/multi-agent' } },
  }
  await openTutor(router, { prompt: '', userId: 7 })
  assert.deepEqual(pushes, ['/multi-agent?mode=learning'])

  // 选航线 → 章节：下一步只认后端 current_module，并给出可进入的真实章节地址。
  const record = {
    learning_path: 1, path_title: 'Web 安全入门', current_module: 2,
    completed_modules: 1, total_modules: 2, completed_labs: 0, total_labs: 2,
    progress_percentage: 50,
  }
  const step = nextStepView(record, modules, 1)
  assert.equal(step.joined, true)
  assert.equal(step.chapterKnown, true)
  assert.equal(step.canEnter, true)
  assert.equal(step.to, '/learning-paths/1/modules/2')
  assert.match(step.note, /由你在章节页操作/)

  const position = modulePosition(2, modules, 1)
  assert.equal(position.label, '第 1 / 2 章')
  assert.equal(position.next.to, '/learning-paths/1/modules/3')
  assert.equal(position.previous, null)

  // 靶场题目 → 抽屉问：题目引用进入同一会话，不另建一套聊天。
  setPageContext({ kind: 'challenge', ref: 42, title: '注入判断', reason: '当前正在练习的题目' })
  requestTutorDrawer()
  const drawer = tutorDrawerSnapshot()
  assert.equal(drawer.open, true)
  assert.equal(drawer.context.kind, 'challenge')
  assert.equal(String(drawer.context.ref), '42')
  queueDraft('请给一点提示，不要直接给答案', 7)
  assert.equal(takeDraft(7), '请给一点提示，不要直接给答案')
  assert.equal(takeDraft(8), '', '换账号后不能取到上一账号的草稿')
  closeTutorDrawer()
  clearPageContext(42)
  assert.equal(tutorDrawerSnapshot().open, false)
  assert.equal(tutorDrawerSnapshot().context, null)

  // 继续导学：下一步仍可进入后台记录的当前章节。
  assert.equal(nextStepView(record, modules, 1).to, '/learning-paths/1/modules/2')

  // 试炼记录到成长复盘：记录区 URL 与筛选可刷新、可分享。
  assert.match(examSource, /export const RECORDS_PATH = '\/exam-center\/history'/)
  assert.match(examSource, /export function parseRecordQuery/)
  assert.match(routerSource, /path: '\/exam-center\/history'[\s\S]*?name: 'ExamHistory'/)
  assert.match(routerSource, /path: '\/exam-center\/result\/:id'[\s\S]*?name: 'ExamResult'/)
  assert.equal(growthDestination('results'), '/dashboard?section=results')
  assert.equal(growthSectionTarget('results'), 'growth-results')

  // 能力探索：仍是独立可达页面。
  assert.match(routerSource, /path: '\/capability-map'[\s\S]*?name: 'CapabilityMap'/)
  assert.match(capabilitySource, /CapabilityMap|capability/i)
})

test('back, forward, refresh and bookmarks restore the same student destinations', () => {
  // 成长分区/时间窗：同一 query 语义可重复解析，刷新与前进后退不丢分区。
  for (const query of [{ section: 'activity', window: '30' }, { section: 'results' }, { section: 'capability' }]) {
    const href = growthDestination(query.section, query)
    const search = href.split('?')[1] || ''
    const params = new URLSearchParams(search)
    assert.equal(parseGrowthSection(params.get('section')), query.section)
    if (query.window) {
      assert.equal(params.get('window'), query.window)
      assert.equal(growthWindow(query.window), 30)
    }
  }
  assert.equal(parseGrowthSection('unknown'), 'overview')
  assert.equal(growthWindow('bad'), null)

  // 书签直达：个人画像区、资源推荐高亮、航线筛选与章节地址都由 URL 承载。
  const profileSource = readFileSync(new URL('../views/Profile.vue', import.meta.url), 'utf8')
  const resourcesSource = readFileSync(new URL('../views/Resources.vue', import.meta.url), 'utf8')
  const pathsSource = readFileSync(new URL('../views/LearningPaths/LearningPathsList.vue', import.meta.url), 'utf8')
  assert.match(profileSource, /route\.query\.tab/)
  assert.match(resourcesSource, /route\.query\.highlight_resource/)
  assert.match(resourcesSource, /route\.query\.highlight_resources/)
  assert.match(pathsSource, /route\.query\.search/)
  assert.match(pathsSource, /route\.query\.difficulty/)
  assert.match(routerSource, /path: '\/learning-paths\/:pathId\/modules\/:moduleId'/)

  // 局部保活白名单不吞未提交 Flag、考试答案或任务证据。
  for (const name of ['Challenges', 'LearningPaths', 'ExamHistory', 'StudentDashboard']) {
    assert.equal(shouldKeepAlive(name), true)
  }
  for (const name of ['ExamTaking', 'LearningKnowledge', 'GeneratedContent', 'ModuleLearning']) {
    assert.equal(shouldKeepAlive(name), false)
  }
})

test('account swaps clear agent host and drafts before the next role lands', () => {
  resetTutorHost()
  setPageContext({ kind: 'challenge', ref: 42, title: '旧账号题目' })
  requestTutorDrawer()
  queueDraft('旧账号草稿', 7)
  resetTutorHost()
  clearDraft()
  assert.deepEqual(tutorDrawerSnapshot(), { open: false, context: null })
  assert.equal(takeDraft(7), '')
  assert.equal(takeDraft(8), '')

  assert.match(runtimeSource, /resetTutorHost\(\)/)
  assert.match(runtimeSource, /clearDraft\(\)/)
  assert.match(appSource, /watch\(\(\) => \[user\.userInfo\?\.id, role\.value\]/)
  assert.match(appSource, /syncAgentAccount|signOutAgent/)
  assert.match(appSource, /:key="`\$\{user\.userInfo\?\.id \|\| 'guest'\}:\$\{role\}`"/)
})

test('teacher and admin keep their own landing and cannot fall into student growth by/bookmark', () => {
  assert.equal(landingFor('teacher'), '/teacher')
  assert.equal(landingFor('admin'), '/admin/dashboard')
  const teacher = { isAuthenticated: true, userInfo: { role: 'teacher' } }
  const admin = { isAuthenticated: true, userInfo: { role: 'admin' } }
  const student = { isAuthenticated: true, userInfo: { role: 'student' } }
  assert.equal(guardDestination({ path: '/dashboard', name: 'StudentDashboard', meta: { requiresAuth: true } }, teacher), undefined)
  assert.equal(guardDestination({ path: '/dashboard', name: 'StudentDashboard', meta: { requiresAuth: true } }, admin), '/admin/dashboard')
  assert.equal(guardDestination({ path: '/guide', name: 'Guide', meta: { requiresAuth: true } }, teacher), '/teacher')
  assert.equal(guardDestination({ path: '/guide', name: 'Guide', meta: { requiresAuth: true } }, admin), '/admin/dashboard')
  assert.equal(guardDestination({ path: '/capability-map', name: 'CapabilityMap', meta: { requiresAuth: true } }, student), undefined)
  assert.match(routerSource, /path: '\/access-denied'/)
  assert.match(routerSource, /path: '\/:pathMatch\(\.\*\)\*'[\s\S]*?name: 'NotFound'/)
})
