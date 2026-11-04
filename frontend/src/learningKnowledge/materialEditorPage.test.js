import { createMaterialDeletion, initialMaterialDeletion } from '../shared/knowledge/materialDeletion.js'
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { compile, computed, createSSRApp, h, reactive, ref, watch } from 'vue'
import { compileScript, parse } from 'vue/compiler-sfc'
import { renderToString } from 'vue/server-renderer'
import { names } from '../shared/navigation/names.js'
import * as editor from './materialEditor.js'
import { formatLocator } from './libraryController.js'
import { materialExample, parseMaterialForm } from './materialForm.js'
import { createRequestGeneration } from './requestGeneration.js'
import { consumeTeachingTransfer, teachingIdentity } from '../shared/knowledge/teachingTransfer.js'

const read = file => readFileSync(new URL(file, import.meta.url), 'utf8')
const pageSource = read('./TeachingKnowledge.vue')
const pageDescriptor = parse(pageSource).descriptor
const withoutImports = script => script.replace(/^import .+ from .+\n/gm, '')
function component(file) {
  const descriptor = parse(read(file)).descriptor
  const code = compileScript(descriptor, { id: file }).content
  const dependencies = { computed, ...editor, formatLocator }
  const result = new Function(...Object.keys(dependencies), withoutImports(code).replace('export default', 'return'))(...Object.values(dependencies))
  const setup = result.setup
  // Runtime compilation does not have SFC binding metadata. Expose the real
  // setup result to the real compiled template, excluding its private marker.
  result.setup = (props, context) => ({ ...setup(props, context) })
  result.render = compile(descriptor.template.content)
  return result
}
const MaterialEditor = component('./MaterialEditor.vue')
const MaterialInspection = component('./MaterialInspection.vue')
const visible = html => html.replace(/<[^>]*>/g, '')

for (const mode of ['register', 'revise']) test(`${mode}: actual editor renders every metadata field, file import and executable submit without raw identity text`, async () => {
  const draft = editor.importMaterialDraft(materialExample(mode), mode)
  draft.task_ids = [862451, 862452]
  draft.catalog_version = 'catalog-internal-uuid'
  draft.source_type = 'resource'
  draft.source_object_id = 934512
  const html = await renderToString(createSSRApp(MaterialEditor, { draft, mode, targetTitle: '已选择的材料', catalogs: [] }))
  for (const field of editor.metadataFields) assert.ok(visible(html).includes(field.label), field.label)
  assert.match(html, /导入材料文件/)
  assert.match(pageDescriptor.template.content, /type="file".*@change="importFile\(\$event, 'register'\)"/)
  assert.match(pageDescriptor.template.content, /type="file".*@change="importFile\(\$event, 'revise'\)"/)
  assert.match(html, /下载登记模板|下载修订模板/)
  assert.match(html, /复查时间/)
  assert.match(html, /已导入 2 项适用任务，名称暂不可读取，提交时核验权限/)
  assert.match(html, /<button type="submit"(?![^>]* disabled)/)
  assert.doesNotMatch(visible(html), /862451|862452|934512|catalog-internal-uuid|task_ids|source_object_id|metadata|teacher_authored|请求 JSON/)
  assert.doesNotMatch(html, /<details|<pre|class="lk-json"/)
})

test('local recheck control preserves exact imported timestamp until edited and can clear it', () => {
  const draft = editor.importMaterialDraft(materialExample('register'), 'register')
  draft.metadata.recheck_due_at = '2027-03-06T15:30:45+08:00'
  const setup = MaterialEditor.setup({ draft }, { expose() {} })
  assert.ok(setup.recheckLocal.value)
  assert.equal(draft.metadata.recheck_due_at, '2027-03-06T15:30:45+08:00')
  setup.setRecheck('2027-03-07T13:21:15')
  assert.equal(draft.metadata.recheck_due_at, new Date('2027-03-07T13:21:15').toISOString())
  setup.setRecheck('')
  assert.equal(draft.metadata.recheck_due_at, null)
})

