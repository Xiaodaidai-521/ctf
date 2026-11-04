import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { compile, createSSRApp, h } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { parse } from 'vue/compiler-sfc'
import { renderToString } from 'vue/server-renderer'
import { canManageLibrary, classLabel, formatLocator, initialLibraryState, libraryError, sourceText, statusLabel } from './libraryController.js'

// Render the actual page template with small presentation-only component stubs.
// Endpoint decisions and request lifecycle are exercised by libraryController.test.js.
const source = readFileSync(new URL('./KnowledgeLibrary.vue', import.meta.url), 'utf8')
const render = compile(parse(source).descriptor.template.content)
const routerLink = { props: ['to'], setup: (props, { slots }) => () => h('a', { href: typeof props.to === 'string' ? props.to : '#' }, slots.default?.()) }
async function pageFor(role, overrides = {}, view = {}) {
  const app = createSSRApp({
    render,
    setup: () => ({
      state: { ...initialLibraryState(), ...overrides }, user: { userInfo: { role } },
      managing: canManageLibrary(role), paused: false, sessionChanged: false,
      resourcePath: '/resources', groupTitle: '资料', groupDescription: '来源与授权',
      emptyNotice: '等待授权检索', internalSourcePath: '', externalSourceUrl: '',
      controller: {}, privacy: {}, fileInput: null, classLabel, statusLabel, formatLocator, libraryError, sourceText,
      changeGroup() {}, resume() {}, closeUpload() {}, chooseFile() {}, resetSearch() {}, ...view,
    }),
  })
  app.component('router-link', routerLink)
  for (const name of ['a-tabs', 'a-alert', 'a-tag', 'a-select', 'a-option']) {
    app.component(name, { setup: (_, { slots }) => () => h('div', [slots.title?.(), slots.default?.()]) })
  }
  app.component('a-tab-pane', { props: ['title', 'disabled'], setup: props => () => h('button', { disabled: props.disabled }, props.title) })
  app.component('a-button', { props: ['disabled'], setup: (props, { slots }) => () => h('button', { disabled: props.disabled }, slots.default?.()) })
  app.component('a-input', { props: ['modelValue'], setup: props => () => h('input', { value: props.modelValue }) })
  app.component('a-empty', { props: ['description'], setup: props => () => h('p', props.description) })
  return renderToString(app)
}

for (const role of ['student', 'guest', undefined]) {
  test(`${role}: library renders no UI, even with old results and upload state`, async () => {
    const html = await pageFor(role, {
      uploadOpen: true, rows: [{ id: 1, title: '旧资料标题' }], detail: { title: '旧资料详情' },
    })
    assert.doesNotMatch(html, /<(?:main|section|header|form|input|button|a)\b|知识资料库|旧资料/)
  })
}

test('teacher rendered page offers upload and existing material review without staff-only choice', async () => {
  const html = await pageFor('teacher', { uploadOpen: true })
  assert.match(html, /上传文档入库/)
  assert.match(html, /href="\/teaching-knowledge"/)
  assert.match(html, /学习资料/)
  assert.match(html, /法律库/)
  assert.match(html, /平台资料/)
  assert.doesNotMatch(html, /仅后台人员|\/admin\/legal\/kb\/tools|任务尝试 UUID/)
})

test('admin legal view retains a contextual link to original tools', async () => {
  const html = await pageFor('admin', { group: 'legal', uploadOpen: true })
  assert.match(html, /href="\/admin\/legal\/kb\/tools"/)
  assert.match(html, /仅后台人员/)
  assert.match(html, /上传文档入库/)
})

test('catalog strings and ingestion failures render as escaped text, never executable HTML', async () => {
  const html = await pageFor('teacher', {
    group: 'legal', uploadOpen: true,
    rows: [{ id: 'document:1', title: '<script>alert(1)</script>', excerpt: '<img src=x onerror=alert(1)>', locator: 'section 1' }],
    uploadResult: { id: 1, status: 'failed', chunk_count: 0, embedded_count: 0, error_message: '<script>embedding failure</script>' },
  })
  assert.match(html, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/)
  assert.match(html, /&lt;img src=x onerror=alert\(1\)&gt;/)
  assert.match(html, /文档处理失败，请检查文件内容或联系管理员/)
  assert.match(html, /文档入库未完成/)
  assert.doesNotMatch(html, /<script>|<img src=x|文档已入库|embedding failure/)
})

