import { createMaterialDeletion, initialMaterialDeletion } from '../shared/knowledge/materialDeletion.js'
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { compile, computed, createSSRApp, effectScope, h, nextTick, reactive, ref, watch } from 'vue'
import { compileScript, parse } from 'vue/compiler-sfc'
import { renderToString } from 'vue/server-renderer'
import * as editor from './materialEditor.js'
import { materialStepForField } from './materialEditorSteps.js'
import { materialExample } from './materialForm.js'
import { createRequestGeneration } from './requestGeneration.js'
import { formatLocator } from './libraryController.js'
import { names } from '../shared/navigation/names.js'
import { clearTeachingTransfer, consumeTeachingTransfer, prepareTeachingTransfer, teachingIdentity } from '../shared/knowledge/teachingTransfer.js'

const read = file => readFileSync(new URL(file, import.meta.url), 'utf8')
const stripImports = source => source.replace(/^import .+ from .+\r?\n/gm, '')
const editorDescriptor = parse(read('./MaterialEditor.vue')).descriptor
const compiledEditor = compileScript(editorDescriptor, { id: 'material-length-regression' }).content
const dependencies = { computed, ...editor }
const MaterialEditor = new Function(...Object.keys(dependencies), stripImports(compiledEditor).replace('export default', 'return'))(...Object.values(dependencies))
const setup = MaterialEditor.setup
MaterialEditor.setup = (props, context) => ({ ...setup(props, context) })
MaterialEditor.render = compile(editorDescriptor.template.content)
const pageDescriptor = parse(read('./TeachingKnowledge.vue')).descriptor
const draftFor = mode => editor.importMaterialDraft(materialExample(mode), mode)

function stepsHarness(mode = 'register', initialStep = 1) {
  const scope = effectScope()
  const props = reactive({ draft: draftFor(mode), mode, targetId: mode === 'revise' ? 'authorized-target' : '', initialStep, busy: false })
  const events = []
  const state = scope.run(() => editor.useMaterialEditorSteps(props, (...args) => events.push(args)))
  return { props, state, events, stop: () => scope.stop() }
}
const stepSections = html => [...html.matchAll(/<section\b([^>]*data-material-step="(\d)"[^>]*)>([\s\S]*?)<\/section>/g)]
const activeSteps = html => stepSections(html).filter(match => !/display:\s*none/.test(match[1])).map(match => Number(match[2]))

for (const mode of ['register', 'revise']) test(`${mode}: the real editor shows exactly one group with all original fields still mounted`, async () => {
  const expected = {
    1: ['title', 'applicability', 'conflict_group'],
    2: ['publisher', 'source_version', 'source_url', 'source_date', 'verified_at', 'license_id', 'license_url', 'attribution_text', 'reuse_scope', 'recheck_due_at'],
    3: ['change_note', 'source_snapshot'],
  }
  for (const initialStep of [1, 2, 3]) {
    const html = await renderToString(createSSRApp(MaterialEditor, { draft: draftFor(mode), mode, initialStep, targetId: 'authorized-target', targetTitle: '已授权材料', catalogs: [{ value: '课程目录', label: '安全课程' }] }))
    assert.deepEqual(activeSteps(html), [initialStep])
    assert.match(html, /<form[^>]* novalidate/)
    assert.equal((html.match(/aria-current="step"/g) || []).length, 1)
    for (const group of stepSections(html)) {
      const keys = [...group[3].matchAll(/data-material-field="([^"]+)"/g)].map(match => match[1])
      assert.deepEqual(keys.filter(key => !['catalog_version', 'revision_target'].includes(key)).sort(), expected[group[2]].sort())
    }
    for (const field of editor.metadataFields) {
      const control = html.match(new RegExp(`<(?:input|textarea)\\b[^>]*data-material-field="${field.key}"[^>]*>`))?.[0]
      assert.ok(control, field.key)
      if (field.required) assert.match(control, /\brequired\b/)
      if (field.max) assert.match(control, new RegExp(`maxlength="${field.max}"`))
      if (field.type) assert.match(control, new RegExp(`type="${field.type}"`))
    }
    assert.match(html, /导入材料文件/)
    assert.match(html, /下载登记模板|下载修订模板/)
    assert.match(html, /适用任务（最多二十项）/)
    assert.match(html, /复查时间（选填，按本地时间）/)
  }
})

