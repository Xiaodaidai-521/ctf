import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import {
  compatDestination, dashboardOwner, dashboardRouteName, examHistoryDestination, examResultDestination,
} from './phase2.js'
import { canOpen, guardDestination } from './access.js'
import { landingFor } from './names.js'
import { openTutor } from '../../learning/agent/public.js'

const routerSource = readFileSync(new URL('../../router/index.js', import.meta.url), 'utf8')
const multiAgentSource = readFileSync(new URL('../../views/MultiAgent/MultiAgentView.vue', import.meta.url), 'utf8')
const legacySource = readFileSync(new URL('../../views/MultiAgent/legacy/LegacyMultiAgentView.vue', import.meta.url), 'utf8')
const profileSource = readFileSync(new URL('../../views/Profile.vue', import.meta.url), 'utf8')
const resourcesSource = readFileSync(new URL('../../views/Resources.vue', import.meta.url), 'utf8')

test('old growth deep links keep their real query parameters and land on the one overview', () => {
  assert.equal(compatDestination('/analytics'), '/dashboard?section=activity')
  assert.equal(compatDestination('/analytics', { window: 30 }), '/dashboard?section=activity&window=30')
  assert.equal(compatDestination('/analytics', { window: 'bad', mode: 'legacy' }), '/dashboard?section=activity&window=bad')
  assert.equal(compatDestination('/my-results'), '/dashboard?section=results')
  assert.equal(compatDestination('/my-results', { review: 7 }), '/dashboard?section=results&review=7')
  assert.equal(compatDestination('/dashboard'), null)
  assert.equal(compatDestination('/multi-agent?mode=learning'), null)
  assert.equal(compatDestination('/unknown'), null)
})

test('exam history/result deep links map to the record sub-views', () => {
  assert.equal(examHistoryDestination(), '/exam-center/history')
  assert.equal(examResultDestination(12), '/exam-center/result/12')
  assert.equal(compatDestination('/exam-history'), '/exam-center/history')
  assert.equal(compatDestination('/exam-result/12'), '/exam-center/result/12')
  assert.equal(compatDestination('/exam-result/12/'), '/exam-center/result/12')
  assert.equal(compatDestination('/exam-result/'), null)
  assert.match(routerSource, /path: '\/exam-history'[\s\S]*?redirect: to => \(\{ path: '\/exam-center\/history', query: to\.query \}\)/)
  assert.match(routerSource, /path: '\/exam-result\/:id'[\s\S]*?redirect: to => \(\{ path: `\/exam-center\/result\/\$\{to\.params\.id\}`, query: to\.query \}\)/)
})

test('/dashboard dispatches by role without sending teachers to student growth', () => {
  assert.equal(dashboardOwner('student'), 'student')
  assert.equal(dashboardOwner('teacher'), 'teacher')
  assert.equal(dashboardOwner('admin'), 'admin')
  assert.equal(dashboardRouteName('student'), 'GrowthOverview')
  assert.equal(dashboardRouteName('teacher'), 'StudentDashboard')
  assert.equal(dashboardRouteName('admin'), 'AdminDashboardHome')
  assert.match(routerSource, /path: '\/dashboard'[\s\S]*?component: \(\) => import\('@\/shared\/navigation\/DashboardEntry\.vue'\)/)
  assert.equal(guardDestination({ path: '/dashboard', name: 'StudentDashboard', meta: {} }, { isAuthenticated: true, userInfo: { role: 'admin' } }), '/admin/dashboard')
  assert.equal(guardDestination({ path: '/dashboard', name: 'StudentDashboard', meta: {} }, { isAuthenticated: true, userInfo: { role: 'teacher' } }), undefined)
  assert.equal(guardDestination({ path: '/dashboard', name: 'StudentDashboard', meta: {} }, { isAuthenticated: true, userInfo: { role: 'student' } }), undefined)
})