const engineeringCopy = /KNOWLEDGE LIBRARY|SOURCE \/|UUID|段落引用|课程目录|索引|嵌入|embedding|Scope|CSRF|服务器|内存|失焦|纯文本|preview_notice|paragraph|legacy_lexical/
for (const role of ['teacher', 'admin']) {
  test(`${role}: teaching cards and details hide identifiers but retain provenance and text`, async () => {
    const material = {
      material_id: '9e2068b7-0000-4000-8000-000000000001', revision: 2, catalog_version: 'm2-catalog-m3',
      title: '授权测试讲义', material_class: 'lesson', review_status: 'published',
      publisher: '课程教研组', source_version: '2026 年版', license_id: 'CC-BY-4.0', attribution_text: '实训团队',
      applicability: '课堂实训', source_url: 'https://example.com/private-id', source_ref: 'evidence-123',
      preview_notice: '管理审阅不代表学生可读；学生预览必须使用其真实尝试和课程授权。',
      chunks: [{ chunk_ref: 'evidence-456', locator: { paragraph: 1, private_key: 'hidden-value' }, text: '<script>原文保持纯文本</script>' }],
    }
    const html = await pageFor(role, { rows: [material], detail: material }, { externalSourceUrl: 'https://example.com/private-id' })
    const text = html.replace(/<[^>]*>/g, '')
    // Source prose is not rewritten; only labels/metadata are cleaned.
    assert.doesNotMatch(text.replace('原文保持纯文本', ''), engineeringCopy)
    assert.doesNotMatch(text, /9e2068b7|m2-catalog-m3|evidence-|hidden-value|private-id|管理审阅不代表/)
    for (const expected of ['授权测试讲义', '第 2 版', '课程教研组', '2026 年版', 'CC-BY-4.0', '实训团队', '段落 1']) assert.ok(text.includes(expected))
    assert.match(html, /&lt;script&gt;原文保持纯文本&lt;\/script&gt;/)
    assert.match(html, /href="https:\/\/example.com\/private-id"/)
    assert.match(html, /href="\/teaching-knowledge"/)
  })

  test(`${role}: all library source types retain chapters and links without implementation metadata`, async () => {
    for (const source_type of ['legal_document', 'document', 'article', 'resource', 'knowledge_concept']) {
      const detail = {
        id: 'internal-id', source_type, source_label: '资料', title: '示例来源', status: 'legacy_lexical',
        source_path: '/capability-map?concept=789', locator: source_type === 'legal_document' ? '第一章 / 第三条 / clause-key-1' : '索引块 2（原文定位待补齐）',
        chunks: [{ id: 'embedding:789', locator: '索引块 2（原文定位待补齐）', index_status: 'legacy_lexical', location_notice: '内部定位说明', text: '来源正文' }],
      }
      const html = await pageFor(role, { group: ['article', 'resource', 'knowledge_concept'].includes(source_type) ? 'platform' : 'legal', rows: [detail], detail }, { internalSourcePath: detail.source_path })
      const text = html.replace(/<[^>]*>/g, '')
      assert.doesNotMatch(text, engineeringCopy)
      assert.doesNotMatch(text, /internal-id|clause-key|789|内部定位说明|capability-map/)
      assert.match(text, /段落 2|第一章 \/ 第三条/)
      assert.match(text, /来源正文/)
      assert.match(html, /href="\/capability-map\?concept=789"/)
    }
  })
}