test('all registration source actions and revision target choices survive the three-step presentation', async () => {
  const draft = draftFor('register')
  draft.material_class = 'hint'
  draft.hint_level = 4
  draft.source_type = 'legal_clause'
  const html = await renderToString(createSSRApp(MaterialEditor, {
    draft, mode: 'register', initialStep: 2, sourcePage: 2, sourcePrevious: true, sourceNext: true,
    sourceOptions: [{ value: 40, label: '可读取法律文件' }], sourceDocument: 40, clauseOptions: [{ value: 41, label: '第三条' }],
  }))
  for (const label of ['来源类型', '查找来源', '查找', '可读取法律文件', '上一页来源', '下一页来源', '第三条', '材料分类', '提示等级']) assert.ok(html.includes(label), label)
  const revisionHtml = await renderToString(createSSRApp(MaterialEditor, {
    draft: draftFor('revise'), mode: 'revise', targetId: 'allowed', targetTitle: '目标课堂材料', targetCatalog: '课堂课程',
    materials: [{ material_id: 'allowed', title: '目标课堂材料' }],
  }))
  assert.match(revisionHtml, /修订目标/)
  assert.match(revisionHtml, /目标课堂材料/)
  assert.match(revisionHtml, /课堂课程/)
  assert.doesNotMatch(revisionHtml, /<legend>来源关联/)
})

for (const mode of ['register', 'revise']) test(`${mode}: navigating in either direction preserves the exact payload and emits no write`, async () => {
  const harness = stepsHarness(mode)
  const before = editor.materialPayload(harness.props.draft, mode)
  harness.props.draft.metadata.source_snapshot = '  第一段。\n\n\t第二段。\n'
  const edited = editor.materialPayload(harness.props.draft, mode)
  await harness.state.nextStep()
  assert.equal(harness.state.step.value, 2)
  await harness.state.nextStep()
  assert.equal(harness.state.step.value, 3)
  harness.state.selectStep(1)
  harness.state.selectStep(3)
  assert.deepEqual(editor.materialPayload(harness.props.draft, mode), edited)
  assert.deepEqual(harness.events, [])
  await harness.state.submit()
  assert.deepEqual(harness.events, [['save']])
  assert.deepEqual(editor.materialPayload(harness.props.draft, mode), edited)
  assert.deepEqual(before.metadata, { ...edited.metadata, source_snapshot: before.metadata.source_snapshot })
  harness.stop()
})

for (const field of editor.metadataFields.filter(item => item.required)) test(`submit reveals the required ${field.label} step without replacing the draft`, async () => {
  const harness = stepsHarness('register', 3)
  harness.props.draft.metadata[field.key] = '   '
  const before = JSON.stringify(harness.props.draft)
  await harness.state.submit()
  assert.equal(harness.state.step.value, materialStepForField(field.key))
  assert.equal(harness.state.validationIssue.value.key, field.key)
  assert.match(harness.state.validationIssue.value.message, /请填写/)
  assert.equal(JSON.stringify(harness.props.draft), before)
  assert.deepEqual(harness.events, [])
  harness.stop()
})

test('next-step validation is scoped to the displayed group, and task/course/target blockers return to basic information', async () => {
  const harness = stepsHarness()
  harness.props.draft.metadata.publisher = ''
  await harness.state.nextStep()
  assert.equal(harness.state.step.value, 2)
  await harness.state.nextStep()
  assert.equal(harness.state.step.value, 2)
  assert.equal(harness.state.validationIssue.value.key, 'publisher')
  harness.props.draft.metadata.publisher = '编写者'
  for (const [mode, mutate, key] of [
    ['register', props => { props.draft.task_ids = [] }, 'task_ids'],
    ['register', props => { props.draft.catalog_version = '' }, 'catalog_version'],
    ['revise', props => { props.targetId = '' }, 'revision_target'],
  ]) {
    const blocked = stepsHarness(mode, 3)
    mutate(blocked.props)
    await blocked.state.submit()
    assert.equal(blocked.state.step.value, 1)
    assert.equal(blocked.state.validationIssue.value.key, key)
    assert.deepEqual(blocked.events, [])
    blocked.stop()
  }
  harness.stop()
})

