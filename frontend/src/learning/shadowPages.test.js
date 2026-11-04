import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { randomUUID } from 'node:crypto'
import * as Vue from 'vue'
import { parse, compileScript, compileTemplate } from 'vue/compiler-sfc'
import { renderToString } from 'vue/server-renderer'
import { createRouter, createMemoryHistory } from 'vue-router'
import { canOpen, guardDestination, pageTitle } from '../shared/navigation/access.js'
import { compatDestination } from '../shared/navigation/phase2.js'
import { teachingDestination, feedbackCandidateDestination } from '../shared/navigation/phase3.js'
import { shadowDestination, wantsCapabilityHistory, DATA_SECURITY_TOPIC, CAPABILITY_HISTORY } from './shadowRoutes.js'
import * as capabilityPresentation from './capability/presentation.js'
const { changelogViews } = capabilityPresentation
import { readableError } from '../views/DataLab/errors.js'
import { splitCodepoints } from '../views/DataLab/codepoints.js'
import { currentReplays, latestRevealedReplays, replayVariants } from '../views/DataLab/replaySelection.js'

const read = path => readFileSync(new URL(path, import.meta.url), 'utf8')
const plain = value => JSON.parse(JSON.stringify(value))
const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no }); return { promise, resolve, reject } }
const settle = async () => { for (let i = 0; i < 20; i++) await Promise.resolve(); await Vue.nextTick() }

function routerFor(role) {
  const source = read('../router/index.js').trimStart().replace(/^import .*$/gm, '').replace(/component: \(\) => import\([^\n]+?\)/g, 'component: {}').replace('export default router', 'router')
  const user = { isAuthenticated: role !== 'guest', userInfo: { id: 1, role } }
  return runInNewContext(source, {
    createRouter, createWebHistory: createMemoryHistory, useUserStore: () => user, document: {},
    TeacherLayout: {}, TeacherDashboard: {}, LearningEffectAnalysis: {},
    guardDestination, pageTitle, compatDestination, teachingDestination, feedbackCandidateDestination, shadowDestination,
  })
}

for (const role of ['student', 'teacher', 'admin']) {
  test(`shadow compatibility: ${role} retains attempt, all query values and hash`, async () => {
    const router = routerFor(role)
    await router.push('/data-lab?attempt=owned-attempt&tag=a&tag=b#task')
    assert.equal(router.currentRoute.value.path, DATA_SECURITY_TOPIC)
    assert.deepEqual(plain(router.currentRoute.value.query), { attempt: 'owned-attempt', tag: ['a', 'b'] })
    assert.equal(router.currentRoute.value.hash, '#task')
    assert.equal(router.currentRoute.value.name, 'DataLab')
    assert.equal(router.currentRoute.value.meta.sensitive, true)
  })
}
for (const [role, expected] of [['guest', '/login'], ['student', '/access-denied'], ['teacher', '/teacher/data-cases'], ['admin', '/admin/data-cases']]) {
  test(`old case management role compatibility: ${role}`, async () => {
    const router = routerFor(role)
    await router.push('/data-lab/teacher?case=owned-case&focus=help#attempts')
    assert.equal(router.currentRoute.value.path, expected)
    if (role === 'teacher' || role === 'admin') {
      assert.deepEqual(plain(router.currentRoute.value.query), { case: 'owned-case', focus: 'help' })
      assert.equal(router.currentRoute.value.hash, '#attempts')
      assert.equal(router.currentRoute.value.meta.sensitive, true)
    }
  })
}
test('case management canonical routes never cross teacher/admin layouts', async () => {
  for (const [role, path] of [['student', '/teacher/data-cases'], ['student', '/admin/data-cases'], ['teacher', '/admin/data-cases'], ['admin', '/teacher/data-cases']]) {
    const router = routerFor(role)
    await router.push(path)
    assert.equal(router.currentRoute.value.path, '/access-denied')
  }
  assert.match(read('../shared/layout/AccessDenied.vue'), /当前账号暂无访问权限/)
  assert.match(read('../shared/layout/AccessDenied.vue'), /学习资料可在智库查找/)
})
test('guest topic access requires login; old history redirects to inline history, not teacher audit', async () => {
  const guest = routerFor('guest')
  await guest.push('/data-lab?attempt=a')
  assert.equal(guest.currentRoute.value.path, '/login')
  for (const role of ['student', 'teacher', 'admin']) {
    const router = routerFor(role)
    await router.push('/capability-map/changelog?version=course-a&student=other')
    assert.equal(router.currentRoute.value.path, '/capability-map')
    assert.equal(router.currentRoute.value.query.version, 'course-a')
    assert.equal(router.currentRoute.value.query.history, '1')
    assert.equal(router.currentRoute.value.hash, '#capability-history')
  }
})
test('compat planning leaves input untouched and does not reinterpret student identity', () => {
  const query = Object.freeze({ attempt: 'a', student: 'other', history: '0' })
  const to = Object.freeze({ path: '/capability-map/changelog/', query })
  assert.deepEqual(shadowDestination(to, 'student'), { path: '/capability-map', query: { ...query, history: '1' }, hash: '#capability-history' })
  assert.equal(query.history, '0')
  assert.equal(shadowDestination({ path: '/unknown' }, 'student'), null)
  assert.equal(wantsCapabilityHistory({ query: { history: '1' } }), true)
  assert.equal(wantsCapabilityHistory({ hash: '#capability-history' }), true)
  assert.equal(wantsCapabilityHistory({ query: { history: ['1'] } }), false)
})

