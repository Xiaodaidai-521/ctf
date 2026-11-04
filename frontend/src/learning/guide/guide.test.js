import test from 'node:test'
import assert from 'node:assert/strict'
import { asList, pathTarget, reviewTarget, reviewReason, guidePlan, orderedPaths, latestConversation } from './model.js'

test('guide accepts paginated and unpaginated API responses', () => {
  assert.deepEqual(asList({ results: [{ id: 1 }] }), [{ id: 1 }])
  assert.deepEqual(asList([{ id: 1 }]), [{ id: 1 }])
  assert.deepEqual(asList(null), [])
})
test('path and review links are local authorized learning pages, never library links', () => {
  assert.equal(pathTarget({ learning_path: 3, current_module: 4 }), '/learning-paths/3/modules/4')
  assert.equal(pathTarget({ learning_path: 3 }), '/learning-paths/3')
  assert.equal(pathTarget({ learning_path: '//other' }), '/learning-paths')
  assert.equal(reviewTarget({ challenge: { id: 2 } }), '/challenge/2')
  assert.equal(reviewTarget({ action_link: '/knowledge' }), '/capability-map')
})
test('every proposed learning action includes a teaching reason', () => {
  const plan = guidePlan([{ learning_path: 2, path_title: '测试航线' }], [{ concept_name: '访问控制', mastery_level: 0.3 }])
  assert.equal(plan.length, 2)
  assert.ok(plan.every(item => item.title && item.reason && item.to))
  assert.match(plan[0].reason, /巩固/)
  assert.match(reviewReason({ recall_probability: 0.4 }), /记忆/)
  assert.match(reviewReason({ next_review_at: '2020-01-01' }, Date.parse('2026-01-01')), /复习时间/)
})
test('empty records offer diagnosis, not invented learner progress', () => {
  const plan = guidePlan([], [])
  assert.equal(plan.length, 1)
  assert.equal(plan[0].to, '/capability-map')
  assert.match(plan[0].reason, /没有足够/)
})
test('latest path and conversation derive from records without mutating API lists', () => {
  const paths = [{ learning_path: 1, last_accessed: '2025-01-01' }, { learning_path: 2, last_accessed: '2026-01-01' }]
  assert.equal(orderedPaths(paths)[0].learning_path, 2)
  assert.equal(paths[0].learning_path, 1)
  assert.equal(latestConversation([{ id: 1, message_count: 0, updated_at: '2026-01-01' }, { id: 2, message_count: 3, updated_at: '2025-01-01' }]).id, 2)
})
