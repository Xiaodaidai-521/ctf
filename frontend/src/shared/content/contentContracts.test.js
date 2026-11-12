import { uiSnapshot } from '../state/retention.js'
import { onAccountClear } from '../state/accountScope.js'
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import * as Vue from 'vue'
import { renderToString } from 'vue/server-renderer'
import { parse, compileScript, compileStyle, compileTemplate } from 'vue/compiler-sfc'
import * as presentation from './presentation.js'
import { names } from '../navigation/names.js'

const read = file => readFileSync(new URL(file, import.meta.url), 'utf8')
function module(file, expose, globals = {}) {
  const text = read(file).replace(/^import[\s\S]*?from ['"][^'"]+['"];?\s*/gm, '').replace(/^export /gm, '')
  return runInNewContext(`${text}\n;({${expose}})`, { ...Vue, ...presentation, uiSnapshot, onAccountClear, ...globals })
}
const domain = module('./api.js', 'createContentApi, requireContentRole', { api: {} })
const challengeModule = module('./useChallengeContent.js', 'useChallengeContent', domain)
const resourceModule = module('./useResourceContent.js', 'useResourceContent', domain)
const challenge = (role, service) => challengeModule.useChallengeContent(role, service)
const resource = (role, service, saveFile = () => {}) => resourceModule.useResourceContent(role, service, saveFile)
const list = (items = [], next = null, count = items.length) => ({ results: items, count, next })
const validForm = () => ({ title: '入门练习', category: 3, difficulty: 'hard', score: 30, description: '题目内容', flag: 'flag{teacher}', hint: '先观察输入', is_active: false, docker_image: 'teaching-image', redirect_port: 80, redirect_type: 'path' })
const forbidden = { response: { status: 403, data: { detail: 'Forbidden internal_uuid' } } }
function originalApi(section, api) {
  const source = read('../../api/index.js')
  const start = source.indexOf(`  ${section}: {`)
  const end = source.indexOf('\n  },', start) + 5
  return runInNewContext(`({${source.slice(start, end)}}).${section}`, { api })
}