function setup(file, bindings, expose) {
  const source = parse(read(file)).descriptor.scriptSetup.content.replace(/import\s+[\s\S]*?\s+from\s+['"][^'"]+['"];?/g, '')
  const mounts = [], unmounts = [], scope = Vue.effectScope()
  const page = scope.run(() => runInNewContext(`${source}\n;({${expose}})`, {
    ...Vue, onMounted: fn => mounts.push(fn), onBeforeUnmount: fn => unmounts.push(fn),
    crypto: { randomUUID }, document: { getElementById: () => null }, ...bindings,
  }))
  return { page, mount: async () => { for (const fn of mounts) await fn(); await settle() }, destroy: () => { for (const fn of unmounts) fn(); scope.stop() } }
}
const sourceFiles = ['../views/DataLab/DataLab.vue', '../views/DataLab/DataLabTeacher.vue', '../views/LearningMap/CapabilityMap.vue', '../views/LearningMap/ChangeLog.vue', '../teacher/CapabilityMapAdmin.vue', '../views/Resources.vue', '../shared/learning/CapabilityHistoryTable.vue']
for (const file of sourceFiles) {
  test(`shadow receiving component compiles: ${file}`, () => {
    const { descriptor, errors } = parse(read(file))
    assert.deepEqual(errors, [])
    const script = compileScript(descriptor, { id: 'shadow-pages' })
    assert.deepEqual(compileTemplate({ source: descriptor.template.content, filename: file, id: 'shadow-pages', compilerOptions: { bindingMetadata: script.bindings } }).errors, [])
  })
}
test('student topic retains all five steps, original write actions, replays and four help levels', () => {
  const source = read('../views/DataLab/DataLab.vue')
  assert.match(source, /const steps = \['任务简介', '依据与事实', '发现与复核', '四轮回放', '提交与结果'\]/)
  for (const fn of ['claim', 'resume', 'saveBasis', 'identify', 'saveReview', 'replay', 'judge', 'submit', 'showSubmission', 'showAnalysis', 'hint']) assert.match(source, new RegExp(`async function ${fn}\\(`))
  for (const action of ['confirm', 'correct', 'false_positive', 'add_manual']) assert.ok(source.includes(action))
  for (const feature of ['teacher_example', 'basis_cards', 'review_history', 'missingVariants', 'expected_revision', 'expected_state_version', 'idempotency_key', 'replay_ids', 'independence', 'v-for="level in 4"']) assert.ok(source.includes(feature), feature)
  assert.match(source, /if \(missingVariants.value.length\) throw/)
  assert.match(source, /help\/\$\{requestId\}\/display/)
  assert.match(read('../views/Resources.vue'), /to="\/resources\/topics\/data-security"/)
  assert.match(source, /返回\{\{ names.resources \}\}/)
  assert.match(read('../views/DataLab/api.js'), /const root = '\/data-lab\/'/)
})
test('student topic clears private state and blocks old index responses on account change/unmount', async () => {
  const first = deferred(), route = Vue.reactive({ query: {}, hash: '' }), user = Vue.reactive({ userInfo: { id: 1, role: 'student' } })
  let reads = 0
  const h = setup('../views/DataLab/DataLab.vue', {
    useRoute: () => route, useRouter: () => ({ replace: value => { route.query = value.query; return Promise.resolve() } }), useUserStore: () => user,
    labApi: { get: () => ++reads === 1 ? first.promise : Promise.resolve({ cases: [], attempts: [] }) },
    splitCodepoints, readableError, currentReplays, latestRevealedReplays, replayVariants,
  }, 'loadIndex, state, cases, attempts, basis, predictions, pending, pendingHelp, resetAttempt')
  const loading = h.page.loadIndex()
  h.page.state.value = { material: 'private' }; h.page.basis.entity_category = 'private'; h.page.predictions.secret = 'private'
  h.page.pending.set('private', 'key'); h.page.pendingHelp.set(1, 'private')
  user.userInfo = { id: 2, role: 'student' }
  await settle()
  first.resolve({ cases: [{ task_key: 'old-private' }], attempts: [{ attempt_id: 'old' }] })
  await loading
  assert.equal(h.page.state.value, null)
  assert.equal(h.page.basis.entity_category, '')
  assert.deepEqual(Object.keys(h.page.predictions), [])
  assert.equal(h.page.pending.size, 0); assert.equal(h.page.pendingHelp.size, 0)
  assert.deepEqual(plain(h.page.cases.value), [])
  h.destroy()
  await h.page.loadIndex()
  assert.equal(reads, 2)
})
test('inline student history reads only me, preserves every record, clears stale identities and uses human errors', async () => {
  const first = deferred(), calls = [], route = Vue.reactive({ query: { version: 'a', student: 'other' } }), user = Vue.reactive({ userInfo: { id: 1, role: 'student' } })
  const all = Array.from({ length: 120 }, (_, i) => ({ capability_title: `能力${i}`, from_state_label: '待诊断', to_state_label: '受助通过', reason_label: '平台核验', created_at: '2026-11-03T02:00:00Z' }))
  const h = setup('../views/LearningMap/ChangeLog.vue', {
    useRoute: () => route, useUserStore: () => user, changelogViews,
    capabilityApi: { changelog: params => { calls.push(params); return calls.length === 1 ? first.promise : Promise.resolve({ items: all }) } },
  }, 'rows, error, load')
  user.userInfo = { id: 2, role: 'student' }
  await settle()
  first.resolve({ items: [{ capability_title: 'old-private' }] }); await settle()
  assert.equal(h.page.rows.value.length, 120)
  assert.equal(h.page.rows.value.at(-1).title, '能力119')
  assert.deepEqual(plain(calls), [{ version: 'a' }, { version: 'a' }])
  h.destroy()
  assert.deepEqual(plain(h.page.rows.value), [])
  const rejected = setup('../views/LearningMap/ChangeLog.vue', {
    useRoute: () => route, useUserStore: () => user, changelogViews,
    capabilityApi: { changelog: async () => { throw { response: { status: 403, data: '<html>INTERNAL</html>' } } } },
  }, 'rows, error, load')
  await settle()
  assert.match(rejected.page.error.value, /无权查看/)
  assert.doesNotMatch(rejected.page.error.value, /html|INTERNAL/)
  rejected.destroy()
})
test('teacher history remains selected-student state history and does not show a previous student after failure', async () => {
  const old = deferred(), user = Vue.reactive({ userInfo: { id: 10, role: 'teacher' } }), route = Vue.reactive({ query: {}, hash: '' }), calls = []
  const service = { learningMap: {
    studentMap: id => id === 1 ? old.promise : Promise.resolve({ student: { id, username: '乙' }, catalog: {}, tracks: [] }),
    studentRecommendations: async () => ({ items: [], gaps: [] }),
    studentChangelog: async (id, params) => { calls.push({ id, params }); return { items: [{ capability_title: '授权判断', from_state: 'assisted_pass', to_state: 'independent', reason: 'retest_independent_pass', created_at: '2026-11-03' }] } },
  } }
  const h = setup('../teacher/CapabilityMapAdmin.vue', { service, useRoute: () => route, useUserStore: () => user, configurationVersionLabel: value => value }, 'studentId, loadStudent, studentMap, changelog, historyRows, studentError')
  h.page.studentId.value = '1'; const firstRead = h.page.loadStudent()
  h.page.studentId.value = '2'; await h.page.loadStudent()
  old.resolve({ student: { id: 1, username: '甲' } }); await firstRead
  assert.equal(h.page.studentMap.value.student.id, 2)
  assert.equal(h.page.historyRows.value[0].title, '授权判断')
  assert.equal(h.page.historyRows.value[0].from, '受助通过')
  assert.equal(h.page.historyRows.value[0].to, '已有独立证据')
  assert.equal(h.page.historyRows.value[0].reason, '复测独立通过')
  assert.deepEqual(calls.map(call => call.id), [1, 2])
  service.learningMap.studentChangelog = async () => { throw { response: { status: 403 } } }
  h.page.studentId.value = '3'; await h.page.loadStudent()
  assert.equal(h.page.studentMap.value, null)
  assert.deepEqual(plain(h.page.changelog.value), [])
  assert.match(h.page.studentError.value, /无权/)
  h.destroy()
})
test('capability explorer opens lazy inline history from both query and anchor without hiding exploration', async () => {
  for (const entry of [{ query: {}, hash: '' }, { query: { history: '1' }, hash: '' }, { query: {}, hash: '#capability-history' }]) {
    const route = Vue.reactive(entry), user = { userInfo: { id: 1, role: 'student' } }, scrolls = []
    const h = setup('../views/LearningMap/CapabilityMap.vue', {
      ...capabilityPresentation, CAPABILITY_HISTORY, wantsCapabilityHistory, useRoute: () => route, useUserStore: () => user, service: {},
      window: { innerWidth: 1440, addEventListener() {}, removeEventListener() {} },
    }, 'historyOpen, historyVisited, historySection, openHistory')
    await settle()
    assert.equal(h.page.historyOpen.value, wantsCapabilityHistory(entry))
    h.page.historySection.value = { scrollIntoView: value => scrolls.push(value) }
    await h.page.openHistory()
    assert.equal(h.page.historyVisited.value, true)
    assert.equal(h.page.historyOpen.value, true)
    assert.equal(scrolls.length, 1)
    h.page.historyOpen.value = false
    assert.equal(h.page.historyVisited.value, true)
    h.destroy()
  }
  const template = parse(read('../views/LearningMap/CapabilityMap.vue')).descriptor.template.content
  for (const component of ['CapabilityExplorer', 'CapabilityDetail', 'CapabilityTaskList']) assert.ok(template.includes(`<${component}`))
})
test('case management retains supervision and help registration while clearing a late private case response', async () => {
  const old = deferred(), user = Vue.reactive({ userInfo: { id: 10, role: 'admin' } }), route = Vue.reactive({ query: { case: 'own-case' }, hash: '' })
  let reads = 0
  const h = setup('../views/DataLab/DataLabTeacher.vue', {
    useRoute: () => route, useUserStore: () => user, readableError,
    api: { analytics: { teacherStudentReport: async () => [] } },
    teacherLabApi: {
      cases: async () => ({ cases: [{ task_key: 'own-case', title: '案例' }] }),
      caseDetail: () => ++reads === 1 ? old.promise : Promise.resolve({ material: { title: '新账号案例' }, status: 'published', paused: false, withdrawn: false, attempts: [] }),
    },
  }, 'loadCases, detail, attempts, helpForm, pending, isAdmin')
  const loading = h.page.loadCases()
  await settle()
  h.page.helpForm.summary = 'private help'; h.page.pending.set('private', 'key')
  user.userInfo = { id: 11, role: 'teacher' }
  await settle()
  old.resolve({ material: { title: 'old-private' }, attempts: [{ attempt_id: 'old' }] })
  await loading
  assert.equal(h.page.isAdmin.value, false)
  assert.equal(h.page.detail.value.title, '新账号案例')
  assert.deepEqual(plain(h.page.attempts.value), [])
  assert.equal(h.page.helpForm.summary, '')
  assert.equal(h.page.pending.size, 0)
  h.destroy()
  assert.equal(h.page.detail.value, null)
  const source = read('../views/DataLab/DataLabTeacher.vue')
  for (const action of ['setStatus', 'recordHelp', 'loadCases', 'loadCase']) assert.ok(source.includes(`async function ${action}(`))
  assert.match(source, /field === 'withdrawn'.*window.confirm/)
  assert.match(source, /idempotency_key: pending.get\(fingerprint\)/)
  assert.match(source, /v-for="level in 4"/)
  assert.doesNotMatch(source, /RecordView.*detail|JSON.stringify\(detail/)
})
test('case query changes during a pending read clear stale case/help and select the new authorized case', async () => {
  const old = deferred(), route = Vue.reactive({ query: { case: 'old-case' } }), user = { userInfo: { id: 10, role: 'teacher' } }, keys = []
  const h = setup('../views/DataLab/DataLabTeacher.vue', {
    useRoute: () => route, useUserStore: () => user, readableError,
    api: { analytics: { teacherStudentReport: async () => [] } },
    teacherLabApi: {
      cases: async () => ({ cases: [{ task_key: 'old-case' }, { task_key: 'new-case' }] }),
      caseDetail: key => { keys.push(key); return key === 'old-case' ? old.promise : Promise.resolve({ material: { title: '新案例' }, attempts: [] }) },
    },
  }, 'run, loadCases, detail, helpForm, taskKey')
  const loading = h.page.run(h.page.loadCases)
  await settle()
  h.page.helpForm.summary = 'old-private'
  route.query.case = 'new-case'
  await settle()
  old.resolve({ material: { title: '旧案例' }, attempts: [] }); await loading
  assert.equal(h.page.taskKey.value, 'new-case')
  assert.equal(h.page.detail.value.title, '新案例')
  assert.equal(h.page.helpForm.summary, '')
  assert.deepEqual(keys, ['old-case', 'new-case'])
  h.destroy()
})
test('shared history table renders all records including last row and retains before/after, reason and time', async () => {
  const descriptor = parse(read('../shared/learning/CapabilityHistoryTable.vue')).descriptor
  const script = compileScript(descriptor, { id: 'history-table', inlineTemplate: true }).content.replace(/import \{([\s\S]*?)\} from "vue"/g, (_, bindings) => `const {${bindings.replace(/ as /g, ': ')}} = Vue`).replace('export default', 'const C =')
  const C = runInNewContext(`${script}\nC`, { Vue })
  const rows = Array.from({ length: 120 }, (_, i) => ({ title: `能力${i}`, from: '提示后通过', to: '独立通过', reason: '新题复测通过', timeLabel: '2026年11月3日' }))
  const html = await renderToString(Vue.createSSRApp(C, { rows }))
  assert.equal((html.match(/data-label="能力"/g) || []).length, 120)
  for (const text of ['能力119', '提示后通过', '独立通过', '新题复测通过', '2026年11月3日', '共 120 条记录']) assert.ok(html.includes(text), text)
})
test('merged exam and learning legacy routes still preserve their role and query behavior', async () => {
  for (const role of ['student', 'teacher', 'admin']) {
    const router = routerFor(role)
    await router.push('/exam-history?type=theory&status=completed&source=old')
    assert.equal(router.currentRoute.value.path, '/exam-center/history')
    assert.deepEqual(plain(router.currentRoute.value.query), { type: 'theory', status: 'completed', source: 'old' })
    await router.push('/exam-result/42?from=review')
    assert.equal(router.currentRoute.value.path, '/exam-center/result/42')
    assert.equal(router.currentRoute.value.query.from, 'review')
    await router.push('/my-results?window=30&review=own')
    assert.equal(router.currentRoute.value.path, role === 'student' ? '/dashboard' : '/my-results')
    assert.equal(router.currentRoute.value.query.review, 'own')
    await router.push('/analytics?window=90')
    assert.equal(router.currentRoute.value.path, role === 'student' ? '/dashboard' : '/analytics')
    assert.equal(router.currentRoute.value.query.window, '90')
  }
})
test('public homepage, profile interview and task evidence remain distinct valuable functions', async () => {
  for (const [role, landing] of [['guest', '/'], ['student', '/guide'], ['teacher', '/teacher'], ['admin', '/admin/dashboard']]) {
    const router = routerFor(role); await router.push('/'); assert.equal(router.currentRoute.value.path, landing)
  }
  const student = routerFor('student')
  await student.push('/profile/setup'); assert.equal(student.currentRoute.value.name, 'ProfileSetup')
  await student.push('/learning-knowledge/own-attempt'); assert.equal(student.currentRoute.value.name, 'LearningKnowledge')
  assert.equal(canOpen({ requiresTeacher: true }, 'student'), false)
})
test('no active business page still links to moved shadow destinations or deleted exam views', () => {
  function scan(dir) {
    for (const file of readdirSync(dir, { withFileTypes: true })) {
      const path = new URL(file.name + (file.isDirectory() ? '/' : ''), dir)
      if (file.isDirectory()) scan(path)
      else if (file.name.endsWith('.vue')) {
        const source = readFileSync(path, 'utf8')
        assert.doesNotMatch(source, /(?:to=|push\(|replace\().*['"]\/(?:data-lab|capability-map\/changelog|exam-history|exam-result)(?:['"/?])/, path.pathname)
        assert.doesNotMatch(source, /import\(['"].*\/views\/Exam(?:History|Result)\.vue/, path.pathname)
      }
    }
  }
  scan(new URL('../', import.meta.url))
  assert.match(read('../views/LearningMap/CapabilityMap.vue'), /<ChangeLog v-if="historyVisited" v-show="historyOpen"/)
  assert.match(read('../teacher/CapabilityMapAdmin.vue'), /studentChangelog\(id, params\)/)
  assert.doesNotMatch(read('../teacher/CapabilityMapAdmin.vue'), /import.*(?:learning\/capability|LearningMap\/ChangeLog)/)
})
