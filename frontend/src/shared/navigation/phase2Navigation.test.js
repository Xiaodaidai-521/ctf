import test from 'node:test'
import assert from 'node:assert/strict'
import {
  GROWTH_SECTIONS, compatDestination, dashboardOwner, dashboardRouteName,
  growthDestination, parseGrowthSection, shouldKeepAlive,
} from './phase2.js'
import { landingFor, names } from './names.js'
import { guardDestination, pageTitle } from './access.js'
import { searchEntries } from './config.js'

test('old growth deep links resolve to the one growth overview with explicit sections', () => {
  assert.equal(compatDestination('/analytics'), '/dashboard?section=activity')
  assert.equal(compatDestination('/analytics', { window: 30 }), '/dashboard?section=activity&window=30')
  assert.equal(compatDestination('/my-results'), '/dashboard?section=results')
  assert.equal(compatDestination('/my-results', { review: 7 }), '/dashboard?section=results&review=7')
  assert.equal(compatDestination('/dashboard'), null)
  assert.equal(compatDestination('/unknown'), null)
  assert.equal(growthDestination('overview'), '/dashboard')
  assert.equal(growthDestination('capability'), '/dashboard?section=capability')
})

test('growth sections accept only the four real sections', () => {
  assert.deepEqual(GROWTH_SECTIONS, ['overview', 'activity', 'results', 'capability'])
  assert.equal(parseGrowthSection('results'), 'results')
  assert.equal(parseGrowthSection('whatever'), 'overview')
  assert.equal(parseGrowthSection(undefined), 'overview')
})

test('exam history and result deep links resolve to the exam center', () => {
  assert.equal(compatDestination('/exam-history'), '/exam-center/history')
  assert.equal(compatDestination('/exam-result/12'), '/exam-center/result/12')
  assert.equal(compatDestination('/exam-result/12/'), '/exam-center/result/12')
  assert.equal(compatDestination('/exam-result/'), null)
})

test('/dashboard dispatch keeps teacher teaching data and sends admin to governance', () => {
  assert.equal(dashboardOwner('student'), 'student')
  assert.equal(dashboardOwner('teacher'), 'teacher')
  assert.equal(dashboardOwner('admin'), 'admin')
  assert.equal(dashboardOwner(undefined), 'student')
  assert.equal(dashboardRouteName('student'), 'GrowthOverview')
  assert.equal(dashboardRouteName('teacher'), 'StudentDashboard')
  assert.equal(dashboardRouteName('admin'), 'AdminDashboardHome')
  assert.equal(guardDestination({ path: '/dashboard', meta: {} }, { isAuthenticated: true, userInfo: { role: 'admin' } }), '/admin/dashboard')
})

test('student role landing and four primary destinations remain unchanged', () => {
  assert.equal(landingFor('student'), '/guide')
  assert.equal(landingFor('teacher'), '/teacher')
  assert.equal(landingFor('admin'), '/admin/dashboard')
  assert.equal(searchEntries('student', names.growth)[0].path, '/dashboard')
  assert.equal(searchEntries('student', names.exams)[0].path, '/exam-center')
})

test('new growth and capability titles use the shared vocabulary', () => {
  assert.equal(pageTitle({ name: 'GrowthOverview' }, 'student'), names.growth)
  assert.equal(pageTitle({ name: 'GrowthActivity' }, 'student'), `${names.growth} · 学习分析`)
  assert.equal(pageTitle({ name: 'GrowthResults' }, 'student'), `${names.growth} · 结果与复盘`)
  assert.equal(pageTitle({ name: 'CapabilityExplorer' }, 'student'), names.capability)
  assert.equal(pageTitle({ name: 'StudentDashboard' }, 'teacher'), `${names.insights} · 教学数据`)
})

test('KeepAlive is an explicit whitelist, not the whole app', () => {
  for (const name of ['Challenges', 'StudentDashboard', 'ExamHistory', 'LearningPaths', 'MultiAgent']) {
    assert.equal(shouldKeepAlive(name), true)
  }
  for (const name of ['ExamTaking', 'Login', 'AdminDashboardHome', 'LearningKnowledge', undefined]) {
    assert.equal(shouldKeepAlive(name), false)
  }
})
