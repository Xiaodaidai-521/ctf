import test from 'node:test'
import assert from 'node:assert/strict'
import { clearTeachingTransfer, consumeTeachingTransfer, prepareTeachingTransfer, teachingIdentity, teachingSource } from './teachingTransfer.js'
const teacher = { id: 2, role: 'teacher' }
const detail = { title: '访问控制', full_text: '完整教学原文', publisher: '课程组', source_version: '第二版', license_id: '课程许可', source_url: 'https://example.org/source', license_url: 'https://example.org/license', source_date: '2026-01-01', verified_at: '2026-11-03', reuse_scope: '课堂使用', applicability: '授权课程' }
test('authorized full source is handed over once, with readable attribution, never as publication', () => {
  clearTeachingTransfer(); prepareTeachingTransfer(teacher, 'material', detail)
  const draft = consumeTeachingTransfer(teachingIdentity(teacher), 'material')
  assert.equal(draft.text, detail.full_text)
  assert.equal(draft.source.license_id, '课程许可')
  assert.equal(draft.source.source_version, '第二版')
  for (const key of ['license_url', 'source_date', 'verified_at', 'reuse_scope', 'applicability']) assert.equal(draft.source[key], detail[key])
  assert.equal(draft.task_ids, undefined)
  assert.equal(draft.is_published, undefined)
  assert.equal(consumeTeachingTransfer(teachingIdentity(teacher), 'material'), null)
})
test('account switches and destination mismatches destroy the handoff', () => {
  prepareTeachingTransfer(teacher, 'path', detail)
  assert.equal(consumeTeachingTransfer(teachingIdentity({ id: 3, role: 'teacher' }), 'path'), null)
  assert.equal(consumeTeachingTransfer(teachingIdentity(teacher), 'path'), null)
  prepareTeachingTransfer(teacher, 'material', detail)
  assert.equal(consumeTeachingTransfer(teachingIdentity(teacher), 'path'), null)
})
test('authorized detail chunks become explicitly attributed excerpts, never fabricated full source', () => {
  const source = { title: '课堂文档', chunks: [{ text: '授权段落原文', id: 'private-id' }, { text: '' }] }
  const content = teachingSource(source)
  assert.equal(content.excerpt, true)
  assert.match(content.text, /不代表完整原文/)
  assert.match(content.text, /授权段落原文/)
  assert.doesNotMatch(content.text, /private-id/)
  prepareTeachingTransfer(teacher, 'material', source)
  const draft = consumeTeachingTransfer(teachingIdentity(teacher), 'material')
  assert.equal(draft.source.title, '课堂文档（段落摘录）')
  assert.equal(draft.excerpt, true)
  assert.equal(draft.source.license_id, '')
  assert.equal(teachingSource({ ...source, material_class: 'teacher_answer' }), null)
  assert.equal(teachingSource({ full_text: '完整原文', chunks: source.chunks }).excerpt, false)
})
test('students, list snippets, secrets and oversize content cannot become learner tasks', () => {
  for (const user of [{ id: 1, role: 'student' }, { id: 1, role: 'admin' }, { role: 'teacher' }]) assert.throws(() => prepareTeachingTransfer(user, 'path', detail))
  for (const source of [{ excerpt: '一段摘要' }, { ...detail, material_class: 'grading_secret' }, { ...detail, material_class: 'teacher_answer' }, { full_text: '字'.repeat(100001) }]) assert.throws(() => prepareTeachingTransfer(teacher, 'path', source))
})
