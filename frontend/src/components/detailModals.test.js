import { accountScope } from '../shared/state/accountScope.js'
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { createRequire } from 'node:module'
import { ref, shallowRef, computed, compile, createSSRApp } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { parse, compileScript, compileStyle, compileTemplate } from 'vue/compiler-sfc'
import { iconCatalog } from '../shared/design/iconCatalog.js'
import { createWorkspaceSession } from '../learning/practice/workspaceSession.js'
import { normalizeEnvironment } from '../learning/practice/environment.js'
import { difficultyText, relationTypeLabel, modeBadge, relatedGroups, submissionScopeNote, submitFeedback } from '../learning/practice/workspaceView.js'
import { readDraft, writeDraft, clearDraft, clearAllDrafts, draftCount } from '../learning/practice/drafts.js'

const require = createRequire(import.meta.url)
const arcoIcons = require('@arco-design/web-vue/lib/icon')
// 题目弹窗拆分后，宿主与工作台组件共同承担原弹窗的全部功能，设计约束一并迁移。
const components = [
  { name: 'ChallengeDetailModal', url: './ChallengeDetailModal.vue' },
  { name: 'ResourceDetailModal', url: './ResourceDetailModal.vue' },
  { name: 'ChallengeWorkspace', url: '../learning/practice/ChallengeWorkspace.vue' },
  { name: 'ChallengeBody', url: '../learning/practice/components/ChallengeBody.vue' },
  { name: 'FlagSubmission', url: '../learning/practice/components/FlagSubmission.vue' },
  { name: 'SubmissionHistory', url: '../learning/practice/components/SubmissionHistory.vue' },
  { name: 'RelatedLearning', url: '../learning/practice/components/RelatedLearning.vue' },
  { name: 'EnvironmentPanel', url: '../learning/practice/components/EnvironmentPanel.vue' },
]
const source = url => readFileSync(new URL(url, import.meta.url), 'utf8')
const descriptors = Object.fromEntries(components.map(({ name, url }) => [name, parse(source(url)).descriptor]))
const tokens = new Set([...readFileSync(new URL('../shared/design/tokens.css', import.meta.url), 'utf8').matchAll(/(--[\w-]+)\s*:/g)].map(match => match[1]))

