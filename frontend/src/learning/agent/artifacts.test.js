import test from 'node:test'
import assert from 'node:assert/strict'
import { pathArtifact, planArtifact, readArtifacts, reviewArtifact, shouldRefresh } from './artifacts.js'

const plain = value => JSON.parse(JSON.stringify(value))

test('plan artifact maps only returned structure and never turns prose into writes', () => {
  assert.equal(planArtifact(null), null)
  assert.equal(planArtifact({}), null)
  const artifact = planArtifact({
    title: '本周教学建议', summary: '先巩固授权边界。',
    stages: [
      { title: '回顾', estimated_time: '15 分钟', actions: ['复述要点'], basis: '上次练习出错' },
      { name: '练习', duration: '20 分钟', tasks: [{ title: '同分类练习' }] },
    ],
    generated_at: '2026-11-02T00:00:00Z', persisted: false,
  })
  assert.equal(artifact.kind, 'plan')
  assert.equal(artifact.title, '本周教学建议')
  assert.deepEqual(artifact.items.map(item => item.title), ['回顾', '练习'])
  assert.deepEqual(artifact.items[0].actions, ['复述要点'])
  assert.equal(artifact.items[0].reason, '上次练习出错')
  assert.equal(artifact.persisted, false)
  assert.match(artifact.note, /尚未保存/)
  // 自由回答不能变成 items。
  assert.equal(planArtifact({ answer: '你应该先学访问控制' }), null)
})

test('path artifact uses the real current module and never invents progress', () => {
  assert.equal(pathArtifact([]), null)
  const artifact = pathArtifact([
    { learning_path: 3, path_title: '授权航线', current_module: 8, current_module_title: '边界核查', completed_modules: 2, total_modules: 5, last_accessed: '2026-11-01T00:00:00Z' },
    { learning_path: 4, path_title: '旧航线', last_accessed: '2026-10-01T00:00:00Z' },
  ])
  assert.equal(artifact.target, '/learning-paths/3/modules/8')
  assert.equal(artifact.completed, 2)
  assert.equal(artifact.total, 5)
  const bare = pathArtifact([{ learning_path: 9, title: '新航线' }])
  assert.equal(bare.target, '/learning-paths/9')
  assert.equal(bare.completed, null)
  assert.equal(bare.total, null)
  assert.equal(pathArtifact([{ learning_path: 9, completed_at: '2026-01-01T00:00:00Z' }]), null)
})

test('review artifact keeps real probability and due date, drops items without an id', () => {
  const artifact = reviewArtifact([
    { id: 1, concept_name: '授权边界', recall_probability: 0.42, next_review_at: '2026-11-05T00:00:00Z', reason: '间隔复习' },
    { concept_name: '无标识提醒' },
    { id: 2, concept_name: '证据来源' },
  ])
  assert.deepEqual(plain(artifact.items.map(item => item.id)), [1, 2])
  assert.equal(artifact.items[0].probability, 0.42)
  assert.equal(artifact.items[0].dueAt, '2026-11-05T00:00:00Z')
  assert.equal(artifact.items[1].probability, null)
  assert.deepEqual(plain(reviewArtifact([]).items), [])
})

test('reading artifacts reports each failure separately and never reuses stale values', async () => {
  const withFailure = await readArtifacts({
    plan: async () => { throw new Error('down') },
    paths: async () => [{ learning_path: 3, path_title: '航线', last_accessed: '2026-11-01T00:00:00Z' }],
    reviews: async () => [{ id: 1, concept_name: '概念' }],
    now: () => Date.parse('2026-11-03T00:00:00Z'),
  })
  assert.deepEqual(withFailure.failures, ['教学建议'])
  assert.equal(withFailure.plan, null)
  assert.equal(withFailure.path.title, '航线')
  assert.equal(withFailure.reviews.items.length, 1)
  assert.equal(withFailure.loadedAt, '2026-11-03T00:00:00.000Z')

  const reviewFailed = await readArtifacts({ plan: async () => null, paths: async () => [], reviews: async () => { throw new Error('x') } })
  assert.equal(reviewFailed.reviews.failed, true)
  assert.deepEqual(reviewFailed.failures, ['复习提醒'])
})

test('refresh compares real identifiers so a new suggestion is visible', () => {
  const before = { plan: { title: 'A' }, path: { target: '/learning-paths/3' }, reviews: { items: [{ id: 1 }] } }
  assert.equal(shouldRefresh(before, before), false)
  assert.equal(shouldRefresh(before, { ...before, plan: { title: 'B' } }), true)
  assert.equal(shouldRefresh(before, { ...before, reviews: { items: [{ id: 1 }, { id: 2 }] } }), true)
  assert.equal(shouldRefresh(null, null), false)
})