test('upload, errors and paused views use actionable copy without changing success criteria', async () => {
  for (const status of ['completed', 'failed', 'running']) {
    const html = await pageFor('admin', { uploadOpen: true, uploadResult: {
      id: 'document-uuid', title: '上传讲义', status, chunk_count: 3, embedded_count: 2,
      error_message: status === 'failed' ? 'EMBEDDING_PROVIDER missing: document-uuid' : '',
    } })
    assert.doesNotMatch(html.replace(/<[^>]*>/g, ''), engineeringCopy)
    assert.doesNotMatch(html, /document-uuid|解析块|已嵌入|任务状态/)
    if (status === 'completed') assert.match(html, /文档已入库/)
    else {
      assert.match(html, /文档入库未完成/)
      assert.doesNotMatch(html, /文档已入库/)
    }
  }
  const denied = await pageFor('teacher', { error: '服务器拒绝访问或 CSRF 校验失败；客户端不能授予权限。' })
  assert.match(denied, /请确认账号权限/)
  assert.doesNotMatch(denied, engineeringCopy)
  for (const sessionChanged of [true, false]) {
    const paused = await pageFor('teacher', {}, { paused: true, sessionChanged })
    assert.match(paused, /请重新加载资料/)
    assert.match(paused, sessionChanged ? /刷新页面/ : /重新加载/)
    assert.doesNotMatch(paused, engineeringCopy)
  }
})

test('resource projection type codes use Chinese labels without changing source prose', async () => {
  const text = '标题\nRead the document carefully.\n分类\n\ndocument'
  assert.equal(sourceText(text, 'resource'), '标题\nRead the document carefully.\n分类\n\n文档')
  assert.equal(sourceText(text, 'article'), text)
  assert.equal(sourceText('Read the document', 'resource'), 'Read the document')
  const row = { id: 1, source_type: 'resource', title: '资源标题', excerpt: text, chunks: [{ text }] }
  const html = await pageFor('teacher', { group: 'platform', rows: [row], detail: row })
  assert.match(html, /Read the document carefully/)
  assert.doesNotMatch(html, /\ndocument/)
  assert.match(html, /文档/)
})

test('locator display accepts meaningful positions, never serializes arbitrary metadata', () => {
  assert.equal(formatLocator({ paragraph: 1, evidence_id: 'private-id' }), '段落 1')
  assert.equal(formatLocator({ chapter: '第一章', article_number: '第三条', page: 2 }), '第一章 / 第三条 / 页 2')
  assert.equal(formatLocator({ heading_path: ['Introduction', '第一节'], paragraph: 3 }), 'Introduction / 第一节 / 段落 3')
  assert.equal(formatLocator('知识点 · sql-injection'), '知识点')
  for (const value of [undefined, null, {}, { internal_id: 'private' }, { paragraph: 'evidence-id' }, ['private'], 'm2-catalog-m3']) assert.equal(formatLocator(value), '')
})

test('display errors keep failures and unknown upload outcomes explicit without raw diagnostics', () => {
  for (const message of ['EMBEDDING_PROVIDER missing', '解析失败']) assert.match(libraryError(message), /处理失败/)
  assert.match(libraryError('请求未完成，未确认服务器结果'), /结果尚未确认.*先核对资料列表/)
  assert.match(libraryError('服务器未接受请求：catalog_version: m2-catalog-m3'), /提交内容有误/)
  assert.match(libraryError('文件超过服务器允许的大小。'), /文件过大/)
  assert.equal(statusLabel('internal-status'), '未提供')
  assert.equal(classLabel('internal-class'), '教学材料')
})

async function headerFor(file, setup) {
  const template = parse(readFileSync(new URL(file, import.meta.url), 'utf8')).descriptor.template.content
  const header = template.slice(template.indexOf('<header'), template.indexOf('</header>') + '</header>'.length)
  const app = createSSRApp({ render: compile(header), setup })
  app.component('router-link', routerLink)
  return renderToString(app)
}

for (const role of ['student', 'guest', 'teacher', 'admin']) {
  test(`resource entry renders only for teachers/admins: ${role}`, async () => {
    const resourceSource = readFileSync(new URL('../views/Resources.vue', import.meta.url), 'utf8')
    const check = resourceSource.match(/const isTeacherOrAdmin = computed\(\(\) => \{([\s\S]*?)\n\}\)/)[1]
    const userStore = { userInfo: { role } }
    const isTeacherOrAdmin = runInNewContext(`(() => {${check}})()`, { userStore })
    const html = await headerFor('../views/Resources.vue', () => ({
      userStore, isTeacherOrAdmin, hasAISurfacedResources: false, resetTutorHighlights() {}, handleUpload() {},
    }))
    if (role === 'teacher' || role === 'admin') {
      assert.match(html, /知识资料库/)
      assert.ok(html.includes(`href="${role === 'teacher' ? '/teacher/knowledge' : '/admin/legal/kb'}"`))
    } else {
      assert.doesNotMatch(html, /知识资料库|\/knowledge|\/admin\/legal\/kb/)
    }
  })
}