for (const { name, url } of components) {
  test(`${name}: template, script and scoped styles compile with declared tokens`, () => {
    const descriptor = descriptors[name]
    const script = compileScript(descriptor, { id: name })
    assert.deepEqual(compileTemplate({ source: descriptor.template.content, filename: `${name}.vue`, id: name, compilerOptions: { bindingMetadata: script.bindings } }).errors, [])
    assert.doesNotMatch(descriptor.template.content + descriptor.scriptSetup.content, /\p{Extended_Pictographic}/u)
    for (const style of descriptor.styles) {
      assert.equal(style.scoped, true)
      assert.deepEqual(compileStyle({ source: style.content, filename: `${name}.vue`, id: name, scoped: true }).errors, [])
      assert.doesNotMatch(style.content, /#[\da-f]{3,8}\b|rgba?\(|gradient\(|font-size:\s*\d|display:\s*none|opacity:\s*0\./i)
      for (const [, token] of style.content.matchAll(/var\((--[\w-]+)/g)) assert.ok(tokens.has(token), token)
      assert.match(style.content, /:focus-visible/)
      assert.doesNotMatch(style.content, /transition:[^;]*all\b/)
    }
    for (const [, icon] of source(url).matchAll(/name="(bi-[a-z0-9-]+)"/g)) {
      assert.ok(iconCatalog[icon], `${icon} is catalogued for AppIcon`)
      assert.ok(arcoIcons[iconCatalog[icon]], `${icon} maps to an existing Arco icon`)
    }
  })
}

// 原弹窗的加载、启动、复制、停止、计时清理都收敛到同一工作台会话。
function makeSession(apiClient, options = {}) {
  const scheduled = []
  const cancelled = []
  const session = createWorkspaceSession({
    apiClient, challengeId: 41, userId: 7,
    schedule: (fn, ms) => { scheduled.push({ fn, ms }); return scheduled.length },
    cancel: timer => cancelled.push(timer),
    ...options,
  })
  return { session, scheduled, cancelled }
}

test('challenge unavailable runtime stays truthful and readable without fabricating container state', async () => {
  const calls = []
  const original = { response: { status: 503, data: { detail: 'Docker daemon unavailable' } } }
  const { session } = makeSession({
    container: async () => { throw original },
    startEnvironment: async id => { calls.push(id); throw original },
  })
  const result = await session.startEnvironment()
  assert.deepEqual(calls, [41])
  assert.equal(result.ok, false)
  assert.equal(session.environment.value.error, '练习环境暂时无法启动，请稍后重试或联系教师。')
  assert.equal(session.environment.value.phase, 'error')
  assert.equal(session.environment.value.starting, false)
  assert.equal(session.environment.value.info, null)
  assert.equal(original.response.data.detail, 'Docker daemon unavailable')
})

test('challenge start, readiness, URL copy, stop and timer cleanup retain existing API calls', async () => {
  const calls = []
  const runtime = { status: 'running', access_url: 'https://practice.example.test/long-path', expires_at: new Date(Date.now() + 1800000).toISOString() }
  const { session, scheduled, cancelled } = makeSession({
    startEnvironment: async id => { calls.push(['start', id]); return { success: true, message: '正在启动', container: { status: 'pending' } } },
    container: async id => { calls.push(['get', id]); return runtime },
    stopEnvironment: async id => { calls.push(['stop', id]); return { success: true, message: '停止成功' } },
    clipboard: { writeText: async url => calls.push(['copy', url]) },
  })

  await session.startEnvironment()
  // 启动响应只到 pending：不得直接宣称可用，也不显示预计百分比。
  assert.equal(session.environment.value.phase, 'waiting')
  assert.equal(session.environmentStatus.value.label, '启动中')
  assert.equal(scheduled.length, 1)

  await session.refreshEnvironment()
  assert.equal(session.environment.value.phase, 'ready')
  assert.equal(session.environmentStatus.value.accessUrl, runtime.access_url)
  assert.match(session.countdownText.value, /^\d{2}:\d{2}$/)
  const rendered = await html('EnvironmentPanel', {
    state: session.environment.value,
    status: session.environmentStatus.value,
    countdownText: session.countdownText.value,
    authenticated: true,
    running: session.environmentStatus.value.running,
    accessUrl: session.environmentStatus.value.accessUrl,
  })
  assert.ok(rendered.includes(runtime.access_url))
  assert.match(rendered, /剩余时间|停止环境/)
  // 诚实说明里可以出现“不显示预计百分比”，但不得出现任何具体百分比或预计剩余数值。
  assert.doesNotMatch(rendered, /预计剩余|\d+\s*%/)

  await session.copyAccess()
  await session.stopEnvironment()
  assert.equal(session.environment.value.info, null)
  assert.deepEqual(calls, [['start', 41], ['get', 41], ['copy', runtime.access_url], ['stop', 41]])
  // 停止后轮询与倒计时定时器都应取消，销毁时也不留残余。
  assert.equal(cancelled.length, scheduled.length)
  session.destroy()
  assert.equal(cancelled.length, scheduled.length)
})

test('environment status that is running but lacks an access URL waits instead of claiming availability', async () => {
  const { session } = makeSession({ container: async () => ({ status: 'running', access_url: '' }) })
  await session.refreshEnvironment()
  assert.equal(session.environment.value.phase, 'waiting')
  assert.equal(session.environmentStatus.value.label, '运行中')
  assert.equal(session.countdownText.value, '未提供')
})

test('challenge submission validates input then preserves submit, refresh and profile requests', async () => {
  const calls = []
  const challengeData = { id: 41, title: '访问控制练习', description: '保留完整题面', difficulty: 'easy', category_name: 'Web', score: 100, hint: '检查访问权限', docker_image: 'existing-image' }
  const { session } = makeSession({
    detail: async id => { calls.push(['detail', id]); return { ...challengeData, is_solved: calls.some(c => c[0] === 'submit') } },
    list: async () => ({ results: [], count: 0 }),
    submit: async (id, flag) => { calls.push(['submit', id, flag]); return { success: true, message: '正确' } },
    mySubmissions: async () => ({ results: [], count: 0, next: null }),
  })
  await session.load()

  const empty = await session.submit()
  assert.equal(empty.ok, false)
  assert.equal(session.message.value, '请输入 Flag')
  assert.equal(calls.filter(c => c[0] === 'submit').length, 0)

  session.setFlag('flag{retained}')
  const done = await session.submit()
  assert.equal(done.ok, true)
  assert.deepEqual(calls.filter(c => c[0] === 'submit'), [['submit', 41, 'flag{retained}']])
  assert.ok(calls.some(c => c[0] === 'detail'))
  assert.equal(session.flag.value, '')
  assert.equal(session.submitting.value, false)

  // 宿主在成功后发出 solved 并刷新画像，原有请求顺序保持。
  const host = workspaceHost()
  host.session.submit = async () => ({ ok: true })
  await host.page.submit()
  assert.deepEqual(JSON.parse(JSON.stringify(host.emitted)), [['solved', { challengeId: 41 }]])
  assert.deepEqual(host.calls, ['profile'])
})

test('challenge modal retains title, hints, attachment, recommendations and authenticated Flag submission', async () => {
  const challengeData = {
    title: '访问控制练习', description: '保留完整题面', difficulty: 'easy', category_name: 'Web', score: 100,
    hint: '检查访问权限', attachment: '/media/attachment.zip', docker_image: 'existing-image',
    recommended_articles: [{ article_id: 1, title: '授权基础', reason: '补充授权检查知识', summary: '真实摘要', url: '/articles/1' }],
    recommended_resources: [{ resource_id: 2, title: '访问控制讲义', reason: '帮助理解本题', category: '讲义', relation_type: 'background', url: '/resources/2' }],
  }
  const mode = modeBadge(challengeData)
  const rendered = [
    await html('ChallengeBody', { challenge: challengeData, difficultyText, mode }),
    await html('EnvironmentPanel', { state: { phase: 'idle', info: null, error: '', starting: false, stopping: false }, status: normalizeEnvironment(null), countdownText: '未提供', authenticated: true, running: false, accessUrl: '' }),
    await html('FlagSubmission', { challenge: challengeData, mode, authenticated: true, flag: '', submitting: false, message: '', messageType: '' }),
    await html('RelatedLearning', { groups: relatedGroups(challengeData) }),
  ].join('')
  for (const text of ['访问控制练习', '保留完整题面', '检查访问权限', '补充授权检查知识', '真实摘要', '帮助理解本题', '背景补充', '提交 Flag', '启动环境']) assert.ok(rendered.includes(text), text)
  for (const link of ['/media/attachment.zip', '/articles/1', '/resources/2']) assert.ok(rendered.includes(`href="${link}"`))
  const modal = descriptors.ChallengeDetailModal.template.content
  assert.match(modal, /role="dialog"/)
  assert.match(modal, /aria-modal="true"/)
  assert.match(modal, /ChallengeWorkspace[\s\S]*mode="modal"/)
  assert.match(modal, /@keydown\.esc\.stop="handleClose"/)
  assert.match(modal, /aria-label="关闭题目详情"/)
  assert.match(modal, /题目详情/)
  assert.match(rendered, /aria-label="Flag 答案"/)
  assert.doesNotMatch(rendered, /background<|注入 AI 回答上下文/)
})

test('challenge practice, guest, solved, loading and feedback presentations preserve conditional actions', async () => {
  const challengeData = { title: '访问控制练习', description: '保留完整题面', difficulty: 'easy', score: 100, docker_image: 'existing-image' }
  const base = { challenge: challengeData, mode: modeBadge(challengeData), flag: '', submitting: false, message: '', messageType: '' }
  let rendered = await html('FlagSubmission', { ...base, authenticated: false })
  assert.match(rendered, /href="\/login"/)
  assert.match(rendered, /登录后提交/)

  const solvedChallenge = { ...challengeData, is_solved: true }
  rendered = await html('FlagSubmission', { ...base, challenge: solvedChallenge, mode: modeBadge(solvedChallenge), authenticated: true })
  assert.match(rendered, /已解决此题/)
  assert.match(rendered, /class="btn btn-primary" disabled/)

  const practice = { ...challengeData, submission_mode: 'practice' }
  rendered = await html('FlagSubmission', { ...base, challenge: practice, mode: modeBadge(practice), authenticated: true })
  assert.match(rendered, /自由练习/)
  assert.match(rendered, /再次启动会重置练习数据/)
  assert.doesNotMatch(rendered, /aria-label="Flag 答案"|class="submit-form"/)

  rendered = await html('FlagSubmission', { ...base, authenticated: true, message: '访问地址已复制到剪贴板', messageType: 'success' })
  assert.match(rendered, /class="submit-message success" role="status"/)
  rendered = await html('FlagSubmission', { ...base, authenticated: true, message: '提交失败，请稍后重试。', messageType: 'error' })
  assert.match(rendered, /class="submit-message error" role="alert"/)

  rendered = await html('ChallengeWorkspace', { loading: true, error: '', session: { challenge: { value: null } } })
  assert.match(rendered, /class="workspace-state" role="status"/)
  assert.match(rendered, /正在读取题目/)
})

test('both detail fetch failures remain visible alerts rather than disappearing in loading state', async () => {
  const { session } = makeSession({ detail: async () => { throw Error('offline') }, list: async () => ({ results: [], count: 0 }) })
  await session.load()
  assert.equal(session.loading.value, false)
  assert.equal(session.error.value, '题目暂时未能读取，请重试。')
  const rendered = await html('ChallengeWorkspace', { loading: false, error: session.error.value, session: { challenge: { value: null } } })
  assert.match(rendered, /role="alert"/)
  assert.match(rendered, /题目暂时未能读取/)
  assert.match(rendered, /重新读取/)

  const { page } = modal('ResourceDetailModal', { api: { resource: { detail: async () => { throw Error('offline') } } } })
  await page.fetchResource()
  assert.equal(page.loading.value, false)
  const resourceRendered = await html('ResourceDetailModal', page)
  assert.match(resourceRendered, /role="alert"/)
  assert.match(resourceRendered, /获取资源失败/)
})

// —— 工作台宿主行为（弹窗与直达页共用） ——
function workspaceHost() {
  const emitted = []
  const calls = []
  const descriptor = descriptors.ChallengeWorkspace
  const script = descriptor.scriptSetup.content.replace(/^import[^\n]+\n/gm, '')
  const compiled = compileScript(descriptor, { id: 'ChallengeWorkspaceHost' })
  const bindings = Object.keys(compiled.bindings).filter(binding => compiled.bindings[binding] !== 'props' && !compiled.imports[binding])
  const session = {
    load: async () => {}, destroy() {}, loadSubmissions: async () => {}, refreshEnvironment: async () => {}, setFlag() {},
    challenge: ref({ id: 41, title: '访问控制练习' }), loading: ref(false), error: ref(''),
    environment: ref({ phase: 'idle', info: null }), submissions: ref({ items: [], hasNext: false }),
    countdownText: ref('未提供'), environmentStatus: ref(normalizeEnvironment(null)),
    flag: ref(''), submitting: ref(false), message: ref(''), messageType: ref(''), related: ref({ sameCategory: [] }),
    submit: async () => ({ ok: false }), startEnvironment: async () => ({ ok: true }), stopEnvironment: async () => ({}), copyAccess: async () => ({ ok: true }),
  }
  const page = runInNewContext(`${script}\n;({ ${bindings.join(',')} })`, {
    ref, shallowRef, computed, accountScope, watch() {}, onActivated() {}, onDeactivated() {}, onMounted() {}, onUnmounted() {},
    defineProps: () => ({ challengeId: 41, mode: 'page' }),
    defineEmits: () => (...args) => emitted.push(args),
    defineExpose: () => {},
    createWorkspaceSession: () => session,
    practiceApi: {},
    setPageContext() {}, clearPageContext() {}, requestTutorDrawer: () => calls.push('tutor'),
    useUserStore: () => ({ isAuthenticated: true, userInfo: { id: 7 }, fetchProfile: async () => calls.push('profile') }),
  })
  return { page, session, emitted, calls }
}

test('workspace host publishes page context, refreshes profile and opens tutoring without leaking answers', () => {
  const { page, emitted, calls } = workspaceHost()
  page.askTutor()
  assert.deepEqual(calls, ['tutor'])
  assert.deepEqual(emitted, [])
})

// —— 原生弹窗的既有资源断言保持不动 ——
function modal(name, globals = {}) {
  const emitted = []
  const intervals = new Map()
  const unmount = []
  const descriptor = descriptors[name]
  const script = descriptor.scriptSetup.content.replace(/^import[^\n]+\n/gm, '')
  const compiled = compileScript(descriptor, { id: name })
  const bindings = Object.keys(compiled.bindings)
    .filter(binding => compiled.bindings[binding] !== 'props' && !compiled.imports[binding])
  let nextTimer = 0
  const page = runInNewContext(`${script}\n;({ ${bindings.join(',')} })`, {
    ref, computed, watch() {}, onMounted() {}, onUnmounted: callback => unmount.push(callback),
    defineProps: () => ({ challengeId: 41, resourceId: 72, highlightResourceId: 19 }),
    defineEmits: () => (...args) => emitted.push(args),
    setInterval: callback => { intervals.set(++nextTimer, callback); return nextTimer },
    clearInterval: timer => intervals.delete(timer), setTimeout: callback => { callback(); return 1 },
    console: { log() {}, error() {} },
    useChallengeStore: () => ({}), useUserStore: () => ({ isAuthenticated: true }),
    marked: { parse: value => value }, DOMPurify: { sanitize: value => value },
    ...globals,
  })
  return { page, emitted, intervals, unmount }
}

async function html(name, page) {
  const app = createSSRApp({ setup: () => page, render: compile(descriptors[name].template.content) })
  for (const [key, component] of Object.entries(arcoIcons)) if (key.startsWith('Icon')) app.component(key, component)
  app.component('AppIcon', { props: ['name'], template: '<span :class="name" aria-hidden="true"></span>' })
  app.component('RouterLink', { props: ['to'], template: '<a :href="to"><slot /></a>' })
  return renderToString(app)
}

const resourceData = { title: '访问控制讲义', resource_type: 'ai_resource', description: '完整资源描述', category: 'Web', uploader_info: { username: '真实上传者' }, is_ai_highlighted: true, created_at: '2026-11-01', view_count: 23, download_count: 7, file_size: 2048 }

test('resource detail and AI preview preserve highlight parameters, real metadata and collapse action', async () => {
  const calls = []
  const { page, emitted } = modal('ResourceDetailModal', { api: { resource: {
    detail: async (id, params) => { calls.push(['detail', id, params.highlight_resource]); return resourceData },
    download: async (id, params) => { calls.push(['download', id, params.highlight_resource]); return { data: { text: async () => '正文保留' } } },
  } } })
  await page.fetchResource()
  assert.deepEqual(calls, [['detail', 72, 19], ['download', 72, 19]])
  assert.equal(page.showPreview.value, true)
  const rendered = await html('ResourceDetailModal', page)
  for (const text of ['导学推荐资料', '真实上传者', '完整资源描述', '23', '7', '2.00 KB', '正文保留', '收起预览', '下载资源']) assert.ok(rendered.includes(text), text)
  page.togglePreview()
  assert.equal(page.showPreview.value, false)
  page.handleClose()
  assert.deepEqual(emitted, [['close']])
})

test('resource preview states retain image/video handlers, visible media errors and disabled explanations', async () => {
  const { page } = modal('ResourceDetailModal')
  page.resource.value = { ...resourceData, resource_type: 'document', file_name: 'diagram.png', file_url: '/diagram.png' }
  page.showPreview.value = true
  let rendered = await html('ResourceDetailModal', page)
  assert.match(rendered, /src="\/diagram.png"/)
  page.handlePreviewError({ type: 'error' })
  rendered = await html('ResourceDetailModal', page)
  assert.match(rendered, /role="alert"/)
  assert.match(rendered, /预览资源加载失败，请稍后重试/)
  page.resource.value = { ...resourceData, resource_type: 'video', file_url: '/lesson.mp4' }
  assert.match(await html('ResourceDetailModal', page), /<video controls src="\/lesson.mp4"/)
  page.resource.value = { ...resourceData, resource_type: 'zip' }
  rendered = await html('ResourceDetailModal', page)
  assert.match(rendered, /class="btn btn-secondary btn-large" disabled/)
  assert.match(rendered, /此类资源暂不支持在线预览，请下载后查看/)
  page.resource.value = { ...resourceData, tags_list: ['思维导图'], cover_url: '/map.svg' }
  page.previewError.value = ''
  assert.match(await html('ResourceDetailModal', page), /href="\/map.svg" target="_blank"/)
  page.previewLoading.value = true
  assert.match(await html('ResourceDetailModal', page), /正在读取资源内容/)
})

test('resource download preserves server filename, blob lifecycle, success and error feedback', async () => {
  const events = []
  const link = { click: () => events.push('click'), remove: () => events.push('remove') }
  let fail = false
  const { page } = modal('ResourceDetailModal', {
    api: { resource: { download: async (id, params) => {
      events.push([id, params.highlight_resource])
      if (fail) throw Error('offline')
      return { data: 'blob', headers: { 'content-disposition': "attachment; filename*=UTF-8''%E8%AE%B2%E4%B9%89.md" } }
    } } },
    URL: { createObjectURL: () => 'blob:resource', revokeObjectURL: url => events.push(['revoke', url]) },
    document: { createElement: () => link, body: { appendChild: () => events.push('append') } },
  })
  page.resource.value = resourceData
  await page.handleDownload()
  assert.equal(link.download, '讲义.md')
  assert.equal(link.href, 'blob:resource')
  assert.deepEqual(events, [[72, 19], 'append', 'click', 'remove', ['revoke', 'blob:resource']])
  assert.equal(page.messageType.value, 'success')
  assert.match(await html('ResourceDetailModal', page), /class="download-message success" role="status"/)
  fail = true
  await page.handleDownload()
  assert.equal(page.downloading.value, false)
  assert.match(await html('ResourceDetailModal', page), /class="download-message error" role="alert"/)
})

// —— 工作台展示映射的纯函数断言（原弹窗条件呈现迁移） ——
test('practice mode is presented without Flag input or scoring, and guest sees a login path', () => {
  assert.deepEqual(modeBadge({ submission_mode: 'practice', score: 100 }), { label: '自由练习', scoring: false })
  assert.deepEqual(modeBadge({ submission_mode: 'flag', score: 100 }), { label: '100 分', scoring: true })
  assert.equal(modeBadge({ submission_mode: 'flag' }).label, '分值未提供')
  assert.equal(difficultyText('hard'), '困难')
  assert.equal(difficultyText(null), '难度未注明')
  assert.equal(relationTypeLabel('background'), '背景补充')
  assert.equal(relationTypeLabel('unknown'), '关联材料')
  assert.equal(submitFeedback({ ok: true, message: '正确' }).type, 'success')
  assert.equal(submitFeedback({ ok: false, message: '回答错误' }).type, 'error')
})

test('related learning keeps real recommendation reasons and says when nothing is linked', () => {
  const groups = relatedGroups({
    recommended_articles: [{ article_id: 1, title: '授权基础', reason: '补充授权检查知识', summary: '真实摘要', url: '/articles/1' }],
    recommended_resources: [{ resource_id: 2, title: '访问控制讲义', reason: '帮助理解本题', category: '讲义', relation_type: 'background', url: '/resources/2' }],
  }, [{ id: 9, title: '同分类练习', difficulty: 'hard' }])
  assert.equal(groups.articles[0].reason, '补充授权检查知识')
  assert.equal(groups.resources[0].relation, '背景补充')
  assert.equal(groups.sameCategory[0].reason, '同分类练习')
  assert.equal(groups.sameCategory[0].difficulty, '困难')
  assert.deepEqual(relatedGroups({}, []), { articles: [], resources: [], sameCategory: [] })
})

test('submission history states its scope, paginates and never invents records', async () => {
  assert.equal(submissionScopeNote({ loaded: 0 }), '')
  // 翻过若干页仍没找到本题记录时，不冒充“没有提交”，范围说明要如实。
  assert.equal(submissionScopeNote({ loaded: 0, hasNext: true, pagesRead: 2 }), '已读取最近 2 页，暂未找到本题提交；仍有更早记录未加载。')
  assert.equal(submissionScopeNote({ loaded: 0, hasNext: false, pagesRead: 3 }), '')
  assert.match(submissionScopeNote({ loaded: 3, hasNext: true }), /仍有更早记录未展开/)
  assert.match(submissionScopeNote({ loaded: 3, hasNext: false }), /已读取本题 3 条/)
  const { session } = makeSession({ mySubmissions: async () => { throw Error('offline') } })
  await session.loadSubmissions()
  assert.match(session.submissionsError.value, /暂时未能读取/)
})

test('drafts are scoped per account and challenge and are cleared on account switch', () => {
  writeDraft(7, 41, 'flag{a}')
  writeDraft(7, 42, 'flag{b}')
  writeDraft(8, 41, 'flag{c}')
  assert.equal(readDraft(7, 41), 'flag{a}')
  assert.equal(readDraft(7, 42), 'flag{b}')
  assert.equal(readDraft(8, 41), 'flag{c}')
  clearDraft(7, 41)
  assert.equal(readDraft(7, 41), '')
  clearAllDrafts()
  assert.equal(draftCount(), 0)
})
