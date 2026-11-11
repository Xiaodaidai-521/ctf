import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { createRouter, createMemoryHistory } from 'vue-router'
import { guardDestination, pageTitle, canOpen } from '../shared/navigation/access.js'
import { entriesFor, searchEntries } from '../shared/navigation/config.js'
import { teachingDestination, feedbackCandidateDestination } from '../shared/navigation/phase3.js'
import { shadowDestination } from '../learning/shadowRoutes.js'

const source = readFileSync(new URL('./index.js', import.meta.url), 'utf8')
const plain = value => JSON.parse(JSON.stringify(value))
function configuration(role) {
  const user = { isAuthenticated: role !== 'guest', userInfo: { id: 1, role } }
  return runInNewContext(source.replace(/^import .*$/gm, '').replace('export default router', 'router'), {
    createRouter: options => ({ ...options, beforeEach(guard) { this.guard = guard } }),
    createWebHistory: () => ({}), useUserStore: () => user, document: {},
    TeacherLayout: {}, TeacherDashboard: {}, LearningEffectAnalysis: {},
    guardDestination, pageTitle, teachingDestination, feedbackCandidateDestination, shadowDestination,
  })
}
function routerFor(role) {
  const config = configuration(role)
  const stub = routes => routes.map(route => ({
    ...route, component: route.component ? { render: () => null } : undefined,
    children: route.children ? stub(route.children) : undefined,
  }))
  const router = createRouter({ history: createMemoryHistory(), routes: stub(config.routes) })
  router.beforeEach(config.guard)
  return router
}

test('formal learning and teaching entries use the existing new components', () => {
  const routes = configuration('student').routes
  const page = path => routes.find(route => route.path === path)
  assert.match(String(page('/guide').component), /learning\/guide\/GuideView/)
  assert.match(String(page('/dashboard').component), /shared\/navigation\/DashboardEntry/)
  assert.match(String(page('/exam-center/history').component), /learning\/exams\/components\/ExamRecords/)
  assert.match(String(page('/exam-center/result/:id').component), /learning\/exams\/components\/ExamRecordDetail/)
  assert.match(String(page('/learning-knowledge/:attemptId').component), /learningKnowledge\/LearningKnowledge/)
  const challenge = readFileSync(new URL('../views/ChallengeDetail.vue', import.meta.url), 'utf8')
  const modal = readFileSync(new URL('../components/ChallengeDetailModal.vue', import.meta.url), 'utf8')
  for (const view of [challenge, modal]) assert.match(view, /learning\/practice\/ChallengeWorkspace\.vue/)
  const teacher = page('/teacher').children
  for (const [path, component] of [
    ['learning-scores', 'teacher/assessment/TeacherAssessment'],
    ['learning-paths', 'teacher/paths/LearningPathsManageList'],
    ['materials', 'learningKnowledge/TeachingKnowledge'],
    ['knowledge', 'learningKnowledge/KnowledgeLibrary'],
    ['feedback', 'teacher/FeedbackWorkbench'],
    ['teaching-actions', 'teacher/TeacherOperations'],
  ]) assert.ok(String(teacher.find(route => route.path === path).component).includes(component), path)
})

test('every visible menu and search entry resolves within its authorized role', () => {
  for (const role of ['guest', 'student', 'teacher', 'admin']) {
    const router = routerFor(role)
    for (const entry of [...entriesFor(role), ...searchEntries(role)]) {
      const resolved = router.resolve(entry.path)
      assert.notEqual(resolved.name, 'NotFound', `${role}: ${entry.path}`)
      if (role !== 'guest') assert.equal(canOpen(resolved.meta, role), true, entry.path)
    }
  }
  assert.ok(entriesFor('admin').some(entry => entry.path === '/admin/data-security'))
  assert.ok(searchEntries('admin', '数据保护').some(entry => entry.path === '/admin/data-security'))
})

test('legacy growth and exam URLs preserve every query value and fragment', async () => {
  const router = routerFor('student')
  for (const [old, path, section] of [
    ['/analytics', '/dashboard', 'activity'], ['/my-results', '/dashboard', 'results'],
    ['/exam-history', '/exam-center/history'], ['/exam-result/7', '/exam-center/result/7'],
  ]) {
    await router.push(`${old}?window=30&review=7&tag=a&tag=b#selected-record`)
    assert.equal(router.currentRoute.value.path, path)
    assert.deepEqual(plain(router.currentRoute.value.query), {
      window: '30', review: '7', tag: ['a', 'b'], ...(section ? { section } : {}),
    })
    assert.equal(router.currentRoute.value.hash, '#selected-record')
  }
})

test('legacy teaching and knowledge URLs keep query and fragment in their own layouts', async () => {
  for (const [role, old, path] of [
    ['teacher', '/teaching-knowledge', '/teacher/materials'],
    ['admin', '/teaching-knowledge', '/admin/legal/kb/materials'],
    ['teacher', '/learning-paths/new', '/teacher/learning-paths/new'],
    ['teacher', '/learning-paths/7/edit', '/teacher/learning-paths/7/edit'],
    ['teacher', '/knowledge', '/teacher/knowledge'],
    ['admin', '/knowledge', '/admin/legal/kb'],
  ]) {
    const router = routerFor(role)
    await router.push(`${old}?tag=a&tag=b#selected-material`)
    assert.equal(router.currentRoute.value.path, path)
    assert.deepEqual(plain(router.currentRoute.value.query), { tag: ['a', 'b'] })
    assert.equal(router.currentRoute.value.hash, '#selected-material')
  }
})

test('new staff entries deny other roles and require login for guests', async () => {
  for (const path of ['/teacher/materials', '/teacher/learning-scores', '/admin/legal/kb/tools', '/admin/data-security']) {
    const guest = routerFor('guest')
    await guest.push(path)
    assert.equal(guest.currentRoute.value.path, '/login')
    const student = routerFor('student')
    await student.push(path)
    assert.equal(student.currentRoute.value.path, '/access-denied')
  }
})