test('existing task evidence header retains feedback, not a library entry', async () => {
  const html = await headerFor('./LearningKnowledge.vue', () => ({ attemptId: 'real-task-id' }))
  assert.match(html, /当前任务的学习证据/)
  assert.match(html, /href="\/feedback"/)
  assert.doesNotMatch(html, /资料库|\/knowledge/)
})

function routerFor(user) {
  const source = readFileSync(new URL('../router/index.js', import.meta.url), 'utf8')
  return runInNewContext(source.trimStart().replace(/^import .*$/gm, '').replace('export default router', 'router'), {
    createRouter: options => ({ ...options, beforeEach(guard) { this.guard = guard } }),
    createWebHistory: () => ({}), useUserStore: () => user, document: {},
    TeacherLayout: {}, TeacherDashboard: {}, LearningEffectAnalysis: {},
  })
}
function routeFor(router, path) {
  if (path === '/knowledge' || path === '/learning-knowledge/:attemptId') return router.routes.find(route => route.path === path)
  const parent = router.routes.find(route => route.path === (path === '/teacher/knowledge' ? '/teacher' : '/admin/legal/kb'))
  const child = parent.children.find(route => route.path === (path === '/teacher/knowledge' ? 'knowledge' : path.endsWith('/tools') ? 'tools' : ''))
  return { ...child, path, meta: { ...parent.meta, ...child.meta } }
}

for (const [path, role, expected] of [
  ['/knowledge', 'guest', '/login'], ['/knowledge', 'student', '/'],
  ['/knowledge', 'teacher', '/teacher/knowledge'], ['/knowledge', 'admin', '/admin/legal/kb'],
  ['/teacher/knowledge', 'guest', '/login'], ['/teacher/knowledge', 'student', '/'],
  ['/teacher/knowledge', 'teacher', undefined], ['/teacher/knowledge', 'admin', '/admin/dashboard'],
  ['/admin/legal/kb', 'student', '/'], ['/admin/legal/kb', 'teacher', '/'], ['/admin/legal/kb', 'admin', undefined],
  ['/admin/legal/kb/tools', 'admin', undefined], ['/admin/legal/kb/tools', 'student', '/'],
  ['/learning-knowledge/:attemptId', 'student', undefined], ['/learning-knowledge/:attemptId', 'guest', '/login'],
]) {
  test(`knowledge route guard: ${path}, ${role}`, () => {
    const router = routerFor({ isAuthenticated: role !== 'guest', userInfo: { role } })
    const route = routeFor(router, path)
    const decisions = []
    router.guard(route, {}, value => decisions.push(value))
    assert.deepEqual(decisions, [expected])
  })
}

for (const role of ['student', 'teacher', 'admin']) {
  test(`real router resolves direct, query, trailing-slash and named library navigation: ${role}`, async () => {
    const config = routerFor({ isAuthenticated: true, userInfo: { role } })
    // Use the actual route records/guard with inert components, avoiding browser-only imports.
    const stubRoutes = routes => routes.map(route => ({
      ...route, component: route.component ? { render: () => null } : undefined,
      children: route.children ? stubRoutes(route.children) : undefined,
    }))
    const router = createRouter({ history: createMemoryHistory(), routes: stubRoutes(config.routes) })
    router.beforeEach(config.guard)
    for (const target of ['/knowledge', '/knowledge?attempt_id=00000000-0000-4000-8000-000000000001', '/knowledge/', { name: 'KnowledgeLibrary' }]) {
      await router.push('/resources')
      await router.push(target)
      const expected = role === 'teacher' ? '/teacher/knowledge' : role === 'admin' ? '/admin/legal/kb' : '/'
      assert.equal(router.currentRoute.value.path, expected)
      assert.notEqual(router.currentRoute.value.name, 'KnowledgeLibrary')
    }
  })
}
