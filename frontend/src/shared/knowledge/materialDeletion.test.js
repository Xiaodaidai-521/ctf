import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { parse, compileScript, compileTemplate } from 'vue/compiler-sfc'
import { createRequestGeneration } from '../../learningKnowledge/requestGeneration.js'
import { createMaterialDeletion, initialMaterialDeletion } from './materialDeletion.js'

const row = { material_id: 'unique-material', revision: 3, title: '课程材料' }
function harness(role = 'teacher', fail, reloadFail = false) {
  const state = initialMaterialDeletion(), generation = createRequestGeneration(), calls = []
  const api = { deleteMaterial: async (...args) => { calls.push(args); if (fail) throw fail } }
  const deletion = createMaterialDeletion({ state, privacy: { begin: () => generation.begin() }, api, getRole: () => role,
    reload: async (ticket, id) => { calls.push(['reload', id]); if (reloadFail) throw Error('offline') } })
  return { state, calls, deletion, generation }
}
for (const role of ['teacher', 'admin']) test(`${role} material deletion needs explicit confirmation, reason and version, then reads back`, async () => {
  const h = harness(role)
  h.deletion.open(row); assert.equal(h.calls.length, 0)
  h.deletion.close(); await h.deletion.confirm(); assert.equal(h.calls.length, 0)
  h.deletion.open(row); await h.deletion.confirm(); assert.match(h.state.error, /理由/)
  h.state.reason = '课程不再使用'; await h.deletion.confirm()
  assert.equal(h.calls[0][0], row.material_id)
  assert.equal(h.calls[0][1].expected_revision, 3); assert.equal(h.calls[0][1].reason, '课程不再使用')
  assert.ok(h.calls[0][1].idempotency_key); assert.equal(h.calls[0][2].aborted, false)
  assert.deepEqual(h.calls[1], ['reload', row.material_id]); assert.equal(h.state.target, null)
  assert.match(h.state.message, /列表已更新/)
})
for (const status of [400, 401, 403, 404, 409, 500]) test(`material delete ${status} never hides failure or fabricates success`, async () => {
  const h = harness('teacher', { response: { status, data: { detail: 'internal_uuid traceback' } } })
  h.deletion.open(row); h.state.reason = '删除旧材料'; await h.deletion.confirm()
  assert.equal(h.state.target.title, row.title); assert.equal(h.state.message, '')
  assert.ok(h.state.error); assert.doesNotMatch(h.state.error, /internal_uuid|traceback|接口/)
  assert.equal(h.state.uncertain, status === 500)
})
test('delete response confirmed but failed readback remains acknowledged with a reload instruction', async () => {
  const h = harness('admin', null, true)
  h.deletion.open(row); h.state.reason = '重复材料'; await h.deletion.confirm()
  assert.equal(h.state.target, null); assert.match(h.state.message, /已删除.*暂未更新/); assert.equal(h.state.uncertain, true)
})
test('student and missing revision cannot send delete', async () => {
  for (const role of ['student', '', undefined]) { const h = harness(role); h.deletion.open(row); await h.deletion.confirm(); assert.equal(h.calls.length, 0) }
  const h = harness(); h.deletion.open({ ...row, revision: null }); h.state.reason = '删除'; await h.deletion.confirm(); assert.equal(h.calls.length, 0); assert.match(h.state.error, /版本/)
})
test('duplicate confirmation and late account response cannot repopulate private delete state', async () => {
  const h = harness(); let resolve
  const deletion = createMaterialDeletion({ state: h.state, privacy: { begin: () => h.generation.begin() }, getRole: () => 'teacher',
    api: { deleteMaterial: () => new Promise(done => { resolve = done }) }, reload: () => assert.fail('stale readback') })
  deletion.open(row); h.state.reason = '删除'; const first = deletion.confirm(); await deletion.confirm()
  assert.equal(h.state.busy, true); h.generation.invalidate(); deletion.clear(); resolve({}); await first
  assert.deepEqual(h.state, initialMaterialDeletion())
})
test('staff-only deletion transport obtains CSRF and preserves DELETE body, encoded id and signal', async () => {
  const calls = [], client = { get: async (...args) => { calls.push(['get', ...args]); return { data: {} } }, delete: async (...args) => { calls.push(['delete', ...args]); return { data: { review_status: 'withdrawn' } } } }
  const text = readFileSync(new URL('./governanceApi.js', import.meta.url), 'utf8').replace(/^import .*\r?\n/gm, '').replace('export const', 'const')
  const api = runInNewContext(text + '\n;governanceKnowledgeApi', { axios: { create: () => client }, encodeURIComponent })
  const body = { expected_revision: 3, reason: '删除', idempotency_key: 'unique-key' }, signal = new AbortController().signal
  const result = await api.deleteMaterial('a/b', body, signal)
  assert.equal(calls[0][1], '/users/csrf/'); assert.equal(calls[1][1], '/teaching-knowledge/materials/a%2Fb/')
  assert.equal(calls[1][2].data, body); assert.equal(calls[1][2].signal, signal); assert.equal(result.review_status, 'withdrawn')
})
test('library and material page compile with deletion, keep narrow material-only entries and existing editors', () => {
  for (const file of ['../../learningKnowledge/KnowledgeLibrary.vue', '../../learningKnowledge/TeachingKnowledge.vue', './MaterialDeleteDialog.vue']) {
    const text = readFileSync(new URL(file, import.meta.url), 'utf8'), descriptor = parse(text).descriptor
    const script = compileScript(descriptor, { id: file })
    assert.deepEqual(compileTemplate({ source: descriptor.template.content, filename: file, id: file, compilerOptions: { bindingMetadata: script.bindings } }).errors, [])
    assert.match(text, /删除材料|确认删除/)
    if (file.includes('KnowledgeLibrary')) assert.match(text, /v-if="state.group === 'teaching'"[^>]*@click="deletion.open\(row\)"/)
    if (file.includes('TeachingKnowledge')) { assert.match(text, /v-show="editorOpen"/); assert.match(text, /MaterialEditor/); assert.match(text, /readMaterialTaskNames/) }
  }
})
