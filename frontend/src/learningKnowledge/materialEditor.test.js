import test from 'node:test'
import assert from 'node:assert/strict'
import { materialExample, parseMaterialForm } from './materialForm.js'
import { emptyMaterialDraft, importMaterialDraft, materialPayload, materialTemplate, metadataFields, materialClasses, sourceTypes, reviewError, sourceChoices, clauseChoices, safeSourceLink, scopeLabel } from './materialEditor.js'
import { formatLocator } from './libraryController.js'

for (const mode of ['register', 'revise']) {
  test(`${mode}: imported complete payload is unchanged, including all metadata and source whitespace`, () => {
    const body = JSON.parse(materialExample(mode))
    body.task_ids = [51, 63]
    body.metadata.source_snapshot = '  第一段原文。\n\n\t第二段原文。\n'
    body.metadata.recheck_due_at = '2027-03-06T15:30:45+08:00'
    const draft = importMaterialDraft(JSON.stringify(body), mode)
    assert.deepEqual(materialPayload(draft, mode), parseMaterialForm(JSON.stringify(body), mode))
    draft.metadata.title = '修改后的标题'
    draft.metadata.conflict_group = '有争议的课堂材料'
    const changed = materialPayload(draft, mode)
    assert.deepEqual(changed, { ...body, metadata: { ...body.metadata, title: draft.metadata.title, conflict_group: draft.metadata.conflict_group } })
    assert.deepEqual(Object.keys(changed).sort(), Object.keys(body).sort())
  })
  test(`${mode}: optional omissions, empty strings and null dates survive import and submit`, () => {
    const body = JSON.parse(materialExample(mode))
    for (const key of ['source_url', 'license_url', 'change_note', 'conflict_group', 'recheck_due_at']) delete body.metadata[key]
    for (const key of ['source_type', 'source_object_id', 'hint_level']) delete body[key]
    assert.deepEqual(materialPayload(importMaterialDraft(JSON.stringify(body), mode), mode), body)
    body.metadata.source_url = ''
    body.metadata.recheck_due_at = null
    if (mode === 'register') body.hint_level = null
    assert.deepEqual(materialPayload(importMaterialDraft(JSON.stringify(body), mode), mode), body)
  })
  test(`${mode}: downloaded blank template has every field but no fabricated task or ready-to-submit sample`, () => {
    const body = JSON.parse(materialTemplate(mode))
    assert.deepEqual(body.task_ids, [])
    assert.equal(body.metadata.source_snapshot, '')
    assert.deepEqual(Object.keys(body.metadata).sort(), [...metadataFields.map(field => field.key), 'recheck_due_at'].sort())
    assert.throws(() => importMaterialDraft(materialTemplate(mode), mode), /文件内容不完整/)
    assert.throws(() => materialPayload(emptyMaterialDraft(), mode), /课程任务/)
  })
}

test('all material classes, hint levels and source types preserve payload meanings', () => {
  for (const [kind] of materialClasses) for (const [source] of sourceTypes) {
    const body = JSON.parse(materialExample('register'))
    body.material_class = kind
    body.source_type = source
    body.source_object_id = source === 'teacher_authored' ? null : 234
    if (kind === 'hint') body.hint_level = 4
    assert.deepEqual(materialPayload(importMaterialDraft(JSON.stringify(body), 'register'), 'register'), body)
  }
})

test('invalid legacy imports remain rejected without showing internal field diagnostics', () => {
  const valid = JSON.parse(materialExample('register'))
  const cases = [
    '{not-json', { ...valid, task_ids: ['TASK-SECRET'] }, { ...valid, task_ids: [] },
    { ...valid, task_ids: Array(21).fill(1) }, { ...valid, scope: 'bypass' },
    { ...valid, source_object_id: -1 }, { ...valid, material_class: 'hint' },
    { ...valid, metadata: { ...valid.metadata, source_date: '2026-02-30' } },
    { ...valid, metadata: { ...valid.metadata, internal: 'secret' } },
  ]
  for (const value of cases) assert.throws(() => importMaterialDraft(typeof value === 'string' ? value : JSON.stringify(value), 'register'), error => {
    assert.doesNotMatch(error.message, /JSON|task_ids|TASK-SECRET|source_object_id|metadata|bypass|scope/)
    return true
  })
  assert.throws(() => importMaterialDraft(JSON.stringify(valid), 'revise'), /文件/)
})

test('edited fields retain validation and never leak parser diagnostic names', () => {
  const draft = importMaterialDraft(materialExample('register'), 'register')
  draft.metadata.title = ''
  assert.throws(() => materialPayload(draft, 'register'), /请填写材料标题/)
  draft.metadata.title = '标题'
  draft.metadata.source_date = '2026-02-30'
  assert.throws(() => materialPayload(draft, 'register'), /来源日期/)
  draft.metadata.source_date = '2026-02-28'
  draft.task_ids = ['task-secret']
  assert.throws(() => materialPayload(draft, 'register'), error => !/task_ids|task-secret|JSON/.test(error.message))
})

test('source options use only identities from authorized projections; legal document IDs are never clause IDs', () => {
  assert.deepEqual(sourceChoices({ results: [
    { source_type: 'article', object_id: 83, title: '来源文章' },
    { source_type: 'resource', object_id: 84, title: '其他类别' },
    { source_type: 'article', object_id: '85', title: '错误值' },
  ] }, 'article'), [{ value: 83, label: '来源文章' }])
  const detail = { source_type: 'legal_document', object_id: 900, chunks: [
    { id: 'clause:17', title: '许可条款', locator: '第一章 / 第三条 / private-key-1' },
    { id: 'embedding:18', title: '不能作为条文' }, { id: 'document:900', title: '不能作为条文' },
  ] }
  assert.deepEqual(clauseChoices(detail, formatLocator), [{ value: 17, label: '许可条款 · 第一章 / 第三条' }])
  assert.deepEqual(clauseChoices({ ...detail, source_type: 'document' }, formatLocator), [])
})

test('errors, publication scope, provenance links are human-readable and do not echo backend content', () => {
  for (const status of [400, 401, 403, 404, 409, 500, 503]) {
    const text = reviewError({ response: { status, data: { task_ids: 'private-uuid', detail: 'CSRF traceback' } } })
    assert.doesNotMatch(text, /private|CSRF|task_ids|traceback|幂等|API|服务器/)
  }
  assert.match(scopeLabel('learner'), /授权任务/)
  assert.match(scopeLabel('unknown_enum'), /暂不可用/)
  for (const link of ['javascript:alert(1)', 'https://user:pass@example.com', '/admin/internal', 'file:///tmp/test']) assert.equal(safeSourceLink(link), '')
  assert.equal(safeSourceLink('https://example.com/license'), 'https://example.com/license')
})