const inspectionFixture = {
  material_id: 'private-material-uuid', title: '待审课堂材料', revision: 3,
  publisher: '课程教研组', source_version: '2026 年版', source_url: 'https://example.com/private-source',
  license_id: 'CC BY 4.0', license_url: 'https://example.com/terms', source_hash: 'private-source-hash',
  author_id: 873461, reviewer_id: 873462, parser_version: 'private-parser-version', acl_version: 349182,
  parse_status: 'completed', published_scope: 'learner', review_status: 'approved', material_class: 'lesson',
  applicability: '适用于课堂实训', change_note: '修正课堂示例', conflict_group: 'private-conflict-key',
  attribution_text: '保留教研组署名', reuse_scope: '课堂使用', source_date: '2026-01-01', verified_at: '2026-01-02',
  source_snapshot: '<script>这是原文，不执行</script>\n\n第二段。', affected_task_count: 2,
  preview_notice: 'internal preview diagnostic',
  chunks: [{ chunk_ref: 'private-chunk-id', heading_path: ['课程材料', '第一章'], locator: { paragraph: 2, internal_id: 'private-locator-id' }, text: '段落原文', location_notice: 'internal locator diagnostic' }],
  tasks: [{ task__task_key: 'private-task-key', task__version: 'internal-version', knowledge_point_ids: ['private-kp'] }],
}
test('inspection renders provenance, full original, chunks and review fields but never raw IDs, locators or enums', async () => {
  const html = await renderToString(createSSRApp(MaterialInspection, { inspection: inspectionFixture, catalogLabel: '安全课程', taskNames: [{ key: 'private-task-key', version: 'internal-version', label: '课堂练习' }] }))
  const text = visible(html)
  for (const expected of ['课程教研组', '2026 年版', 'CC BY 4.0', '第一章', '段落 2', '安全课程', '课堂练习', '保留教研组署名', '适用于课堂实训', '修正课堂示例', '受影响任务', '已批准', '段落已就绪', '在授权任务内供学生使用', '完整原文', '段落原文']) assert.ok(text.includes(expected), expected)
  assert.doesNotMatch(text, /private-|internal|87346|349182|learner|completed|approved|lesson|UUID|JSON|SHA|ACL|解析器/)
  assert.match(html, /&lt;script&gt;这是原文，不执行&lt;\/script&gt;/)
  assert.doesNotMatch(html, /<script>|location_notice/)
  assert.match(html, /href="https:\/\/example.com\/private-source"/)
})

test('unknown metadata enums and missing names have human fallbacks, not hidden raw details', async () => {
  const html = await renderToString(createSSRApp(MaterialInspection, { inspection: { ...inspectionFixture, material_class: 'unknown-class', review_status: 'unknown-state', parse_status: 'unknown-parse', published_scope: 'unknown-scope' } }))
  assert.doesNotMatch(visible(html), /unknown-|private-task-key|873461/)
  assert.match(html, /任务名称暂不可用/)
  assert.match(html, /姓名暂不可用/)
})

