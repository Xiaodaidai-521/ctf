import { createAccountGuard, onAccountClear, syncStateAccount } from '../../shared/state/accountScope.js'
import { persistPath, pathSaveError } from '../../shared/paths/savePath.js'
import { uiSnapshot } from '../../shared/state/retention.js'
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compile, computed, createSSRApp, h, reactive, ref, watch } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { compileScript, compileTemplate, parse } from 'vue/compiler-sfc'
import { prepareTeachingTransfer, consumeTeachingTransfer, clearTeachingTransfer, teachingIdentity } from '../../shared/knowledge/teachingTransfer.js'

const read = file => readFileSync(new URL(file, import.meta.url), 'utf8')
const plain = value => JSON.parse(JSON.stringify(value))
const tick = () => new Promise(resolve => setImmediate(resolve))
const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no }); return { promise, resolve, reject } }
const files = { editor: '../../shared/paths/PathManageEditor.vue', list: '../../shared/paths/PathManageList.vue' }
const exposed = {
  editor: 'props, names, renameCopy, pathForm, chapters, isNewPath, saveError, saveUncertain, loading, loadError, saving, notice, challengeError, categoryError, challengesLoading, availableChallenges, categories, challengeSearch, challengeFilterCategory, filteredChallenges, selectedChallengesCount, tempSelectedChallengeIds, editingChapterIndex, pathInfoExpanded, activeChapterId, challengeSelectorVisible, confirmModalVisible, addChapter, moveChapterUp, moveChapterDown, deleteChapter, confirmDelete, openChallengeSelector, toggleChallengeSelection, confirmChallengeSelection, removeChallenge, togglePrerequisite, isPrerequisiteSelected, loadPathData, loadChallenges, loadCategories, savePath, goBack, getModuleTypeLabel, getDifficultyBadgeClass',
  list: 'props, names, loading, loaded, loadError, paths, stats, searchQuery, filterDifficulty, filterStatus, filteredPaths, deleting, confirmModalVisible, loadLearningPaths, createPath, editPath, viewPath, goBack, deletePath, confirmDelete, validNumber, getDifficultyLabel, resetFilters',
}
function page(kind, options = {}) {
  const script = parse(read(files[kind])).descriptor.scriptSetup.content.replace(/^import .*$/gm, '')
  let mounted, unmount
  const routes = []
  const route = reactive({ path: '/teacher/learning-paths', params: {}, query: {}, ...options.route })
  const props = { api: { list: async () => [], challenges: async () => [], categories: async () => [], ...options.api }, managementBase: '/teacher/learning-paths', home: '/teacher', ...options.props }
  const state = runInNewContext(`${script}\n;({ ${exposed[kind]} })`, {
    createAccountGuard, onAccountClear, persistPath, pathSaveError, uiSnapshot, ref, reactive, computed, watch, defineProps: () => props, useRoute: () => route,
    useRouter: () => ({ push: value => routes.push(value), replace: async value => { routes.push(value); route.params.id = value.split('/').at(-2) } }),
    onMounted: fn => { mounted = fn }, onBeforeUnmount: fn => { unmount = fn },
    names: { paths: '学习航线' }, renameCopy: value => value, alert: options.alert || (() => {}), console,
  })
  return { state, routes, route, mount: () => mounted(), unmount: () => unmount() }
}
async function visible(kind, state) {
  const app = createSSRApp({ render: compile(parse(read(files[kind])).descriptor.template.content), setup: () => state })
  app.component('AppIcon', { props: ['name'], render: () => h('span') })
  return (await renderToString(app)).replace(/<[^>]*>/g, '')
}