test('role guards keep each role at reachable destinations and guests at login', () => {
  assert.equal(canOpen({ requiresAuth: true }, 'student'), true)
  assert.equal(canOpen({ requiresAuth: true }, 'guest'), false)
  assert.equal(canOpen({ requiresTeacher: true }, 'student'), false)
  assert.equal(canOpen({ requiresTeacherOnly: true }, 'admin'), false)
  assert.equal(guardDestination({ path: '/teacher', name: 'TeacherHome', meta: { requiresTeacherOnly: true } }, { isAuthenticated: true, userInfo: { role: 'student' } }), '/access-denied')
  assert.equal(guardDestination({ path: '/admin/users', name: 'AdminUsers', meta: { requiresAdmin: true } }, { isAuthenticated: true, userInfo: { role: 'teacher' } }), '/access-denied')
  assert.equal(guardDestination({ path: '/guide', name: 'Guide', meta: { requiresAuth: true } }, { isAuthenticated: true, userInfo: { role: 'teacher' } }), '/teacher')
  assert.equal(guardDestination({ path: '/', name: 'Home', meta: {} }, { isAuthenticated: true, userInfo: { role: 'student' } }), '/guide')
  assert.equal(guardDestination({ path: '/', name: 'Home', meta: {} }, { isAuthenticated: false, userInfo: {} }), undefined)
  assert.equal(landingFor('student'), '/guide')
  assert.equal(landingFor('teacher'), '/teacher')
  assert.equal(landingFor('admin'), '/admin/dashboard')
})

test('multi-agent legacy deep links stay compatible without exposing old student configuration', async () => {
  assert.match(routerSource, /path: '\/multi-agent'[\s\S]*?name: 'MultiAgent'[\s\S]*?component: \(\) => import\('@\/views\/MultiAgent\/MultiAgentView\.vue'\)/)
  assert.match(routerSource, /path: '\/multi-agent\/:challengeId'[\s\S]*?name: 'MultiAgentChallenge'[\s\S]*?component: \(\) => import\('@\/views\/MultiAgent\/MultiAgentView\.vue'\)/)
  assert.match(multiAgentSource, /<TutorHost mode="page" \/>/)
  assert.match(multiAgentSource, /<LegacyMultiAgentView v-else \/>/)
  assert.match(multiAgentSource, /watch\(\(\) => route\.params\.challengeId, applyChallengeContext\)/)
  assert.doesNotMatch(multiAgentSource, /route\.query\.mode/, '学生的新导学页不接受旧 mode 配置')
  assert.match(legacySource, /route\.query\.mode === 'learning'/)

  const pushes = []
  const router = {
    push: async value => { pushes.push(value) },
    currentRoute: { value: { path: '/multi-agent' } },
  }
  await openTutor(router, { prompt: '继续上一题', userId: 7 })
  assert.deepEqual(pushes, ['/multi-agent?mode=learning'])
})

test('path, module and generated-content routes remain independent and reloadable', () => {
  assert.match(routerSource, /path: '\/learning-paths\/:id'[\s\S]*?name: 'LearningPathDetail'/)
  assert.match(routerSource, /path: '\/learning-paths\/:pathId\/modules\/:moduleId'[\s\S]*?name: 'ModuleLearning'/)
  assert.match(routerSource, /path: '\/content\/:id'[\s\S]*?name: 'GeneratedContent'/)
  const moduleSource = readFileSync(new URL('../../views/LearningPaths/ModuleLearning.vue', import.meta.url), 'utf8')
  const detailSource = readFileSync(new URL('../../views/LearningPaths/LearningPathDetail.vue', import.meta.url), 'utf8')
  assert.match(moduleSource, /watch\(\[pathId, moduleId\]/)
  assert.match(moduleSource, /onBeforeRouteUpdate\(unsavedNotesGuard\)/)
  assert.match(detailSource, /watch\(pathId, \(next, previous\) =>/)
})

test('profile persona and resource highlight deep links keep their original sections', () => {
  assert.match(profileSource, /const tabFromQuery = value => \(PROFILE_TABS\.includes\(value\) \? value : 'solved'\)/)
  assert.match(profileSource, /route\.query\.tab/)
  assert.match(profileSource, /router\.replace\(\{ path: '\/profile', query \}\)/)
  assert.match(resourcesSource, /highlight_resource/)
  assert.match(resourcesSource, /highlight_resources/)
  assert.match(resourcesSource, /delete query\.highlight_resource/)
  assert.match(resourcesSource, /delete query\.highlight_resources/)
})