function harness(overrides = {}) {
  const lifecycle = { mount: [], unmount: [], deactivate: [], leave: [] }
  const route = reactive({ fullPath: '/teaching-knowledge', query: {} })
  const user = reactive({ userInfo: { role: 'teacher' }, isAuthenticated: true })
  const win = new EventTarget()
  const doc = new EventTarget()
  doc.visibilityState = 'visible'
  doc.hasFocus = () => true
  const usePrivatePage = new Function('onBeforeUnmount', 'onDeactivated', 'onMounted', 'ref', 'watch', 'onBeforeRouteLeave', 'useRoute', 'useUserStore', 'createRequestGeneration', 'document', 'window',
    withoutImports(read('./usePrivatePage.js')).replace('export function', 'function') + '\nreturn usePrivatePage')(
    fn => lifecycle.unmount.push(fn), fn => lifecycle.deactivate.push(fn), fn => lifecycle.mount.push(fn), ref, watch,
    fn => lifecycle.leave.push(fn), () => route, () => user, createRequestGeneration, doc, win)
  const calls = []
  const api = {
    materials: async () => ({ results: [{ material_id: 'private-material-uuid', revision: 3, title: '材料', catalog_version: 'catalog-one' }] }),
    inspect: async () => ({ ...inspectionFixture }),
    register: async body => { calls.push(['register', body]); return { material_id: 'private-material-uuid', revision: 3 } },
    revise: async (id, body) => { calls.push(['revise', id, body]); return { material_id: id, revision: 3 } },
    transition: async (id, action, body) => { calls.push(['transition', id, action, body]) },
    library: async () => ({ results: [] }), libraryDetail: async () => ({}), ...overrides,
  }
  let requestIndex = 0
  const dependencies = {
    computed, ref, reactive, createMaterialDeletion, initialMaterialDeletion, MaterialDeleteDialog: {}, onMounted() {}, names, useUserStore: () => user, useRoute: () => route,
    consumeTeachingTransfer, teachingIdentity, knowledgeApi: api, usePrivatePage,
    requestKey: () => `request-${++requestIndex}`, ...editor, formatLocator,
    readMaterialCatalog: async version => ({ value: version || 'catalog-one', label: '课程名称' }),
    readMaterialTaskNames: async () => [], MaterialEditor, MaterialInspection,
  }
  const script = withoutImports(pageDescriptor.scriptSetup.content)
  const exposed = [...script.matchAll(/^(?:const|(?:async )?function) (\w+)/gm)].map(match => match[1])
  const page = new Function(...Object.keys(dependencies), script + `\nreturn { ${exposed.join(',')} }`)(...Object.values(dependencies))
  for (const fn of lifecycle.mount) fn()
  page.privacy.resume()
  return { page, calls, api, user, route, win, doc, lifecycle }
}
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done }); return { resolve, promise } }
async function importInto(page, mode = 'register', text = materialExample(mode)) {
  page.changeMode(mode)
  const target = { files: [{ size: text.length, text: async () => text }], value: '/private/filename.json' }
  await page.importFile({ target })
  assert.equal(target.value, '')
}

test('register and revise remain executable with exact imported payload, refresh and clearing after confirmed success', async () => {
  for (const mode of ['register', 'revise']) {
    const { page, calls } = harness()
    page.selectedId.value = 'private-material-uuid'
    await importInto(page, mode)
    const body = parseMaterialForm(materialExample(mode), mode)
    await page.saveMaterial()
    assert.deepEqual(calls[0], mode === 'register' ? ['register', body] : ['revise', 'private-material-uuid', body])
    assert.equal(page.inspection.value.title, inspectionFixture.title)
    assert.equal(page.draft.value.metadata.source_snapshot, '')
    assert.match(page.message.value, /材料已保存/)
  }
})

test('invalid import and validation errors preserve previously entered full form; changing course clears only tasks', async () => {
  const { page } = harness()
  await importInto(page)
  const before = editor.materialPayload(page.draft.value, 'register')
  await page.importFile({ target: { files: [{ size: 5, text: async () => '{bad}' }], value: 'private-file.json' } })
  assert.deepEqual(editor.materialPayload(page.draft.value, 'register'), before)
  assert.match(page.error.value, /原表单未被替换/)
  page.changeCatalog('another-authorized-course')
  assert.deepEqual(page.draft.value.task_ids, [])
  assert.deepEqual(page.draft.value.metadata, before.metadata)
  await page.saveMaterial()
  assert.match(page.error.value, /课程任务/)
})