for (const file of [...Object.values(files), 'LearningPathsManage.vue', 'LearningPathsManageList.vue', '../../views/LearningPaths/LearningPathsManage.vue', '../../views/LearningPaths/LearningPathsManageList.vue']) {
  test(`${file}: complete management and compatibility entries compile`, () => {
    const { descriptor, errors } = parse(read(file))
    assert.deepEqual(errors, [])
    assert.ok(compileScript(descriptor, { id: file }).content)
    assert.deepEqual(compileTemplate({ source: descriptor.template.content, filename: file, id: file }).errors, [])
    assert.doesNotMatch(read(file), /@\/admin\/|@\/api['"]|fetch\(|axios\./)
  })
}

test('path list has one primary creation action and secondary per-record edits', () => {
  const source = read(files.list)
  assert.equal((parse(source).descriptor.template.content.match(/btn-primary/g) || []).length, 1)
  assert.match(source, /class="action-btn btn-secondary" @click="editPath\(path.id\)"/)
  assert.match(source, /搜索航线名称/)
  assert.match(read(files.editor), /航线标题<\/label>/)
  assert.match(read(files.editor), /航线描述<\/label>/)
})
test('management failure is not an empty list or zero statistics; success can be retried', async () => {
  let fail = true
  const { state: p } = page('list', { api: { list: async () => { if (fail) throw new Error('private failure'); return [] } } })
  let text = await visible('list', p)
  assert.match(text, /读取中/)
  assert.doesNotMatch(text, /暂无可管理/)
  await p.loadLearningPaths()
  text = await visible('list', p)
  assert.match(text, /未能完整读取/)
  assert.doesNotMatch(text, /暂无可管理|可管理航线0|private failure/)
  fail = false
  await p.loadLearningPaths()
  assert.equal(p.loaded.value, true)
  assert.equal(p.stats.value.total, 0)
  assert.match(await visible('list', p), /暂无可管理/)
})

test('missing enrolment is not zero, real zero is retained, and draft URL filter is reactive', async () => {
  const { state: p, route } = page('list', { route: { query: { status: 'draft' } }, api: { list: async () => [
    { id: 1, title: '草稿', difficulty: 'AP', is_published: false, enrollment_count: 0 },
    { id: 2, title: '公开', difficulty: 'EX', is_published: true },
    { id: 3, title: '待确认' },
  ] } })
  await p.loadLearningPaths()
  assert.deepEqual(p.filteredPaths.value.map(item => item.id), [1])
  assert.equal(p.stats.value.enrolled, null)
  const text = await visible('list', p)
  assert.match(text, /0 人在学/)
  route.query.status = 'published'
  await tick()
  assert.deepEqual(p.filteredPaths.value.map(item => item.id), [2])
  assert.match(await visible('list', p), /未提供 人在学/)
  p.paths.value[1].enrollment_count = 2
  p.paths.value[2].enrollment_count = 0
  assert.equal(p.stats.value.enrolled, 2)
  route.query.status = 'private-enum'
  await tick()
  assert.equal(p.filterStatus.value, '')
  p.searchQuery.value = '草'
  p.filterDifficulty.value = 'AP'
  assert.equal(p.filteredPaths.value.length, 1)
  p.resetFilters()
  assert.equal(p.filteredPaths.value.length, 3)
})

test('management list ignores late success and failure, including after unmount', async () => {
  const pending = [deferred(), deferred(), deferred()]
  let index = 0
  const p = page('list', { api: { list: () => pending[index++].promise } })
  const first = p.state.loadLearningPaths(), second = p.state.loadLearningPaths()
  pending[1].resolve([{ id: 2 }]); await second
  pending[0].reject(new Error('old')); await first
  assert.deepEqual(p.state.paths.value.map(row => row.id), [2])
  assert.equal(p.state.loadError.value, '')
  const third = p.state.loadLearningPaths(); p.unmount()
  pending[2].resolve([{ id: 3 }]); await third
  // Authorized records are explicitly cleared on unmount, never restored by late work.
  assert.equal(p.state.paths.value.length, 0)
})

test('teacher CRUD destinations stay in teacher layout, old admin neutral entries retain old CRUD', () => {
  const p = page('list')
  p.state.createPath(); p.state.editPath(7); p.state.viewPath(7); p.state.goBack()
  assert.deepEqual(p.routes, ['/teacher/learning-paths/new', '/teacher/learning-paths/7/edit', '/learning-paths/7', '/teacher'])
  const admin = page('list', { props: { managementBase: '/learning-paths', home: '/admin/dashboard' } })
  admin.state.createPath(); admin.state.editPath(7); admin.state.goBack()
  assert.deepEqual(admin.routes, ['/learning-paths/new', '/learning-paths/7/edit', '/admin/dashboard'])
  assert.match(read('../../views/LearningPaths/LearningPathsManage.vue'), /\/learning-paths\/manage/)
})

test('deletion confirms once, preserves original id, and distinguishes failed readback from successful delete', async () => {
  const pending = deferred(), calls = [], messages = []
  const { state: p } = page('list', { alert: message => messages.push(message), api: {
    delete: id => { calls.push(id); return pending.promise }, list: async () => { throw new Error('read failed') },
  } })
  p.deletePath({ id: 7, title: '原航线' })
  const request = p.confirmDelete(); await p.confirmDelete()
  assert.deepEqual(calls, [7])
  pending.resolve({}); await request
  assert.match(messages[0], /删除已完成.*列表读取失败/)
  assert.equal(p.deleting.value, false)
})

test('new path confirms persistence, replaces new URL, survives reload and saves an additional chapter', async () => {
  let savedPath, modules = [], nextId = 10
  const calls = []
  const api = {
    create: async body => { calls.push('POST path'); savedPath = { ...body, id: 7, slug: 'generated-path' }; return savedPath },
    update: async (id, body) => { calls.push('PUT path'); savedPath = { ...savedPath, ...body }; return savedPath },
    createModule: async body => { calls.push('POST module'); const row = { ...body, id: nextId++ }; modules.push(row); return row },
    updateModule: async (id, body) => { calls.push('PUT module'); const row = { ...modules.find(m => m.id === id), ...body }; modules = modules.map(m => m.id === id ? row : m); return row },
    detail: async () => savedPath, modules: async () => modules,
  }
  const p = page('editor', { route: { params: {} }, api })
  await p.state.loadPathData()
  Object.assign(p.state.pathForm, { title: '唯一教学航线', description: '教学目标', is_published: false })
  p.state.addChapter(); Object.assign(p.state.chapters.value[0], { title: '第一章', content: '第一章正文' })
  await p.state.savePath(); await tick()
  assert.deepEqual(p.routes, ['/teacher/learning-paths/7/edit'])
  assert.equal(p.state.saving.value, false); assert.equal(p.state.saveError.value, '')
  assert.match(p.state.notice.value, /已保存.*草稿/)
  assert.equal(p.state.pathForm.slug, 'generated-path')
  const reload = page('editor', { route: { params: { id: 7 } }, api })
  await reload.state.loadPathData()
  assert.equal(reload.state.pathForm.title, '唯一教学航线'); assert.equal(reload.state.chapters.value.length, 1)
  reload.state.addChapter(); Object.assign(reload.state.chapters.value[1], { title: '第二章', content: '第二章正文' })
  await reload.state.savePath()
  assert.equal(modules.length, 2); assert.deepEqual(calls, ['POST path', 'POST module', 'PUT path', 'PUT module', 'POST module'])
  reload.state.pathForm.is_published = true; await reload.state.savePath()
  assert.match(reload.state.notice.value, /已发布，学生可见/)
})
test('confirmed creation feedback survives keyed route remount once and never crosses accounts', async () => {
  syncStateAccount({ id: 90001, role: 'teacher' })
  const saved = { id: 71, title: '新航线', slug: 'generated', description: '教学目标', difficulty: 'AP', estimated_hours: 10, color: '#B7352D', is_published: false }
  let module
  const api = { create: async () => saved, createModule: async body => { module = { ...body, id: 11 }; return module }, detail: async () => saved, modules: async () => [module] }
  try {
    const p = page('editor', { api }); await p.state.loadPathData()
    Object.assign(p.state.pathForm, saved, { id: null }); p.state.addChapter()
    Object.assign(p.state.chapters.value[0], { title: '新章节', content: '新正文' })
    await p.state.savePath(); p.unmount()
    const mounted = page('editor', { route: { params: { id: 71 } }, api }); await mounted.state.loadPathData()
    assert.match(mounted.state.notice.value, /已保存.*草稿/)
    await mounted.state.loadPathData(); assert.equal(mounted.state.notice.value, '')
    uiSnapshot('paths:saved:/teacher/learning-paths:71').write(true)
    syncStateAccount({ id: 90002, role: 'teacher' })
    const next = page('editor', { route: { params: { id: 71 } }, api }); await next.state.loadPathData()
    assert.equal(next.state.notice.value, '')
  } finally { syncStateAccount(null) }
})
test('changing editor route clears previous private data and ignores late reads', async () => {
  const pending = deferred()
  const p = page('editor', { route: { params: { id: 7 } }, api: { detail: () => pending.promise, modules: async () => [] } })
  const reading = p.state.loadPathData()
  p.state.pathForm.title = '旧私有航线'; p.route.params.id = 'new'
  assert.equal(p.state.pathForm.title, ''); assert.equal(p.state.pathForm.id, null)
  pending.resolve({ id: 7, title: '晚到的私有航线' }); await reading
  assert.equal(p.state.pathForm.title, ''); assert.equal(p.state.isNewPath.value, true)
})
test('editor waits for chapters and fails atomically without exposing an empty editable replacement', async () => {
  const messages = []
  const { state: p } = page('editor', { route: { params: { id: 7 } }, alert: message => messages.push(message), api: {
    detail: async () => ({ title: '已读取基本字段' }), modules: async () => { throw new Error('private') },
  } })
  await p.loadPathData()
  assert.equal(p.pathForm.title, '')
  assert.match(p.loadError.value, /章节未能完整读取/)
  await p.savePath()
  assert.deepEqual(messages, [])
  assert.match(await visible('editor', p), /暂不能编辑或保存/)
})

test('chapters retain content, order, prerequisites, hints and existing labs outside active options', async () => {
  const { state: p } = page('editor')
  await p.loadPathData(); await p.loadChallenges()
  p.addChapter(); p.addChapter()
  assert.notEqual(p.chapters.value[0].id, p.chapters.value[1].id)
  const first = p.chapters.value[0]
  p.togglePrerequisite(1, first.id)
  assert.equal(p.isPrerequisiteSelected(p.chapters.value[1], first.id), true)
  p.moveChapterUp(1); p.moveChapterDown(0)
  assert.deepEqual(plain(p.chapters.value.map(c => c.order)), [0, 1])
  first.challenges = [{ id: 9, title: '已下架但原先关联的实验', points: 10 }]
  p.availableChallenges.value = [{ id: 10, title: '新的实验', category: { id: 2, name: 'Web' } }]
  p.openChallengeSelector(0)
  p.toggleChallengeSelection(p.availableChallenges.value[0])
  assert.equal(p.selectedChallengesCount.value, 2)
  p.confirmChallengeSelection()
  assert.deepEqual(plain(p.chapters.value[0].challenges.map(c => c.id)), [9, 10])
  p.challengeSearch.value = '新的'; p.challengeFilterCategory.value = '2'
  assert.equal(p.filteredChallenges.value.length, 1)
  p.removeChallenge(0, 1)
  assert.deepEqual(plain(p.chapters.value[0].challenges.map(c => c.id)), [9])
})

test('knowledge transfer creates a source-attributed unposted chapter after loading, never publishes', async () => {
  let consumed = 0
  const p = page('editor', { props: { takeDraft: () => { consumed++; return {
    title: '访问控制', text: '完整原文', source: { title: '教学资料', publisher: '出版方', source_version: '第二版', license_id: 'CC-BY', source_url: 'https://example.test/source', attribution_text: '原作者' },
  } } } })
  await p.mount()
  assert.equal(consumed, 1)
  assert.equal(p.state.pathForm.is_published, false)
  assert.equal(p.state.chapters.value.length, 1)
  const chapter = p.state.chapters.value[0]
  for (const text of ['教学目标', '完整原文', '练习', '检验', '教学资料', '第二版', 'CC-BY', '原作者']) assert.ok(chapter.content.includes(text))
  assert.equal(chapter.source.source_version, '第二版')
  assert.match(p.state.notice.value, /尚未保存或发布/)
  assert.match(read('LearningPathsManage.vue'), /consumeTeachingTransfer\(teachingIdentity\(userStore.userInfo\), 'path'\)/)
})

test('management API traverses existing paginated clients without fetching next URLs or dropping failures', async () => {
  const apiSource = read('../../shared/paths/api.js').replace(/^import .*$/gm, '').replace(/^export /gm, '').replace(/default createPathManagementApi\(\)/, '')
  const calls = []
  const { createPathManagementApi } = runInNewContext(`${apiSource}\n;({ createPathManagementApi })`, { client: {}, Object, Array })
  const api = createPathManagementApi({ learningPaths: {
    list: async params => { calls.push(plain(params)); return { results: [{ id: params.page }], next: params.page === 1 ? 'https://untrusted.test/page2' : null } },
    delete: id => id,
  } })
  assert.deepEqual(plain(await api.list()), [{ id: 1 }, { id: 2 }])
  assert.deepEqual(calls, [{ page: 1 }, { page: 2 }])
  assert.equal(api.delete(7), 7)
  const bad = createPathManagementApi({ learningPaths: { list: async () => ({ results: [], next: '/unread/' }) } })
  await assert.rejects(bad.list(), /尚未完整读取/)
})

test('editor normalizes all chapter payloads before replacing the path and ignores overlapping reads', async () => {
  let malformed = true
  const p = page('editor', { route: { params: { id: 'path-original' } }, api: {
    detail: async () => ({ title: '不得局部写入', slug: 'original-slug' }),
    modules: async () => malformed ? [{ module_labs: {} }] : [{ id: 1, title: '真实章节', module_labs: [] }],
  } })
  await p.state.loadPathData()
  assert.equal(p.state.pathForm.title, '')
  assert.equal(p.state.chapters.value.length, 0)
  assert.match(p.state.loadError.value, /暂不能编辑或保存/)
  malformed = false; await p.state.loadPathData()
  assert.equal(p.state.chapters.value[0].title, '真实章节')
  const reads = [deferred(), deferred(), deferred()]; let index = 0
  const raced = page('editor', { route: { params: { id: 7 } }, api: {
    detail: () => reads[index++].promise, modules: async () => [],
  } })
  const first = raced.state.loadPathData(), second = raced.state.loadPathData()
  reads[0].reject(new Error('old')); await first
  assert.equal(raced.state.loading.value, true)
  assert.equal(raced.state.loadError.value, '')
  reads[1].resolve({ title: '新读取' }); await second
  assert.equal(raced.state.pathForm.title, '新读取')
  const third = raced.state.loadPathData(); raced.unmount()
  reads[2].resolve({ title: '已卸载' }); await third
  assert.equal(raced.state.pathForm.title, '')
})

test('challenge and category retries ignore older results and failures without clearing newer pending state', async () => {
  const challenges = [deferred(), deferred(), deferred()], categories = [deferred(), deferred(), deferred()]
  let c = 0, k = 0
  const p = page('editor', { api: { challenges: () => challenges[c++].promise, categories: () => categories[k++].promise } })
  const oldChallenges = p.state.loadChallenges(), newChallenges = p.state.loadChallenges()
  const oldCategories = p.state.loadCategories(), newCategories = p.state.loadCategories()
  challenges[0].reject(new Error('old')); categories[0].reject(new Error('old'))
  await Promise.all([oldChallenges, oldCategories])
  assert.equal(p.state.challengesLoading.value, true)
  assert.equal(p.state.challengeError.value, '')
  assert.equal(p.state.categoryError.value, '')
  challenges[1].resolve([{ id: 2, title: '新实验' }]); categories[1].resolve([{ id: 2, name: '新分类' }])
  await Promise.all([newChallenges, newCategories])
  assert.equal(p.state.availableChallenges.value[0].id, 2)
  assert.equal(p.state.categories.value[0].id, 2)
  const lateChallenges = p.state.loadChallenges(), lateCategories = p.state.loadCategories(); p.unmount()
  challenges[2].resolve([{ id: 3 }]); categories[2].resolve([{ id: 3 }])
  await Promise.all([lateChallenges, lateCategories])
  assert.equal(p.state.availableChallenges.value.length, 0)
  assert.equal(p.state.categories.value[0].id, 2)
})

test('chapter selector and confirmation retain target identity across reorder and remove only dangling dependencies once', async () => {
  const { state: p } = page('editor')
  await p.loadPathData(); await p.loadChallenges()
  p.addChapter(); p.addChapter(); p.addChapter()
  const [first, second, third] = p.chapters.value
  p.togglePrerequisite(1, first.id); p.togglePrerequisite(2, first.id)
  p.openChallengeSelector(0)
  p.availableChallenges.value = [{ id: 72, title: '关联实验' }]
  p.toggleChallengeSelection(p.availableChallenges.value[0])
  p.moveChapterDown(0)
  p.confirmChallengeSelection()
  assert.deepEqual(plain(first.challenges.map(item => item.id)), [72])
  assert.equal(second.challenges.length, 0)
  p.deleteChapter(1)
  p.moveChapterDown(1)
  await p.confirmDelete(); await p.confirmDelete()
  assert.deepEqual(plain(p.chapters.value.map(item => item.id)), [second.id, third.id])
  assert.deepEqual(plain(p.chapters.value.map(item => item.prerequisites)), [[], []])
  assert.deepEqual(plain(p.chapters.value.map(item => item.order)), [0, 1])
})

test('knowledge draft does not wait for optional bank and is consumed only once on reload, never into existing paths', async () => {
  const bank = deferred(); let consumed = 0
  const incoming = { title: '教学资料', text: '授权完整原文', source: { attribution_text: '原作者', license_id: 'CC-BY', source_version: '原始版本' } }
  const p = page('editor', { props: { takeDraft: () => { consumed++; return incoming } }, api: { challenges: () => bank.promise } })
  const mounting = p.mount(); await tick()
  assert.equal(p.state.chapters.value.length, 1)
  assert.equal(p.state.chapters.value[0].source.source_version, '原始版本')
  assert.equal(p.state.challengesLoading.value, true)
  assert.equal(p.state.pathForm.is_published, false)
  await p.state.loadPathData()
  assert.equal(consumed, 1)
  assert.equal(p.state.chapters.value.length, 1)
  bank.resolve([]); await mounting
  const existing = page('editor', { route: { params: { id: 7 } }, props: { takeDraft: () => { consumed++; return incoming } }, api: { detail: async () => ({ title: '已发布航线', is_published: true }), modules: async () => [{ id: 1, title: '已有章节', content: '已有正文' }] } })
  await existing.mount()
  assert.equal(consumed, 1)
  assert.equal(existing.state.pathForm.is_published, true)
  assert.equal(existing.state.chapters.value[0].content, '已有正文')
})

test('teacher transfer receiver rechecks current role and identity without importing after an account switch', () => {
  const teacher = { id: 2, role: 'teacher' }
  const userStore = reactive({ userInfo: teacher })
  const route = reactive({ query: { from: 'knowledge' } })
  const source = parse(read('LearningPathsManage.vue')).descriptor.scriptSetup.content.replace(/^import .*$/gm, '')
  const { takeKnowledgeDraft } = runInNewContext(`${source}\n;({ takeKnowledgeDraft })`, { useRoute: () => route, useUserStore: () => userStore, consumeTeachingTransfer, teachingIdentity })
  try {
    for (const user of [{ id: 2, role: 'student' }, { id: 2, role: 'admin' }, { role: 'teacher' }, { id: 3, role: 'teacher' }]) {
      prepareTeachingTransfer(teacher, 'path', { title: '真实资料', full_text: '真实授权全文', material_class: 'lesson' })
      userStore.userInfo = user
      assert.equal(takeKnowledgeDraft(), null)
    }
    prepareTeachingTransfer(teacher, 'path', { title: '真实资料', full_text: '真实授权全文', material_class: 'lesson' })
    userStore.userInfo = teacher
    assert.equal(takeKnowledgeDraft().text, '真实授权全文')
    assert.equal(takeKnowledgeDraft(), null)
  } finally { clearTeachingTransfer() }
})

test('path editor displays航线copy and no internal colour codes while retaining the exact colour input value', async () => {
  const { state: p } = page('editor')
  await p.loadPathData()
  const original = p.pathForm.color
  const text = await visible('editor', p)
  assert.match(text, /航线基本信息/)
  assert.doesNotMatch(text, /路径基本信息|#[\da-f]{6}\b/i)
  assert.equal(p.pathForm.color, original)
  assert.match(parse(read(files.editor)).descriptor.template.content, /v-model="pathForm.color"[\s\S]*?type="color"/)
})
