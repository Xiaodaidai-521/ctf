import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compile, computed, createSSRApp, ref } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { compileScript, compileTemplate, parse } from 'vue/compiler-sfc'
import { parseReferenceFile } from './referenceFile.js'
import { recordRows } from './recordPresentation.js'

const fields = [{ key: 'owner_id', label: '负责人', type: 'number' }, { key: 'evidence_refs', label: '证据', type: 'list' }, { key: 'external_ref', label: '关联资料' }]
const read = file => readFileSync(new URL(file, import.meta.url), 'utf8')
const plain = value => JSON.parse(JSON.stringify(value))
function downloads() {
  const blobs = [], links = [], revoked = []
  const helper = runInNewContext(`${read('referenceFile.js').replace(/export /g, '')}\n;({ downloadRecord })`, {
    Blob, URL: { createObjectURL(blob) { blobs.push(blob); return `blob:local-${blobs.length}` }, revokeObjectURL: url => revoked.push(url) },
    document: { createElement() { const link = { clicks: 0, click() { this.clicks++ } }; links.push(link); return link } },
  })
  return { ...helper, blobs, links, revoked }
}
function form(file, props, emit = () => {}, helpers = {}) {
  const { descriptor } = parse(read(file))
  const exposed = file === 'RecordView.vue' ? 'rows, downloadRecord' : 'error, message, empty, hasValue, download, clear, importFile'
  return runInNewContext(`${descriptor.scriptSetup.content.replace(/^import .*$/gm, '')}\n;({ ${exposed} })`, {
    ref, computed, recordRows, parseReferenceFile, ...helpers, defineProps: () => props, defineEmits: () => emit,
  })
}
for (const file of ['ReferenceImport.vue', 'RecordView.vue']) {
  test(`${file}: script and template compile`, () => {
    const { descriptor, errors } = parse(read(file))
    assert.deepEqual(errors, [])
    assert.ok(compileScript(descriptor, { id: file }).content)
    assert.deepEqual(compileTemplate({ source: descriptor.template.content, filename: file, id: file }).errors, [])
  })
}
test('strict file import retains arbitrary original references and list order', () => {
  const original = { owner_id: 72, evidence_refs: ['fact-private', 'evidence-private'], external_ref: 'outside/private-reference' }
  assert.deepEqual(parseReferenceFile(JSON.stringify(original), fields), original)
  assert.deepEqual(parseReferenceFile('{"owner_id":"72"}', fields), { owner_id: 72, evidence_refs: [], external_ref: '' })
})
test('strict file import rejects unknown fields, prototype names and wrong types', () => {
  for (const value of ['null', '[]', 'true', '{', '{"other":1}', '{"__proto__":{}}', '{"constructor":"x"}', '{"prototype":"x"}']) {
    assert.throws(() => parseReferenceFile(value, fields))
  }
  for (const owner_id of [true, [], {}, 0, -1, 1.5, '1e3', ' 1 ', Number.MAX_SAFE_INTEGER + 1]) {
    assert.throws(() => parseReferenceFile(JSON.stringify({ owner_id }), fields), /负责人/)
  }
  for (const evidence_refs of ['not-a-list', [1], [{}], ['x'.repeat(2001)]]) {
    assert.throws(() => parseReferenceFile(JSON.stringify({ evidence_refs }), fields), /证据/)
  }
  assert.throws(() => parseReferenceFile(JSON.stringify({ external_ref: {} }), fields), /关联资料/)
  assert.throws(() => parseReferenceFile(' '.repeat(1024 * 1024 + 1), fields), /文件过大/)
})
test('template download and import round-trip all values, without displaying internal references', async () => {
  const d = downloads(), emitted = []
  const props = { title: '核查关联', fields, modelValue: { owner_id: 72, evidence_refs: ['fact-private'], external_ref: 'outside-private' } }
  const state = form('ReferenceImport.vue', props, (...args) => emitted.push(args), d)
  state.download()
  assert.deepEqual(JSON.parse(await d.blobs[0].text()), props.modelValue)
  assert.equal(d.links[0].download, '核查关联模板.json')
  assert.equal(d.links[0].clicks, 1)
  assert.deepEqual(d.revoked, ['blob:local-1'])
  const event = { target: { value: 'selected', files: [{ size: 100, text: () => d.blobs[0].text() }] } }
  await state.importFile(event)
  assert.deepEqual(plain(emitted[0]), ['update:modelValue', props.modelValue])
  assert.equal(event.target.value, '')
  assert.match(state.message.value, /未提交|再提交/)
  const html = await renderToString(createSSRApp({ render: compile(parse(read('ReferenceImport.vue')).descriptor.template.content), setup: () => ({ ...props, ...state }) }))
  assert.doesNotMatch(html.replace(/<[^>]*>/g, ''), /fact-private|outside-private|owner_id|evidence_refs|external_ref/)
  assert.match(html, /负责人：已填写/)
  state.clear()
  assert.deepEqual(plain(emitted[1]), ['update:modelValue', { owner_id: '', evidence_refs: [], external_ref: '' }])
})
test('invalid and unreadable files never replace the original form or echo read errors', async () => {
  const emitted = [], props = { title: '关联', fields, modelValue: { owner_id: 72 } }
  const state = form('ReferenceImport.vue', props, (...args) => emitted.push(args), downloads())
  for (const file of [{ size: 10, text: async () => '{"owner_id":true}' }, { size: 10, text: async () => { throw new Error('FileError internal_uuid') } }, { size: 1024 * 1024 + 1 }]) {
    await state.importFile({ target: { value: '', files: [file] } })
    assert.ok(state.error.value)
    assert.doesNotMatch(state.error.value, /FileError|internal_uuid/)
  }
  assert.equal(emitted.length, 0)
  assert.equal(props.modelValue.owner_id, 72)
})
test('activity recommendation evidence retains real index values and downloadable raw fields', async () => {
  const original = { mastery_score: 0, consistency_score: 12.5, focus_score: 72, web: 70, crypto: null, pwn: 0, unsupported_reference: 'private-event-id' }
  const d = downloads(), props = { value: original, title: '活动建议依据' }
  const state = form('RecordView.vue', props, () => {}, d)
  const html = await renderToString(createSSRApp({ render: compile(parse(read('RecordView.vue')).descriptor.template.content), setup: () => ({ ...props, ...state }) }))
  const text = html.replace(/<[^>]*>/g, '')
  assert.match(text, /掌握指数0/)
  assert.match(text, /学习节奏指数12.5/)
  assert.match(text, /专注指数72/)
  assert.match(text, /Web安全70/)
  assert.match(text, /密码学未提供/)
  assert.match(text, /二进制安全0/)
  assert.doesNotMatch(text, /mastery_score|consistency_score|focus_score|unsupported_reference|private-event-id|\{\s*"/)
  state.downloadRecord(props.value, `${props.title}.json`)
  assert.deepEqual(JSON.parse(await d.blobs[0].text()), original)
})
test('readable records retain all original data in exact downloads, without raw keys or JSON on page', async () => {
  const original = JSON.parse('{"summary":"保留核查说明","status":"passed","ref":"original-private","events":[{"status":"unknown_backend_enum","action_id":"uuid-private"}],"constructor":"private","toString":"private"}')
  const d = downloads(), props = { value: original, title: '核查资料' }
  const state = form('RecordView.vue', props, () => {}, d)
  const html = await renderToString(createSSRApp({ render: compile(parse(read('RecordView.vue')).descriptor.template.content), setup: () => ({ ...props, ...state }) }))
  const text = html.replace(/<[^>]*>/g, '')
  assert.match(text, /保留核查说明.*通过/)
  assert.doesNotMatch(text, /original-private|unknown_backend_enum|uuid-private|constructor|toString|function|\{\s*"/)
  state.downloadRecord(props.value, `${props.title}.json`)
  assert.deepEqual(JSON.parse(await d.blobs[0].text()), original)
})
