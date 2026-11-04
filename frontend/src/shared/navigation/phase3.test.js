import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { teachingDestination, feedbackCandidateDestination } from './phase3.js'
import { groupsFor, activeEntry } from './config.js'
import { canOpen } from './access.js'

for (const [old, current] of [
  ['/teaching-knowledge', '/teacher/materials'],
  ['/learning-paths/manage', '/teacher/learning-paths'],
  ['/learning-paths/new', '/teacher/learning-paths/new'],
  ['/learning-paths/17/edit', '/teacher/learning-paths/17/edit'],
]) test(`teacher compatibility retains query and teaching layout: ${old}`, () => {
  const query = Object.freeze({ from: 'legacy', status: 'draft' })
  assert.deepEqual(teachingDestination(old, query, 'teacher'), { path: current, query })
  assert.deepEqual(teachingDestination(`${old}/`, query, 'teacher'), { path: current, query })
  for (const role of ['student', 'admin', 'guest', undefined]) assert.equal(teachingDestination(old, query, role), null)
})

test('learning detail, module and unknown routes are not management redirects', () => {
  for (const path of ['/learning-paths', '/learning-paths/17', '/learning-paths/17/modules/2', '/teacher/materials', '/other']) {
    assert.equal(teachingDestination(path, {}, 'teacher'), null)
  }
})

test('feedback legacy opens candidates in processing, reconciliation stays independent', () => {
  assert.deepEqual(feedbackCandidateDestination({ query: { status: 'candidate_created' } }), {
    path: '/teacher/feedback', query: { status: 'candidate_created' }, hash: '#candidates',
  })
  assert.equal(activeEntry('teacher', '/teacher/feedback/reconciliation'), 'reconciliation')
  assert.equal(activeEntry('teacher', '/teacher/feedback/17'), 'feedback')
})

test('insight and scoring pages share a group, three content pages remain independent', () => {
  const groups = groupsFor('teacher')
  const tracking = groups.find(group => group.items.some(item => item.key === 'insights'))
  assert.deepEqual(tracking.items.map(item => item.path), ['/teacher/learning-effect', '/teacher/learning-scores'])
  const paths = groups.flatMap(group => group.items.map(item => item.path))
  for (const path of ['/teacher/resources', '/teacher/knowledge', '/teacher/materials']) assert.equal(paths.filter(item => item === path).length, 1)
  assert.equal(paths.includes('/teacher/feedback/candidates'), false)
})

test('new teacher routes retain teacher-only access and shared assembly boundaries', () => {
  const source = readFileSync(new URL('../../router/index.js', import.meta.url), 'utf8')
  for (const role of ['student', 'admin', 'guest']) assert.equal(canOpen({ requiresTeacherOnly: true }, role), false)
  assert.equal(canOpen({ requiresTeacherOnly: true }, 'teacher'), true)
  for (const file of ['TeacherChallengePanel.vue', 'TeacherResourcePanel.vue', 'TeacherLearningDashboard.vue']) {
    const page = readFileSync(new URL(`../../teacher/${file}`, import.meta.url), 'utf8')
    assert.doesNotMatch(page, /from ['"][^'"]*admin\/views/)
  }
  assert.match(source, /path: 'materials'.*requiresTeacherOnly: true/)
  assert.match(source, /path: 'learning-scores'.*teacher\/assessment\/TeacherAssessment/)
  assert.match(source, /path: 'learning-paths\/new'.*teacher\/paths\//)
})