test('content domain preserves existing endpoints and all eleven request fields for both roles', async () => {
  for (const role of ['teacher', 'admin']) {
    const calls = []
    const transport = Object.fromEntries(['get', 'post', 'put', 'delete'].map(method => [method, async (...args) => { calls.push([method, ...args]); return {} }]))
    const client = { challenge: originalApi('challenge', transport), resource: originalApi('resource', transport) }
    const api = domain.createContentApi(role, client)
    const fields = validForm()
    await api.categories(); await api.challenges({ page: 2, is_active: 'false' }); await api.challengeDetail(7)
    await api.createChallenge(fields); await api.updateChallenge(7, fields); await api.deleteChallenge(7)
    await api.resources({ status: 'pending', page: 1, page_size: 1 })
    await api.reviewResource(8, 'rejected', '请补充来源')
    const upload = new FormData(); upload.append('title', '课程资料')
    await api.uploadResource(upload); await api.downloadResource(8)
    assert.equal(api.role, role)
    assert.deepEqual(calls.map(call => call.slice(0, 2)), [
      ['get', '/challenges/categories/'], ['get', '/challenges/challenges/'], ['get', '/challenges/challenge/7/'],
      ['post', '/challenges/challenges/'], ['put', '/challenges/challenges/7/'], ['delete', '/challenges/challenges/7/'],
      ['get', '/resources/admin/'], ['post', '/resources/review/'], ['post', '/resources/upload/'], ['get', '/resources/8/download/'],
    ])
    assert.equal(calls[3][2], fields); assert.equal(calls[4][2], fields)
    assert.deepEqual(Object.keys(calls[7][2]), ['resource_id', 'status', 'review_comment'])
    assert.equal(calls[7][2].review_comment, '请补充来源')
    assert.equal(calls[8][2], upload); assert.equal(calls[9][2].responseType, 'blob')
  }
})
test('missing/student roles never receive a management API or state', () => {
  for (const role of [undefined, 'student', 'visitor', 'administrator']) {
    assert.throws(() => domain.createContentApi(role, {}), /仅供教师和管理员/)
    assert.throws(() => challenge(role, {}), /仅供教师和管理员/)
    assert.throws(() => resource(role, {}), /仅供教师和管理员/)
  }
})
test('teacher resource 403 is preserved without public-list fallback, fake empty state or fake zero counts', async () => {
  let calls = 0, fallback = 0
  const api = domain.createContentApi('teacher', { resource: { adminList: async () => { calls++; throw forbidden }, list: async () => { fallback++; return list() } } })
  const page = resource('teacher', api)
  await page.applyQuery({ status: 'pending', resource: '71' })
  assert.equal(calls, 1); assert.equal(fallback, 0)
  assert.match(page.state.listError, /教师账号没有资源审核权限/)
  assert.match(page.state.selectionError, /无法查看所选资源/)
  assert.equal(page.state.total, null); assert.equal(Object.keys(page.state.counts).length, 0)
  assert.doesNotMatch(page.state.listError, /Forbidden|uuid|403|API/)
})
test('resource status and query selection find readable details across authorised pages', async () => {
  const calls = []
  const page = resource('admin', { resources: async params => {
    calls.push(params)
    if (params.page_size === 1) return list([], null, 2)
    return params.page === 1 ? list([{ id: 1, title: '第一份' }], '?page=2', 2) : list([{ id: 71, title: '课程讲义', status: 'approved' }], null, 2)
  } })
  await page.applyQuery({ status: 'approved', resource: '71' })
  assert.equal(page.state.status, 'approved'); assert.equal(page.state.preview.title, '课程讲义')
  assert.ok(calls.some(params => params.page === 2 && params.status === 'approved'))
  await page.applyQuery({ status: 'approved', resource: '999' })
  assert.equal(page.state.preview, null); assert.match(page.state.selectionError, /不在当前审核状态/)
  assert.doesNotMatch(page.state.selectionError, /999/)
})
test('resource selection read failures remain explicit and cannot become a not-found claim', async () => {
  const page = resource('admin', { resources: async params => {
    if (params.page === 2) throw Error('offline')
    return list([{ id: 1 }], '?page=2', 2)
  } })
  await page.applyQuery({ status: 'pending', resource: '3' })
  assert.equal(page.state.preview, null); assert.match(page.state.selectionError, /暂时未完成/)
  assert.equal(page.state.selectionLoading, false)
})
test('challenge filters actually send category, difficulty, inactive status and pagination', async () => {
  const calls = []
  const page = challenge('admin', { challenges: async params => { calls.push(params); return list([{ id: 5 }], '?page=2', 21) } })
  Object.assign(page.state.filters, { category: 3, difficulty: 'hard', is_active: 'false' })
  await page.filter(); await page.changePage(2)
  assert.deepEqual(Object.keys(calls[0]), ['page', 'page_size', 'category', 'difficulty', 'is_active'])
  assert.equal(calls[0].is_active, 'false'); assert.equal(calls[1].page, 2)
  assert.equal(page.state.total, 21); assert.equal(page.state.hasNext, true)
})
test('challenge create/edit save all original fields, preserve failed form and only close on success', async () => {
  const writes = []; let fail = true
  const service = { challenges: async () => list(), challengeDetail: async () => ({ id: 5, ...validForm() }), createChallenge: async data => { writes.push(data); if (fail) throw Error('offline') }, updateChallenge: async (id, data) => { writes.push({ id, data }) } }
  const page = challenge('teacher', service)
  page.create(); Object.assign(page.state.form, validForm()); await page.save()
  assert.equal(page.state.editor, 'create'); assert.equal(page.state.form.flag, 'flag{teacher}'); assert.match(page.state.error, /保存题目/)
  fail = false; await page.save()
  assert.equal(page.state.editor, null); assert.match(page.state.success, /已保存/)
  assert.deepEqual(Object.keys(writes[1]), presentation.challengeFields)
  await page.edit({ id: 5 }); await page.save()
  assert.equal(writes[2].id, 5); assert.deepEqual(Object.keys(writes[2].data), presentation.challengeFields)
  page.create(); assert.equal(page.state.form.title, ''); assert.equal(page.state.form.is_active, true)
})
test('missing answer is not fabricated; all original fields stay editable', async () => {
  const page = challenge('admin', { challengeDetail: async () => ({ id: 5, title: '原题', category: 3, description: '内容' }) })
  await page.edit({ id: 5 })
  assert.equal(page.state.form.flag, ''); assert.equal(Object.keys(page.state.form).length, 11)
  await page.save(); assert.match(page.state.error, /答案/); assert.equal(page.state.editor, 'edit')
})
test('challenge deletion is confirmed, refreshes, corrects last-row page and preserves failure feedback', async () => {
  const calls = []; let fail = false
  const page = challenge('admin', { deleteChallenge: async id => { calls.push(id); if (fail) throw forbidden }, challenges: async () => list() })
  await page.remove({ id: 2, title: '原题' }, () => false); assert.equal(calls.length, 0)
  page.state.page = 2; page.state.items = [{ id: 2 }]
  await page.remove({ id: 2, title: '原题' }, () => true)
  assert.equal(page.state.page, 1); assert.match(page.state.success, /已删除/)
  fail = true; await page.remove({ id: 3, title: '原题' }, () => true)
  assert.match(page.state.error, /无权删除题目/); assert.equal(page.state.busy, false)
})
test('challenge list/category failures are separate, malformed data never becomes empty and retry recovers', async () => {
  let fail = true
  const page = challenge('teacher', { challenges: async () => fail ? {} : list([{ id: 1 }]), categories: async () => { if (fail) throw Error('offline'); return [{ id: 3, name: '基础' }] } })
  await Promise.all([page.load(), page.loadCategories()])
  assert.match(page.state.listError, /读取题目/); assert.match(page.state.categoriesError, /读取分类/)
  assert.equal(page.state.total, null)
  fail = false; await Promise.all([page.load(), page.loadCategories()])
  assert.equal(page.state.listError, ''); assert.equal(page.state.categoriesError, ''); assert.equal(page.state.categories[0].name, '基础')
})
test('late challenge/resource list responses cannot overwrite newer filters or unmounted state', async () => {
  for (const make of [service => challenge('teacher', { challenges: service }), service => resource('admin', { resources: service })]) {
    const pending = []
    const page = make(params => new Promise(resolve => pending.push({ params, resolve })))
    const first = page.load(); const second = page.load()
    pending[0].resolve(list([{ id: 1 }])); await first; assert.equal(page.state.loading, true)
    pending[1].resolve(list([{ id: 2 }])); await second; assert.equal(page.state.items[0].id, 2)
    const third = page.load(); page.destroy(); pending[2].resolve(list([{ id: 3 }])); await third
    // Unmount now deliberately wipes authorized records; the late response must not repopulate them.
    assert.equal(page.state.items.length, 0)
  }
})
test('resource filtering/pagination send existing search, type, category, ordering and status params', async () => {
  const calls = [], page = resource('admin', { resources: async params => { calls.push(params); return list([{ id: 1 }], '?page=2', 21) } })
  Object.assign(page.state.filters, { search: '讲义', resource_type: 'document', category: '密码学', ordering: '-download_count' })
  await page.selectStatus('approved'); await page.changePage(2); await page.selectStatus('all')
  assert.equal(calls[0].search, '讲义'); assert.equal(calls[0].resource_type, 'document'); assert.equal(calls[0].status, 'approved')
  assert.equal(calls[1].page, 2); assert.equal(calls[2].page, 1); assert.equal(calls[2].status, undefined)
})
test('stale resource counts cannot overwrite a newer permission failure', async () => {
  const pending = []
  const page = resource('teacher', { resources: params => params.page_size === 1 ? new Promise(resolve => pending.push(resolve)) : Promise.reject(forbidden) })
  const old = page.loadCounts()
  await page.load()
  for (const resolve of pending) resolve(list([], null, 8))
  await old
  assert.equal(Object.keys(page.state.counts).length, 0)
  assert.match(page.state.listError, /没有资源审核权限/)
})
test('a changed resource query cannot receive the previous target detail', async () => {
  let resolveOld
  const page = resource('admin', { resources: params => {
    if (params.page === 2 && params.status === 'pending') return new Promise(resolve => { resolveOld = resolve })
    return Promise.resolve(params.status === 'approved' ? list([{ id: 9, title: '新选择' }]) : list([{ id: 1 }], '?page=2', 2))
  } })
  const old = page.applyQuery({ status: 'pending', resource: '7' })
  await new Promise(resolve => setImmediate(resolve))
  assert.equal(typeof resolveOld, 'function')
  await page.applyQuery({ status: 'approved', resource: '9' })
  resolveOld(list([{ id: 7, title: '旧选择' }]))
  await old
  assert.equal(page.state.preview.title, '新选择')
})
test('resource count read failures do not fabricate or retain zero counts, retry uses all original statuses', async () => {
  let fail = true
  const page = resource('admin', { resources: async params => { if (fail && params.status === 'approved') throw Error('offline'); return list([], null, params.status === 'pending' ? 0 : 4) } })
  await page.loadCounts(); assert.equal(Object.keys(page.state.counts).length, 0); assert.match(page.state.countsError, /数量/)
  fail = false; await page.loadCounts(); assert.equal(page.state.counts.pending, 0); assert.equal(page.state.counts.all, 4)
})
test('resource rejection requires a reason, preserves denial and retains approval/rejection notes', async () => {
  const calls = []; let fail = true
  const page = resource('admin', { resources: async () => list(), reviewResource: async (...args) => { calls.push(args); if (fail) throw forbidden } })
  page.review({ id: 7, title: '资源' }, 'rejected'); await page.confirmReview(); assert.equal(calls.length, 0)
  page.state.note = '请补充出处'; await page.confirmReview(); assert.notEqual(page.state.review, null); assert.equal(page.state.note, '请补充出处'); assert.match(page.state.error, /无权/)
  fail = false; await page.confirmReview(); assert.equal(page.state.review, null); assert.deepEqual(calls[1], [7, 'rejected', '请补充出处'])
  page.review({ id: 7 }, 'approved'); page.state.note = '内容适用'; await page.confirmReview(); assert.deepEqual(calls[2], [7, 'approved', '内容适用'])
})
test('teacher upload remains available through original API despite review 403, without claiming a visible review list', async () => {
  const uploads = []
  const page = resource('teacher', { resources: async () => { throw forbidden }, uploadResource: async data => uploads.push(data) })
  page.state.uploadOpen = true
  const data = new FormData(); data.append('title', '教学材料')
  await page.upload(data)
  assert.equal(uploads[0], data); assert.equal(page.state.uploadOpen, false)
  assert.match(page.state.success, /已上传/); assert.match(page.state.listError, /没有资源审核权限/); assert.equal(page.state.total, null)
})
test('download uses original Blob response, preserves unavailable-file feedback and guards duplicates', async () => {
  let fail = true, calls = 0; const saves = []
  const page = resource('admin', { downloadResource: async () => { calls++; if (fail) throw { response: { status: 404 } }; return { data: new Blob(['讲义']), headers: {} } } }, (...args) => saves.push(args))
  page.state.preview = { id: 7, title: '讲义' }; await page.download(); assert.match(page.state.error, /文件暂不可用/); assert.equal(saves.length, 0)
  fail = false; await page.download(); assert.equal(saves[0][1].title, '讲义'); assert.equal(calls, 2)
})
test('download file helper decodes filenames and always revokes Blob URL', () => {
  const events = [], link = { click: () => events.push('click'), remove: () => events.push('remove') }
  presentation.saveResourceFile({ data: 'blob', headers: { 'content-disposition': "attachment; filename*=UTF-8''%E8%AE%B2%E4%B9%89.pdf" } }, {}, { createElement: () => link, body: { appendChild: () => events.push('append') } }, { createObjectURL: () => 'blob:download', revokeObjectURL: value => events.push(value) })
  assert.equal(link.download, '讲义.pdf'); assert.deepEqual(events, ['append', 'click', 'remove', 'blob:download'])
})

