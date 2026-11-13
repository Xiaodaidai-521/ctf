import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import { computed, effectScope, nextTick, reactive, ref, watch } from 'vue'
import { names, landingFor } from './names.js'
import { createRecentVisits } from './recentVisits.js'
import { shadowDestination } from '../../learning/shadowRoutes.js'
import { groupsFor, entriesFor, searchEntries, activeEntry, learningLinks } from './config.js'
import { canOpen, guardDestination, pageTitle } from './access.js'
import { clearTeachingTransfer, consumeTeachingTransfer, prepareTeachingTransfer, teachingIdentity } from '../knowledge/teachingTransfer.js'

for (const [role, target] of [['student', '/guide'], ['teacher', '/teacher'], ['admin', '/admin/dashboard']]) {
  test(`${role}: login and authenticated root share one landing`, () => {
    assert.equal(landingFor(role), target)
    assert.equal(guardDestination({ name: 'Home' }, { isAuthenticated: true, userInfo: { role } }), target)
    for (const item of entriesFor(role)) assert.ok(item.roles.includes(role))
    assert.equal(new Set(entriesFor(role).map(item => item.path)).size, entriesFor(role).length)
  })
}
test('student primary navigation has exactly four destinations plus a separate exam entrance', () => {
  assert.deepEqual(entriesFor('student').map(item => item.label), [names.guide, names.practice, names.resources, names.growth])
  assert.ok(searchEntries('student').find(item => item.path === '/exam-center'))
  assert.equal(entriesFor('student').some(item => item.path === '/exam-center'), false)
})
test('students cannot discover staff libraries in navigation or page search', () => {
  assert.equal(searchEntries('student').some(item => /knowledge|admin|teacher/.test(item.path)), false)
  assert.equal(searchEntries('student', names.knowledge).length, 0)
  assert.deepEqual(groupsFor('unknown'), [])
})
test('role search resolves canonical names and preserves original structured learning tools', () => {
  assert.equal(searchEntries('teacher', names.knowledge)[0].path, '/teacher/knowledge')
  assert.equal(searchEntries('admin', names.foundation)[0].path, '/admin/legal/kb')
  for (const path of ['/learning-paths', '/capability-map', '/analytics', '/my-results', '/resources/topics/data-security']) {
    assert.ok(learningLinks.some(item => item.path === path))
  }
  assert.equal(shadowDestination({ path: '/data-lab', query: {}, hash: '' }, 'student').path, '/resources/topics/data-security')
})
test('deep pages select the most specific navigation entry', () => {
  assert.equal(activeEntry('teacher', '/teacher/feedback/reconciliation'), 'reconciliation')
  assert.equal(activeEntry('student', '/challenge/3'), 'practice')
  assert.equal(activeEntry('student', '/learning-paths/3/modules/8'), 'guide')
  assert.equal(activeEntry('admin', '/admin/legal/kb/tools'), 'foundation')
})
test('staff denial is explicit while task evidence authorization is unchanged', () => {
  for (const role of ['guest', 'student', 'teacher', 'admin']) {
    assert.equal(canOpen({ requiresTeacher: true }, role), ['teacher', 'admin'].includes(role))
    assert.equal(canOpen({ requiresAuth: true }, role), role !== 'guest')
  }
  assert.equal(guardDestination({ meta: { requiresAdmin: true } }, { isAuthenticated: true, userInfo: { role: 'student' } }), '/access-denied')
})
test('old teacher learning dashboard remains accessible, not swallowed by the new landing', () => {
  assert.equal(guardDestination({ path: '/dashboard' }, { isAuthenticated: true, userInfo: { role: 'teacher' } }), undefined)
  assert.ok(entriesFor('teacher').some(item => item.matches.includes('/dashboard')))
  assert.equal(activeEntry('teacher', '/dashboard'), 'insights')
})
test('page titles use the canonical vocabulary', () => {
  assert.equal(pageTitle({ name: 'Guide' }), names.guide)
  assert.equal(pageTitle({ name: 'TeacherKnowledgeLibrary' }), names.knowledge)
  assert.equal(pageTitle({ name: 'AdminLegalKbHome' }), names.foundation)
  assert.equal(pageTitle({ meta: { title: '学习路径' } }), names.paths)
})
test('header clears private search on identity changes and ignores unauthenticated role data', async () => {
  const source = readFileSync(new URL('../layout/GlobalHeader.vue', import.meta.url), 'utf8')
  const script = source.match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm, '')
  const user = reactive({ isAuthenticated: true, userInfo: { id: 1, role: 'student' } })
  const scope = effectScope()
  const header = scope.run(() => vm.runInNewContext(`${script}\n;({ query, searchOpen, role })`, {
    computed, ref, watch, useUserStore: () => user, useRouter: () => ({}), useRoute: () => reactive({ path: '/guide' }),
    onBeforeUnmount() {}, window: { addEventListener() {}, removeEventListener() {} }, createRecentVisits,
    defineProps() {}, defineEmits() {}, searchEntries, clearTeachingTransfer,
  }))
  try {
    header.query.value = '私人的学习问题'
    header.searchOpen.value = true
    const teacher = { id: 7, role: 'teacher' }
    prepareTeachingTransfer(teacher, 'material', { full_text: '未提交的教学原文' })
    user.userInfo = { id: 2, role: 'student' }
    await nextTick()
    assert.equal(header.query.value, '')
    assert.equal(header.searchOpen.value, false)
    assert.equal(consumeTeachingTransfer(teachingIdentity(teacher), 'material'), null)
    prepareTeachingTransfer(teacher, 'path', { full_text: '同账号重新登录也不恢复' })
    user.isAuthenticated = false
    user.userInfo = { id: 2, role: 'admin' }
    await nextTick()
    assert.equal(header.role.value, 'guest')
    assert.equal(consumeTeachingTransfer(teachingIdentity(teacher), 'path'), null)
  } finally { scope.stop() }
})
test('shell mounts one header and retains the teaching entry after pet removal', () => {
  const source = readFileSync(new URL('../../App.vue', import.meta.url), 'utf8')
  assert.equal((source.match(/<GlobalHeader\b/g) || []).length, 1)
  assert.equal((source.match(/<TutorPet\b/g) || []).length, 0)
  assert.doesNotMatch(source, /AnnouncementButton|Navbar|agent\/lifecycle|agent\/draft/)
  const guide = readFileSync(new URL('../../learning/guide/GuideView.vue', import.meta.url), 'utf8')
  const header = readFileSync(new URL('../layout/GlobalHeader.vue', import.meta.url), 'utf8')
  for (const page of [guide, header]) assert.match(page, /openTutor/)
})