test('hidden native-invalid input is revealed and rendered before focus/reportValidity; valid correction can submit', async () => {
  const harness = stepsHarness('register', 3)
  let renderedStep = 3
  harness.state.step.value = 1
  const scope = effectScope()
  scope.run(() => watch(harness.state.step, value => { renderedStep = value }, { flush: 'post' }))
  let invalid = true
  const calls = []
  const control = {
    dataset: { materialField: 'source_url' }, willValidate: true, validationMessage: '请填写有效网址。',
    closest: () => ({ dataset: { materialStep: '2' } }), checkValidity: () => !invalid,
    focus() { assert.equal(renderedStep, 2); calls.push('focus') },
    reportValidity() { assert.equal(renderedStep, 2); calls.push('reportValidity') },
  }
  harness.state.form.value = { querySelectorAll: () => [control], querySelector: () => control }
  await harness.state.submit()
  assert.equal(harness.state.step.value, 2)
  assert.equal(harness.state.validationIssue.value.key, 'source_url')
  assert.deepEqual(calls, ['focus', 'reportValidity'])
  assert.deepEqual(harness.events, [])
  invalid = false
  await harness.state.submit()
  assert.deepEqual(harness.events, [['save']])
  scope.stop()
  harness.stop()
})

test('date/length validation remains strict; busy navigation and submission do not act', async () => {
  const harness = stepsHarness('register', 3)
  harness.props.draft.metadata.source_date = '2026-02-30'
  await harness.state.submit()
  assert.equal(harness.state.step.value, 2)
  assert.equal(harness.state.validationIssue.value.key, 'source_date')
  harness.props.draft.metadata.source_date = '2026-02-28'
  harness.props.draft.metadata.source_snapshot = '长'.repeat(100001)
  await harness.state.submit()
  assert.equal(harness.state.step.value, 3)
  assert.match(harness.state.validationIssue.value.message, /长度/)
  harness.props.busy = true
  harness.state.selectStep(1)
  await harness.state.nextStep()
  await harness.state.submit()
  assert.equal(harness.state.step.value, 3)
  assert.deepEqual(harness.events, [])
  harness.stop()
})

test('replacing the draft or receiving a new initial step clears only presentation validation state', async () => {
  const harness = stepsHarness('register', 3)
  harness.props.draft.metadata.title = ''
  await harness.state.submit()
  harness.props.draft = draftFor('register')
  harness.props.initialStep = 2
  await nextTick()
  assert.equal(harness.state.step.value, 2)
  assert.equal(harness.state.validationIssue.value, null)
  assert.deepEqual(editor.materialPayload(harness.props.draft, 'register'), JSON.parse(materialExample('register')))
  harness.stop()
})