test('native file-dialog blur clears old data but fresh revision import resumes and can choose an authorized target', async () => {
  const h = harness()
  h.page.inspection.value = { ...inspectionFixture }
  h.page.selectedId.value = 'old-private-target'
  h.page.reason.value = 'old-private-reason'
  h.win.dispatchEvent(new Event('blur'))
  const text = materialExample('revise')
  await h.page.importFile({ target: { files: [{ size: text.length, text: async () => text }], value: 'private-file.json' } }, 'revise')
  assert.equal(h.page.formMode.value, 'revise')
  assert.equal(h.page.selectedId.value, '')
  assert.equal(h.page.reason.value, '')
  await h.page.chooseRevisionTarget('private-material-uuid')
  assert.deepEqual(editor.materialPayload(h.page.draft.value, 'revise'), JSON.parse(text))
  await h.page.saveMaterial()
  assert.equal(h.calls[0][0], 'revise')
})

test('switching revision target to another course clears tasks, not metadata', async () => {
  const { page } = harness()
  await importInto(page, 'revise')
  page.selectedCatalog.value = 'catalog-old'
  page.materials.value = [{ material_id: 'target-new', catalog_version: 'catalog-new', revision: 3 }]
  await page.chooseRevisionTarget('target-new')
  assert.deepEqual(page.draft.value.task_ids, [])
  assert.equal(page.draft.value.metadata.title, JSON.parse(materialExample('revise')).metadata.title)
})

test('new local selection cannot resume after a cross-tab session change', async () => {
  const h = harness()
  const event = new Event('storage'); event.key = 'userInfo'; h.win.dispatchEvent(event)
  await importInto(h.page)
  assert.deepEqual(h.page.draft.value, editor.emptyMaterialDraft())
})

test('failed mutation keeps complete editable draft; backend diagnostics never enter page error', async () => {
  const { page } = harness({ register: async () => { throw { response: { status: 400, data: 'task_ids private-id' } } } })
  await importInto(page)
  const before = editor.materialPayload(page.draft.value, 'register')
  await page.saveMaterial()
  assert.deepEqual(editor.materialPayload(page.draft.value, 'register'), before)
  assert.doesNotMatch(page.error.value, /task_ids|private-id/)
})

for (const event of ['blur', 'pagehide', 'visibilitychange', 'storage', 'route', 'user', 'deactivate', 'unmount', 'leave']) test(`${event}: clears draft, imported task/source identities, inspection and options`, async () => {
  const h = harness()
  await importInto(h.page)
  h.page.inspection.value = { ...inspectionFixture }
  h.page.sourceOptions.value = [{ value: 873461, label: '私密来源' }]
  h.page.taskNames.value = [{ key: 'secret', label: '私密任务' }]
  h.page.reason.value = '私密审阅理由'
  if (event === 'visibilitychange') { h.doc.visibilityState = 'hidden'; h.doc.dispatchEvent(new Event(event)) }
  else if (event === 'storage') { const ev = new Event(event); ev.key = 'userInfo'; h.win.dispatchEvent(ev) }
  else if (event === 'route') h.route.fullPath = '/teacher/knowledge'
  else if (event === 'user') h.user.userInfo = { role: 'student' }
  else if (h.lifecycle[event]) h.lifecycle[event].forEach(fn => fn())
  else h.win.dispatchEvent(new Event(event))
  assert.deepEqual(h.page.draft.value, editor.emptyMaterialDraft())
  assert.equal(h.page.inspection.value, null)
  assert.deepEqual(h.page.sourceOptions.value, [])
  assert.deepEqual(h.page.taskNames.value, [])
  assert.equal(h.page.reason.value, '')
})

