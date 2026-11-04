import test from 'node:test'
import assert from 'node:assert/strict'
import { cockpitTiles, cockpitPriorities, cockpitError } from './model.js'
const source = data => ({ data, loading: false, error: '' })
test('cockpit uses source-owned counts without adding overlapping queues', () => {
  const rows = cockpitTiles({ reviews: source({ counts: { manual_pending: 2, sampling_pending: 3, disputes_pending: 4 } }), feedback: source({ counts: { pending_fact_review: 1, pending_evidence: 2, confirmed: 3, reopened: 4, handled: 90 } }), resources: source({ count: 8 }), materials: source({ results: [{ review_status: 'in_review' }, { review_status: 'published' }] }), paths: source({ results: [{ is_published: false }, { is_published: true }], next: 'next' }) })
  assert.deepEqual(rows.map(row => row.count), [8, 1, 2, 3, 4, 10, 1])
  assert.match(rows.find(row => row.key === 'paths').scope, /本次已读取/)
  assert.match(rows.find(row => row.key === 'manual').href, /tab=manual/)
})
test('missing, malformed and denied counts never become zero', () => {
  const rows = cockpitTiles({ resources: { data: null, error: '授权不足', loading: false }, feedback: source({ counts: {} }), reviews: source({ counts: { manual_pending: null, sampling_pending: -1, disputes_pending: '2' } }) })
  assert.ok(rows.every(row => row.count === null))
  assert.equal(rows[0].error, '授权不足')
  assert.match(cockpitError({ response: { status: 403 } }), /授权/)
})
test('real zero is retained and priority feedback opens its exact authorized detail', () => {
  assert.equal(cockpitTiles({ reviews: source({ counts: { manual_pending: 0 } }) }).find(row => row.key === 'manual').count, 0)
  const rows = cockpitPriorities({ feedback: source({ items: [{ feedback_id: 'abc', task_title: '练习一', status: 'pending_fact_review', student_name: '学生', conflict_flag: true }, { feedback_id: 'done', status: 'handled' }] }) })
  assert.equal(rows.length, 1)
  assert.equal(rows[0].href, '/teacher/feedback/abc')
  assert.match(rows[0].reason, /冲突/)
})
