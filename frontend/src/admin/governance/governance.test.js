import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { compile, createSSRApp, h } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { parse, compileScript, compileStyle, compileTemplate } from 'vue/compiler-sfc'
import { countValue, createSourceController, governanceError, listScope, listValue, numberValue, scoreLabel } from './data.js'
import { governanceTiles } from '../cockpit/model.js'
import { chunkLabel, grantPayload, indexIssue, jobStatus, supervisionFacts } from '../foundation/presentation.js'
import { challengeDistributions, platformStats, scoreTrend, studentSummary } from '../insights/presentation.js'
const read = path => readFileSync(new URL(path, import.meta.url), 'utf8')
const files = ['../views/Dashboard.vue', '../foundation/FoundationFrame.vue', '../foundation/FoundationLibrary.vue', '../foundation/IndexTools.vue', '../foundation/IndexHealth.vue', '../foundation/AuthorizationSupervision.vue', '../insights/PlatformInsights.vue', '../insights/AssessmentSupervision.vue', '../views/StudentLearning.vue', '../views/LearningScores.vue']
const tokens = new Set([...read('../../shared/design/tokens.css').matchAll(/(--[\w-]+):/g)].map(match => match[1]))
for (const file of files) test(`${file}: scoped semantic tokens and real Vue compilation`, () => {
  const source = read(file), descriptor = parse(source).descriptor
  assert.deepEqual(parse(source).errors, [])
  const script = compileScript(descriptor, { id: 'governance' })
  assert.deepEqual(compileTemplate({ source: descriptor.template.content, filename: file, id: 'governance', compilerOptions: { bindingMetadata: script.bindings } }).errors, [])
  for (const style of descriptor.styles) {
    assert.equal(style.scoped, true)
    const css = style.src ? readFileSync(new URL(style.src, new URL(file, import.meta.url)), 'utf8') : style.content
    assert.deepEqual(compileStyle({ source: css, filename: file, id: 'governance', scoped: true }).errors, [])
    assert.doesNotMatch(css, /#[\da-f]{3,8}\b|rgba?\(|outline\s*:\s*none/i)
    for (const [, token] of css.matchAll(/var\((--[\w-]+)/g)) assert.ok(tokens.has(token), token)
  }
  assert.doesNotMatch(source, /from ['"][^'"]*(?:@\/teacher\/|\.\.\/teacher\/)/)
  assert.doesNotMatch(source, /axios|\.get\(['"]\/api|v-html|setInterval/)
})

test('numeric and list contracts distinguish missing, malformed and genuine zero', () => {
  for (const value of [null, undefined, -1, '0', true, NaN, Infinity]) assert.equal(countValue(value), null)
  assert.equal(countValue(0), 0)
  for (const value of [null, undefined, '', true, 'abc']) assert.equal(numberValue(value), null)
  assert.equal(scoreLabel(null), '未提供'); assert.equal(scoreLabel(0), '0.00 分')
  assert.throws(() => listValue({ count: 0 })); assert.throws(() => listValue({ results: [null] }))
  assert.deepEqual(listValue({ results: [] }), [])
  assert.equal(listScope({ results: [{ title: '资料' }], count: 40 }), '本次已读取 1 条，共 40 条')
})

test('governance cards isolate content totals, sampled index issues, permissions and material supervision', () => {
  const tiles = governanceTiles({ resources: { data: { results: [], count: 31 } }, articles: { data: { results: [], count: 0 } }, jobs: { data: { results: [{ status: 'failed' }, { status: 'completed', total_chunks: 4, embedded_chunks: 2 }, { status: 'running' }] } }, applications: { data: [] }, materials: { data: { results: [{ review_status: 'in_review' }, { review_status: 'published' }] } } })
  assert.equal(tiles.find(row => row.key === 'resources').count, 31)
  assert.equal(tiles.find(row => row.key === 'articles').count, 0)
  assert.equal(tiles.find(row => row.key === 'jobs').count, 2)
  assert.equal(tiles.find(row => row.key === 'materials').count, 1)
  assert.equal(tiles.find(row => row.key === 'grants').count, null)
  assert.match(tiles.find(row => row.key === 'grants').notice, /还不能确认待处理数量/)
  for (const tile of tiles) assert.ok(tile.href.startsWith('/admin/'))
  assert.equal(tiles.find(row => row.key === 'resources').href, '/admin/resources?status=pending')
  assert.equal(tiles.find(row => row.key === 'jobs').href, '/admin/legal/kb/health?status=attention')
})

test('a failed content source never falls back to an unfiltered count or blocks other sources', async () => {
  const sources = { resources: {}, articles: {}, applications: {} }
  const controller = createSourceController(sources, { resources: async () => { throw { response: { status: 403 } } }, articles: async () => ({ results: [], count: 0 }), applications: async () => [] })
  await controller.load()
  const tiles = governanceTiles(sources)
  assert.equal(tiles[0].count, null); assert.match(tiles[0].error, /授权/)
  assert.equal(tiles[1].count, 0)
  assert.equal(sources.applications.loading, false)
})

test('refresh generation rejects delayed data, account changes and blocked roles', async () => {
  let resolve, allowed = true, calls = 0
  const sources = { records: {} }
  const controller = createSourceController(sources, { records: () => { calls++; return new Promise(done => { resolve = done }) } }, () => allowed)
  const pending = controller.load(); controller.clear(); resolve(['private']); await pending
  assert.equal(sources.records.data, null)
  const second = controller.load(); allowed = false; resolve(['other account']); await second
  assert.equal(sources.records.data, null)
  await controller.load(); assert.equal(calls, 2)
})

test('newer source reads win and old errors cannot replace them', async () => {
  let fail
  const sources = { records: {} }
  let first = true
  const controller = createSourceController(sources, { records: () => { if (first) { first = false; return new Promise((_, reject) => { fail = reject }) } return { results: [], count: 0 } } })
  const old = controller.load(); await controller.load(); fail(Error('old')); await old
  assert.equal(sources.records.error, '')
  assert.equal(sources.records.data.count, 0)
})

test('index health states do not equate pending, absent counts or missing coverage with success', () => {
  assert.equal(jobStatus('future'), '状态待确认')
  assert.equal(indexIssue({ status: 'running' }), '')
  assert.equal(indexIssue({ status: 'completed', total_chunks: 0, embedded_chunks: 0 }), '')
  assert.match(indexIssue({ status: 'completed', total_chunks: 6, embedded_chunks: 3 }), /不一致/)
  assert.equal(chunkLabel({ total_chunks: null, embedded_chunks: 0 }), '段落数量未提供')
  assert.match(read('../foundation/IndexHealth.vue'), /持续可用、全部来源的索引覆盖率与实时告警尚未提供/)
})

test('authorization payload uses real directory choices and preserves staff review and secret restrictions', () => {
  const people = [{ id: 7, username: '学生', role: 'student' }, { id: 8, username: '教师', role: 'teacher' }, { id: 9, username: '管理员', role: 'admin' }]
  const catalog = { version: 'course-version', label: '课程' }
  const form = { user: 8, active: false, can_review: true, maintain_secrets: false }
  assert.deepEqual(grantPayload(form, people, catalog), { catalog_version: 'course-version', user_id: 8, active: false, can_review: true, maintain_secrets: false })
  assert.throws(() => grantPayload({ ...form, user: 7 }, people, catalog), /教师或管理员/)
  assert.throws(() => grantPayload({ ...form, maintain_secrets: true }, people, catalog), /只能授予管理员/)
  assert.throws(() => grantPayload({ ...form, user: 123 }, people, catalog), /选择/)
  assert.throws(() => grantPayload(form, people, null), /选择/)
})

test('material supervision resolves names, does not render raw personnel keys or approve materials', () => {
  const facts = supervisionFacts({ author_id: 11, reviewer_id: 11, published_scope: 'internal' }, [{ id: 11, username: '审阅教师' }])
  assert.equal(facts[0][1], '审阅教师'); assert.match(facts[3][1], /同一人/)
  assert.doesNotMatch(read('../foundation/AuthorizationSupervision.vue'), /\.transition\(|\.register\(|\.revise\(|author_id\s*}}|reviewer_id\s*}}|v-html/)
})

test('restricted material maintenance retains the shared staff workbench without teacher privilege expansion', () => {
  const supervision = read('../foundation/AuthorizationSupervision.vue')
  assert.match(supervision, /to="\/admin\/legal\/kb\/materials"/)
  assert.match(supervision, /names\.materialMaintenance/)
  assert.match(supervision, /仅供已有相应权限的人员/)
  assert.match(supervision, /后台独立校验/)
  const workbench = read('../../learningKnowledge/TeachingKnowledge.vue')
  assert.match(workbench, /user\.userInfo\?\.role === 'admin' \? names\.materialMaintenance : names\.materials/)
  assert.match(workbench, /shared\/knowledge\/staffApi\.js/)
  assert.doesNotMatch(workbench, /from ['"][^'"]*(?:@\/teacher\/|\.\.\/teacher\/)/)
  for (const action of ['submit', 'approve', 'publish', 'withdraw']) assert.ok(workbench.includes(`value="${action}"`))
  for (const action of ['register', 'revise', 'transition', 'inspect']) assert.ok(workbench.includes(`knowledgeApi.${action}(`))
  assert.match(workbench, /MaterialEditor/)
  assert.match(workbench, /MaterialInspection/)
  assert.match(workbench, /usePrivatePage\(clearContent\)/)
  assert.throws(() => grantPayload({ user: 8, active: true, can_review: true, maintain_secrets: true }, [{ id: 8, role: 'teacher' }], { version: 'course' }), /只能授予管理员/)
})

test('platform statistics are source-specific and unknown metrics remain unknown', () => {
  const stats = platformStats({ users: { data: { total: 9 } }, leaderboard: { data: { total: 4 } }, challenges: { data: [{}, {}] }, submissions: { data: { total_submissions: 0, success_rate: 0 } } })
  assert.equal(stats.totalUsers, 9); assert.equal(stats.rankedUsers, 4); assert.equal(stats.totalChallenges, 2)
  assert.equal(stats.totalSubmissions, 0); assert.equal(stats.successRate, 0)
  for (const key of ['newUsers', 'activeChallenges', 'totalScore', 'avgScore']) assert.equal(stats[key], null)
  const absent = platformStats({ users: { data: { total: null } }, submissions: { data: { success_rate: 101 } } })
  assert.equal(absent.totalUsers, null); assert.equal(absent.successRate, null)
})

test('distribution counts preserve uncategorized items and use only their own denominator', () => {
  const result = challengeDistributions([{ category_name: '网络安全', difficulty: 'easy' }, {}, { category_name: '网络安全', difficulty: 'future' }])
  assert.equal(result.categories.find(row => row.name === '网络安全').percentage, 67)
  assert.equal(result.categories.find(row => row.name === '未分类').count, 1)
  assert.equal(result.difficulties.find(row => row.name === '未标注').count, 2)
  assert.deepEqual(challengeDistributions([]), { categories: [], difficulties: [] })
})

test('student usage keeps real zero mastery, sample scopes and missing solved counts', () => {
  const summary = studentSummary([{ mastery: 0, solved_count: 0, onboarded: false }, { mastery: 100, solved_count: null, onboarded: true }, { mastery: null }])
  assert.equal(summary.averageMastery, 50); assert.equal(summary.masterySamples, 2)
  assert.equal(summary.onboarded, 1); assert.equal(summary.onboardedSamples, 2)
  assert.equal(summary.correctSubmissions, null)
  assert.equal(studentSummary([]).averageMastery, null)
})

test('assessment trend gaps remain gaps, and validity follows actual records', () => {
  const trend = scoreTrend([{ measured_at: '2026-11-02', dimension_scores: {}, validity_status: 'expired' }, { measured_at: '2026-11-01', dimension_scores: { web: 0 }, validity_status: 'effective' }], 'web')
  assert.equal(trend[0].value, 0); assert.equal(trend[1].value, null)
  assert.equal(trend[0].validity, '有效'); assert.equal(trend[1].validity, '已过期')
})

test('assessment and platform facades are independent read-only admin modules, teacher grading remains available', () => {
  const api = read('../insights/api.js')
  assert.doesNotMatch(api, /createAdminScore\(|createTeacherScore\(|\.post\(|learningAgent|analytics\.insights\(|teacherStudentReport/)
  for (const marker of ['adminStudentReport', 'adminScores', 'adminTeachingPlan', 'adminStats']) assert.ok(api.includes(marker))
  assert.match(read('../views/LearningScores.vue'), /AssessmentSupervision/)
  assert.match(read('../views/StudentLearning.vue'), /PlatformInsights/)
  assert.match(read('../../teacher/assessment/TeacherAssessment.vue'), /录入评分|保存评分并生成方案/)
})

test('staff governance facade never changes student evidence API and uses CSRF before writes', () => {
  const transport = read('../../shared/knowledge/governanceApi.js')
  assert.match(transport, /await get\('\/users\/csrf\//)
  for (const endpoint of ['documents', 'ingestion-jobs', 'embeddings', 'retrieval-logs', 'teaching-knowledge/grants']) assert.ok(transport.includes(endpoint))
  assert.doesNotMatch(transport, /localStorage|interceptors|learning-knowledge\/evidence|learning-knowledge\/search/)
  assert.match(read('../../shared/knowledge/staffApi.js'), /\.\.\.governanceKnowledgeApi/)
})

test('unknown operation errors never claim success or expose backend internals', () => {
  assert.match(governanceError({ response: { status: 403 } }), /核对授权/)
  assert.match(governanceError({ response: { status: 400, data: { error: 'private_id = SQL' } } }, true), /提交未被接受/)
  assert.doesNotMatch(governanceError({ response: { status: 500, data: 'private_id' } }, true), /private_id/)
  for (const file of ['../foundation/IndexTools.vue', '../foundation/AuthorizationSupervision.vue']) {
    const source = read(file)
    assert.match(source, /mutationPending\.value\) uncertain\.value = true/)
    assert.match(source, /request\.isCurrent\(\)/)
    assert.match(source, /uncertain/)
  }
})

const routerLink = { props: ['to'], setup: (props, { slots }) => () => h('a', { href: typeof props.to === 'string' ? props.to : props.to.path }, slots.default?.()) }
async function renderDashboard(allowed, sources) {
  const template = parse(read('../views/Dashboard.vue')).descriptor.template.content
  const app = createSSRApp({ render: compile(template), setup: () => ({ allowed, names: { admin: '治理驾驶舱', globalInsights: '全局洞察', foundation: '基座治理' }, loading: false, tiles: governanceTiles(sources), load() {} }) })
  app.component('router-link', routerLink); app.component('icon-arrow-right', { render: () => h('span', '打开') })
  return renderToString(app)
}
test('rendered governance empty, failed and denied states keep links and never fake counts or AI entrances', async () => {
  const html = await renderDashboard(true, { resources: { data: { results: [], count: 0 } }, articles: { error: '当前账号无法读取，请核对授权。' } })
  assert.match(html, /当前已读取范围内没有待办/)
  assert.match(html, /role="alert"/); assert.match(html, /还不能确认待处理数量/)
  assert.match(html, /href="\/admin\/resources\?status=pending"/)
  assert.doesNotMatch(html, /multi-agent|协作对话|模拟|总待办/)
  assert.equal((html.match(/class="governance-primary"/g) || []).length, 1)
  const denied = await renderDashboard(false, {})
  assert.match(denied, /仅供管理员/); assert.doesNotMatch(denied, /<a |治理待办|刷新待办/)
})