test('late local file reads, source lookups and inspection cannot repopulate after privacy clear', async () => {
  for (const channel of ['file', 'source', 'inspection']) {
    const wait = deferred()
    const h = harness({ library: () => wait.promise, inspect: () => wait.promise })
    let pending
    if (channel === 'file') pending = h.page.importFile({ target: { files: [{ size: 1, text: () => wait.promise }], value: '' } })
    else if (channel === 'source') { h.page.draft.value.source_type = 'article'; pending = h.page.loadSources() }
    else pending = h.page.inspect({ material_id: 'private', catalog_version: 'secret-version', revision: 1 })
    h.win.dispatchEvent(new Event('blur'))
    wait.resolve(channel === 'file' ? materialExample('register') : channel === 'source' ? { results: [{ object_id: 17, source_type: 'article', title: '私密来源' }] } : inspectionFixture)
    await pending
    assert.deepEqual(h.page.draft.value, editor.emptyMaterialDraft())
    assert.deepEqual(h.page.sourceOptions.value, [])
    assert.equal(h.page.inspection.value, null)
  }
})

for (const status of [401, 403, 404, 503]) test(`${status}: permission-sensitive write failure clears all private form data`, async () => {
  const { page } = harness({ register: async () => { throw { response: { status } } } })
  await importInto(page)
  await page.saveMaterial()
  assert.deepEqual(page.draft.value, editor.emptyMaterialDraft())
  assert.deepEqual(page.catalogs.value, [])
})

test('all four review actions keep expected revision, reason and request-key retry semantics', async () => {
  for (const action of ['submit', 'approve', 'publish', 'withdraw']) {
    const { page, calls } = harness()
    page.inspection.value = { ...inspectionFixture }
    page.action.value = action
    page.reason.value = '  核实本次材料  '
    await page.runAction()
    assert.deepEqual(calls[0], ['transition', 'private-material-uuid', action, { expected_revision: 3, reason: '核实本次材料', idempotency_key: 'request-1' }])
  }
  const attempts = []
  const { page } = harness({ transition: async (...args) => { attempts.push(args); throw new Error('connection lost') } })
  page.inspection.value = { ...inspectionFixture }
  page.reason.value = '同一操作'
  await page.runAction(); await page.runAction()
  assert.deepEqual(attempts[0][2], attempts[1][2])
  page.reason.value = '新理由'
  await page.runAction()
  assert.notEqual(attempts[2][2].idempotency_key, attempts[1][2].idempotency_key)
})

test('student or guest render no material UI, regardless of retained state', async () => {
  for (const role of ['student', 'guest']) {
    const h = harness()
    h.user.userInfo = { role }
    const app = createSSRApp({ render: compile(pageDescriptor.template.content), setup: () => ({ ...h.page, paused: false, sessionChanged: false }) })
    app.component('MaterialEditor', MaterialEditor)
    app.component('MaterialInspection', MaterialInspection)
    app.component('router-link', { setup: (_, { slots }) => () => h('a', slots.default?.()) })
    const html = await renderToString(app)
    assert.doesNotMatch(html, /<main|材料工坊|<form/)
    await h.page.loadList()
    assert.deepEqual(h.calls, [])
  }
})

test('source selection uses authorized list entries and clause keys only, never a document identity', async () => {
  const { page } = harness({ libraryDetail: async () => ({ source_type: 'legal_document', object_id: 921, chunks: [{ id: 'clause:17', title: '第三条' }] }) })
  page.draft.value.source_type = 'legal_clause'
  page.sourceOptions.value = [{ value: 921, label: '法律文件' }]
  await page.selectSource(922)
  assert.equal(page.draft.value.source_object_id, null)
  await page.selectSource(921)
  assert.equal(page.draft.value.source_object_id, null)
  assert.deepEqual(page.clauses.value, [{ value: 17, label: '第三条' }])
})

test('material styles use existing semantic tokens, with no old global stylesheet or raw dimensions/colors', () => {
  assert.doesNotMatch(pageSource, /import ['"]\.\/learningKnowledge.css/)
  for (const file of ['./TeachingKnowledge.vue', './MaterialEditor.vue', './MaterialInspection.vue']) {
    const style = parse(read(file)).descriptor.styles[0]
    assert.ok(style.scoped)
    assert.doesNotMatch(style.content, /#[0-9a-f]{3,8}\b|\d+(?:px|rem)\b|rgba?\(/i)
    assert.match(style.content, /var\(--/)
  }
})