function pageHarness(overrides = {}) {
  const lifecycle = { mount: [], unmount: [], deactivate: [], leave: [] }
  const mounted = []
  const route = reactive({ fullPath: '/teaching-knowledge', query: {} })
  const user = reactive({ userInfo: { id: 7, role: 'teacher' }, isAuthenticated: true })
  const win = new EventTarget()
  const doc = new EventTarget()
  const scrolls = []
  doc.visibilityState = 'visible'
  doc.hasFocus = () => true
  doc.getElementById = id => ({ scrollIntoView: options => scrolls.push([id, options]) })
  const usePrivatePage = new Function('onBeforeUnmount', 'onDeactivated', 'onMounted', 'ref', 'watch', 'onBeforeRouteLeave', 'useRoute', 'useUserStore', 'createRequestGeneration', 'document', 'window',
    stripImports(read('./usePrivatePage.js')).replace('export function', 'function') + '\nreturn usePrivatePage')(
    fn => lifecycle.unmount.push(fn), fn => lifecycle.deactivate.push(fn), fn => lifecycle.mount.push(fn), ref, watch,
    fn => lifecycle.leave.push(fn), () => route, () => user, createRequestGeneration, doc, win)
  const calls = []
  const api = {
    materials: async () => ({ results: [] }),
    inspect: async () => ({ material_id: 'authorized', revision: 1, title: '已保存材料' }),
    register: async body => { calls.push(['register', body]); return { material_id: 'authorized', revision: 1 } },
    revise: async () => { calls.push(['revise']) }, transition: async () => { calls.push(['transition']) }, ...overrides,
  }
  const dependencies = {
    computed, ref, reactive, createMaterialDeletion, initialMaterialDeletion, MaterialDeleteDialog: {}, onMounted: fn => mounted.push(fn), names, useUserStore: () => user, useRoute: () => route,
    consumeTeachingTransfer, teachingIdentity, knowledgeApi: api, usePrivatePage, requestKey: () => 'length-test-request',
    ...editor, formatLocator, readMaterialCatalog: async () => ({ value: 'catalog-one', label: '课程名称' }),
    readMaterialTaskNames: async () => [], MaterialEditor, MaterialInspection: {}, document: doc,
  }
  const script = stripImports(pageDescriptor.scriptSetup.content)
  const exposed = [...script.matchAll(/^(?:const|(?:async )?function) (\w+)/gm)].map(match => match[1])
  const page = new Function(...Object.keys(dependencies), script + `\nreturn { ${exposed.join(',')} }`)(...Object.values(dependencies))
  lifecycle.mount.forEach(fn => fn())
  page.privacy.resume()
  return { page, user, calls, win, route, scrolls, mount: async () => { for (const fn of mounted) await fn() } }
}
async function pageHtml(page) {
  const app = createSSRApp({ render: compile(pageDescriptor.template.content), setup: () => ({ ...page, names, paused: page.privacy.paused, sessionChanged: page.privacy.sessionChanged }) })
  app.component('MaterialEditor', MaterialEditor)
  app.component('MaterialInspection', { render: () => null })
  app.component('ContentAreaNav', { render: () => null })
  app.component('router-link', { setup: (_, { slots }) => () => h('a', slots.default?.()) })
  return renderToString(app)
}
const registrationTag = html => html.match(/<section\b[^>]*id="material-registration"[^>]*>/)?.[0]

test('material workshop defaults to the list; toggling registration preserves draft, source query and inspection', async () => {
  const harness = pageHarness()
  await harness.page.resumeAndLoad()
  const closed = await pageHtml(harness.page)
  assert.match(closed, /aria-expanded="false"[^>]*>登记材料/)
  assert.match(registrationTag(closed), /display:\s*none/)
  harness.page.toggleEditor()
  const draft = harness.page.draft.value
  draft.metadata.title = '未提交的课堂草稿'
  draft.metadata.source_snapshot = '原文\n\n第二段'
  harness.page.sourceQuery.value = '搜索保留'
  harness.page.inspection.value = { title: '保留检查' }
  harness.page.toggleEditor()
  harness.page.toggleEditor()
  assert.equal(harness.page.draft.value, draft)
  assert.equal(harness.page.draft.value.metadata.source_snapshot, '原文\n\n第二段')
  assert.equal(harness.page.sourceQuery.value, '搜索保留')
  assert.equal(harness.page.inspection.value.title, '保留检查')
  assert.doesNotMatch(registrationTag(await pageHtml(harness.page)), /display:\s*none/)
  assert.deepEqual(harness.calls, [])
})