const pages = ['../../teacher/TeacherChallengePanel.vue', '../../teacher/TeacherResourcePanel.vue', '../../admin/views/Challenges.vue', '../../admin/views/Resources.vue']
const components = readdirSync(new URL('./', import.meta.url)).filter(file => file.endsWith('.vue')).map(file => `./${file}`)
const tokenSource = read('../design/tokens.css')
const tokens = new Set([...tokenSource.matchAll(/(--[\w-]+)\s*:/g)].map(match => match[1]))
for (const file of [...pages, ...components]) test(`content SFC contract, scoped tokens and no internal display: ${file}`, () => {
  const { descriptor, errors } = parse(read(file))
  assert.deepEqual(errors, [])
  const script = compileScript(descriptor, { id: 'content-contract' })
  assert.deepEqual(compileTemplate({ source: descriptor.template.content, filename: file, id: 'content-contract', compilerOptions: { bindingMetadata: script.bindings } }).errors, [])
  assert.doesNotMatch(descriptor.template.content, /\{\{[^}]*\.(?:id|uuid)\b|\{\{[^}]*\b(?:file_url|url)\b|\$route\.path|\/api\//)
  assert.doesNotMatch(descriptor.scriptSetup.content, /from ['"]@\/(?:teacher|admin)\//)
  for (const style of descriptor.styles) {
    const css = style.src ? readFileSync(new URL(style.src, new URL(file, import.meta.url)), 'utf8') : style.content
    assert.equal(style.scoped, true); assert.doesNotMatch(css, /#[\da-f]{3,8}\b|rgba?\(|@import/i)
    assert.deepEqual(compileStyle({ source: css, filename: file, id: 'data-v-content', scoped: true }).errors, [])
    for (const [, name] of css.matchAll(/var\((--[\w-]+)/g)) assert.ok(tokens.has(name), name)
  }
})
function executeSfc(file, props = {}, globals = {}) {
  const descriptor = parse(read(file)).descriptor
  const bindingEntries = Object.entries(compileScript(descriptor, { id: 'sfc-runtime' }).bindings)
  const bindings = bindingEntries.filter(([, type]) => type !== 'props').map(([name]) => name)
  const declaredProps = Object.fromEntries(bindingEntries.filter(([, type]) => type === 'props').map(([name]) => [name, undefined]))
  const registry = Object.fromEntries(['ChallengeFilters', 'ChallengeTable', 'ChallengeEditor', 'ContentPagination', 'ContentAreaNav', 'ResourceSidebar', 'ResourceFilters', 'ResourceReviewList', 'ResourceReviewDialog', 'ResourcePreview', 'ResourceUploadForm', 'ContentDialog', 'AppIcon', 'ProtectionBadge', 'router-link'].map(name => [name, { name, setup(_, { slots }) { return () => Vue.h('div', {}, [slots.default?.(), slots.footer?.()]) } }]))
  const script = descriptor.scriptSetup.content.replace(/^import[\s\S]*?from ['"][^'"]+['"];?\s*/gm, '')
  const state = runInNewContext(`${script}\n;({${bindings}})`, { ...Vue, ...presentation, ...registry, names, defineProps: () => props, defineEmits: () => () => {}, onMounted() {}, onBeforeUnmount() {}, watch() {}, ...globals })
  return { state, component: { setup: () => ({ ...declaredProps, ...props, ...state }), render: Vue.compile(descriptor.template.content), components: registry } }
}
test('real teacher resource SFC renders permission explanation, not the empty list branch or internal identifiers', async () => {
  const page = resource('teacher', { resources: async () => { throw forbidden } })
  await page.applyQuery({ status: 'pending', resource: '71' })
  const view = executeSfc('../../teacher/TeacherResourcePanel.vue', {}, { useResourceContent: () => page, useRoute: () => ({ query: {} }) })
  const html = await renderToString(Vue.createSSRApp(view.component))
  assert.match(html, /教师账号没有资源审核权限/); assert.match(html, /暂时无法查看所选资源/)
  assert.doesNotMatch(html, /暂无符合筛选条件|Forbidden|internal_uuid/)
  assert.match(read('../../teacher/TeacherResourcePanel.vue'), /<ContentAreaNav/)
})
test('real shared challenge form renders every original field in create and edit modes', async () => {
  for (const mode of ['create', 'edit']) {
    const form = validForm()
    const view = executeSfc('./ChallengeEditor.vue', { role: 'teacher', mode, form, categories: [{ id: 3, name: '课程分类' }], busy: false })
    const html = await renderToString(Vue.createSSRApp(view.component))
    for (const label of ['标题', '分类', '难度', '分数', '题目描述', '答案', '提示', '状态', '环境镜像', '服务端口', '访问方式']) assert.ok(html.includes(label), label)
    assert.ok(html.includes('flag{teacher}')); assert.ok(html.includes('课程分类'))
    assert.ok(html.includes('答案暂不能在这里确认是否保存'))
  }
})
test('shared upload form emits complete multipart data including the real optional cover field', () => {
  const events = []
  const view = executeSfc('./ResourceUploadForm.vue', { role: 'teacher' }, { FormData, defineEmits: () => (...args) => events.push(args) })
  Object.assign(view.state.form, { title: '讲义', resource_type: 'document', category: '密码学', description: '课堂使用', tags: '基础,安全' })
  view.state.file.value = new Blob(['讲义']); view.state.cover.value = new Blob(['cover'], { type: 'image/png' })
  view.state.submit()
  assert.equal(events[0][0], 'upload')
  assert.deepEqual([...events[0][1].keys()], ['title', 'resource_type', 'category', 'description', 'tags', 'file', 'cover_image'])
  view.state.file.value = { size: 501 * 1024 * 1024 }; view.state.submit(); assert.equal(events.length, 1); assert.match(view.state.localError.value, /500MB/)
})
test('native content dialog opens modally, protects busy writes, closes and restores prior focus', () => {
  let mount, unmount, closes = 0, restored = 0, opened = 0, closed = 0
  const props = { title: '编辑题目', busy: true }
  const view = executeSfc('./ContentDialog.vue', props, {
    document: { activeElement: { isConnected: true, focus: () => restored++ } },
    onMounted: handler => { mount = handler }, onBeforeUnmount: handler => { unmount = handler },
    defineEmits: () => () => closes++,
  })
  view.state.dialog.value = { showModal: () => opened++, close: () => closed++, getBoundingClientRect: () => ({ left: 10, right: 100, top: 10, bottom: 100 }) }
  mount(); assert.equal(opened, 1)
  view.state.requestClose(); assert.equal(closes, 0)
  props.busy = false; view.state.requestClose(); assert.equal(closes, 1)
  view.state.onBackdrop({ target: view.state.dialog.value, clientX: 50, clientY: 50 }); assert.equal(closes, 1)
  view.state.onBackdrop({ target: view.state.dialog.value, clientX: 0, clientY: 0 }); assert.equal(closes, 2)
  unmount(); assert.equal(closed, 1); assert.equal(restored, 1)
})
test('resource preview retains all original metadata, download and review actions stay reachable', async () => {
  const view = executeSfc('./ResourcePreview.vue', { role: 'admin', resource: { id: 7, title: '讲义', resource_type: 'document', status: 'approved', category: '密码学', uploader_info: { username: '教师' }, created_at: '2026-11-03T00:00:00Z', file_size: 1024, view_count: 2, download_count: 1, description: '课堂使用' } })
  const html = await renderToString(Vue.createSSRApp(view.component))
  for (const text of ['讲义', '文档', '密码学', '教师', '上传时间', '文件大小', '查看', '下载', '资源描述', '课堂使用', '下载文件']) assert.ok(html.includes(text), text)
  for (const page of pages) assert.doesNotMatch(read(page), /api\.(?:get|post|put|delete)|from ['"]@\/api/)
  for (const role of ['teacher', 'admin']) {
    const page = read(role === 'teacher' ? '../../teacher/TeacherResourcePanel.vue' : '../../admin/views/Resources.vue')
    for (const tag of ['ResourceFilters', 'ResourceReviewList', 'ResourcePreview', 'ResourceUploadForm', 'ContentPagination']) assert.ok(page.includes(`<${tag}`), tag)
    if (role === 'admin') assert.ok(page.includes('<ResourceReviewDialog'))
    else { assert.doesNotMatch(page, /ResourceReviewDialog|@review=/); assert.match(page, /请联系管理员处理审核/) }
    assert.ok(page.includes(`useResourceContent('${role}')`)); assert.ok(page.includes('route.query.status'))
  }
})


test('teacher review actions are absent and forced confirmation never submits, while administrator actions remain', async () => {
  let writes = 0
  const page = resource('teacher', { reviewResource: async () => writes++ })
  page.review({ id: 7 }, 'approved')
  assert.equal(page.state.review, null)
  page.state.review = { item: { id: 7 }, action: 'approved' }
  await page.confirmReview()
  assert.equal(writes, 0)
  for (const role of ['teacher', 'admin']) {
    const view = executeSfc('./ResourceReviewList.vue', { role, items: [{ id: 7, title: '课程资料', status: 'pending' }] })
    const html = await renderToString(Vue.createSSRApp(view.component))
    assert.ok(html.includes('查看'))
    if (role === 'teacher') { assert.doesNotMatch(html, />通过<|>拒绝</); assert.match(html, /等待管理员审核/) }
    else { assert.match(html, />通过</); assert.match(html, />拒绝</) }
  }
  page.destroy()
})