for (const excerpt of [false, true]) test(`knowledge transfer (${excerpt ? 'excerpt' : 'full text'}) opens registration at source/license without saving or publishing`, async () => {
  clearTeachingTransfer()
  const harness = pageHarness()
  prepareTeachingTransfer(harness.user.userInfo, 'material', {
    title: '授权资料', material_class: 'hint', publisher: '教研组', source_version: '版本一', license_id: '课堂许可',
    ...(excerpt ? { chunks: [{ text: '授权段落' }] } : { full_text: '完整原文\n\n第二段' }),
  })
  await harness.mount()
  assert.equal(harness.page.editorOpen.value, true)
  assert.equal(harness.page.editorInitialStep.value, 2)
  assert.equal(harness.page.formMode.value, 'register')
  assert.equal(harness.page.draft.value.material_class, 'hint')
  assert.equal(harness.page.draft.value.metadata.publisher, '教研组')
  assert.deepEqual(harness.page.draft.value.task_ids, [])
  assert.match(harness.page.draft.value.metadata.source_snapshot, excerpt ? /摘录.*不代表完整原文/ : /完整原文\n\n第二段/)
  assert.deepEqual(activeSteps(await pageHtml(harness.page)), [2])
  assert.deepEqual(harness.calls, [])
  assert.equal(harness.scrolls[0][0], 'material-form-title')
  assert.equal(consumeTeachingTransfer(teachingIdentity(harness.user.userInfo), 'material'), null)
})

test('transfers for another identity never open registration', async () => {
  const harness = pageHarness()
  prepareTeachingTransfer({ id: 99, role: 'teacher' }, 'material', { title: '其他身份资料', full_text: '不应显示' })
  await harness.mount()
  assert.equal(harness.page.editorOpen.value, false)
  assert.equal(harness.page.draft.value.metadata.source_snapshot, '')
  assert.deepEqual(harness.calls, [])
})

test('privacy interruption closes registration and late file completion cannot reopen it', async () => {
  let resolve
  const file = new Promise(done => { resolve = done })
  const harness = pageHarness()
  harness.page.toggleEditor()
  const pending = harness.page.importFile({ target: { files: [{ size: 100, text: () => file }], value: 'private.json' } }, 'register')
  harness.win.dispatchEvent(new Event('blur'))
  assert.equal(harness.page.editorOpen.value, false)
  resolve(materialExample('register'))
  await pending
  assert.equal(harness.page.editorOpen.value, false)
  assert.deepEqual(harness.page.draft.value, editor.emptyMaterialDraft())
  assert.deepEqual(harness.calls, [])
})

for (const event of ['storage', 'user', 'route']) test(`${event}: privacy invalidation also folds registration and resets its starting step`, () => {
  const harness = pageHarness()
  harness.page.toggleEditor()
  harness.page.editorInitialStep.value = 2
  harness.page.draft.value.metadata.source_snapshot = '不再可展示的草稿'
  if (event === 'storage') { const changed = new Event('storage'); changed.key = 'userInfo'; harness.win.dispatchEvent(changed) }
  else if (event === 'user') harness.user.userInfo = { id: 99, role: 'student' }
  else harness.route.fullPath = '/teacher/knowledge'
  assert.equal(harness.page.editorOpen.value, false)
  assert.equal(harness.page.editorInitialStep.value, 1)
  assert.deepEqual(harness.page.draft.value, editor.emptyMaterialDraft())
  assert.deepEqual(harness.calls, [])
})

test('fresh explicit import opens registration; confirmed save folds it but failed writes retain editable state', async () => {
  for (const fails of [false, true]) {
    const harness = pageHarness(fails ? { register: async () => { throw { response: { status: 400 } } } } : {})
    const text = materialExample('register')
    await harness.page.importFile({ target: { files: [{ size: text.length, text: async () => text }], value: 'draft.json' } })
    assert.equal(harness.page.editorOpen.value, true)
    const before = editor.materialPayload(harness.page.draft.value, 'register')
    await harness.page.saveMaterial()
    assert.equal(harness.page.editorOpen.value, fails)
    if (fails) assert.deepEqual(editor.materialPayload(harness.page.draft.value, 'register'), before)
    else assert.equal(harness.page.draft.value.metadata.source_snapshot, '')
  }
})
